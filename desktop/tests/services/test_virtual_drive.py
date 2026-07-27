"""Unit tests for VirtualDriveService: pagination, read sessions, listing cache.

Critical invariant: ``next_after`` is ALWAYS a string, never ``None``.

VirtualDrive.exe's C++ ``ReadDirectory`` reads this field with nlohmann
``j.value("next_after", "")``, which falls back to the default ONLY when the key
is absent. A present-but-``null`` value makes ``get<std::string>()`` throw
``type_error.302``; that exception escapes the WinFsp callback and terminates the
binary, tearing the drive down with "the I/O operation has been aborted" on every
empty folder. So an empty/last page must serialise ``next_after`` as ``""`` —
never ``None``.
"""

import json
import logging
import struct
import threading
from unittest.mock import MagicMock, patch

from services.virtual_drive import VirtualDriveService


def _entries(*names: str) -> list[dict]:
    """Build a sorted listing of entry dicts shaped like Android's response."""
    return [{"name": n, "is_dir": False, "size": 0, "mtime_ms": 0} for n in names]


def test_empty_dir_next_after_is_empty_string_not_none() -> None:
    """An empty directory must page to ``next_after == ""`` (never ``None``).

    This is the exact regression that crashed VirtualDrive.exe: ``None`` →
    JSON ``null`` → nlohmann ``type_error.302`` inside ``ReadDirectory``.
    """
    result = VirtualDriveService._page_entries([], None, 200)

    assert result == {
        "ok": True,
        "entries": [],
        "has_more": False,
        "next_after": "",
    }
    # Guard the invariant explicitly so a future refactor can't reintroduce null.
    assert result["next_after"] is not None
    assert isinstance(result["next_after"], str)


def test_last_page_next_after_is_string() -> None:
    """A non-empty page that exhausts the listing: ``has_more`` False, cursor a str."""
    result = VirtualDriveService._page_entries(_entries("a", "b"), None, 200)

    assert [e["name"] for e in result["entries"]] == ["a", "b"]
    assert result["has_more"] is False
    assert result["next_after"] == "b"
    assert isinstance(result["next_after"], str)


def test_full_page_sets_has_more_and_cursor() -> None:
    """More entries than the limit: ``has_more`` True, cursor = last name of page."""
    result = VirtualDriveService._page_entries(_entries("a", "b", "c"), None, 2)

    assert [e["name"] for e in result["entries"]] == ["a", "b"]
    assert result["has_more"] is True
    assert result["next_after"] == "b"


def test_after_cursor_advances_to_remainder() -> None:
    """Paging with the previous page's cursor returns only the remainder."""
    result = VirtualDriveService._page_entries(_entries("a", "b", "c"), "b", 2)

    assert [e["name"] for e in result["entries"]] == ["c"]
    assert result["has_more"] is False
    assert result["next_after"] == "c"


def test_after_cursor_past_end_is_empty_page() -> None:
    """A cursor at/after the last entry yields an empty page with ``next_after == ""``."""
    result = VirtualDriveService._page_entries(_entries("a", "b"), "b", 200)

    assert result["entries"] == []
    assert result["has_more"] is False
    assert result["next_after"] == ""


# ── Persistent read-session tests ──────────────────────────────────────────────


class _FakeStream:
    """Minimal stand-in for a TauSyncStream: records writes, replays canned reads."""

    def __init__(self, response: bytes = b"") -> None:
        self._buf = bytearray(response)
        self.written = bytearray()
        self.closed = False
        self.read_calls = 0
        self.read_until_calls = 0

    def feed(self, data: bytes) -> None:
        """Append bytes the peer will 'send back' on subsequent reads."""
        self._buf += data

    def write_string(self, text: str, encoding: str = "utf-8") -> int:
        self.written += text.encode(encoding)
        return len(text)

    def write(self, data: bytes) -> int:
        self.written += bytes(data)
        return len(data)

    def read(self, n: int = -1) -> bytes:
        self.read_calls += 1
        if n is None or n < 0:
            n = len(self._buf)
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def read_until(self, delimiter: bytes) -> bytes:
        """Read up to and including *delimiter*, leaving the rest buffered.

        Mirrors ``TauSyncStream.read_until``: bytes after the delimiter stay in
        the stream's own buffer and are returned by later ``read`` calls, which
        is what lets a header and the payload behind it share one stream.
        """
        self.read_until_calls += 1
        idx = self._buf.find(delimiter)
        if idx == -1:
            chunk = bytes(self._buf)
            self._buf.clear()
            return chunk
        end = idx + len(delimiter)
        chunk = bytes(self._buf[:end])
        del self._buf[:end]
        return chunk

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _service_with_streams(*streams: _FakeStream) -> VirtualDriveService:
    """Build a service whose ``connectivity.tau.connect`` hands out the given streams."""
    connectivity = MagicMock()
    connectivity.connected = True
    connectivity.tau.connect.side_effect = list(streams)
    return VirtualDriveService(connectivity=connectivity, device_info=MagicMock())


class _FakeFrameStream:
    """A named pipe carrying exactly one request frame, then EOF.

    ``_handle_connection`` talks frames (``[4B jsonLen][4B payLen][json][payload]``)
    rather than the JSON streams ``_FakeStream`` models, and loops until a read
    raises — so this serves one request and then hangs up to end the loop.
    """

    def __init__(self, req: dict, payload: bytes = b"") -> None:
        body = json.dumps(req).encode("utf-8")
        self._buf = bytearray(
            struct.pack("<II", len(body), len(payload)) + body + payload)
        self.written = bytearray()

    def read_exact(self, n: int, timeout: object = None) -> bytes:
        if len(self._buf) < n:
            raise EOFError("peer closed")  # ends _handle_connection's loop
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def write(self, data: bytes) -> int:
        self.written += bytes(data)
        return len(data)


def _serve_one(svc: VirtualDriveService, req: dict) -> _FakeFrameStream:
    """Run one request through ``_handle_connection`` and return the pipe.

    The serve loop is gated on ``_is_running``, which only ``start()`` sets — so
    flip it for the duration rather than spinning up the real pipe server.
    """
    pipe = _FakeFrameStream(req)
    svc._is_running.set()
    try:
        svc._handle_connection(pipe)
    finally:
        svc._is_running.clear()
    return pipe


def _read_header(length: int) -> bytes:
    """The framed read response header Android sends before the payload bytes."""
    return (json.dumps({"ok": True, "length": length}) + "\n").encode("utf-8")


def test_read_open_connects_once_and_sends_path_header() -> None:
    """``read_open`` opens one channel, sends ``{path}``, and registers the session."""
    stream = _FakeStream()
    svc = _service_with_streams(stream)

    resp, payload = svc._op_read_open({"path": "/DCIM/clip.mp4"}, b"")

    assert resp["ok"] is True
    session = resp["session"]
    assert session in svc._read_sessions
    assert svc._connectivity.tau.connect.call_count == 1
    assert json.loads(stream.written.decode().strip()) == {"path": "/DCIM/clip.mp4"}


def test_sessioned_read_reuses_stream_without_reconnecting() -> None:
    """A sessioned ``read`` reuses the open stream (no new connect) and returns bytes."""
    stream = _FakeStream()
    svc = _service_with_streams(stream)
    session = svc._op_read_open({"path": "/v.mp4"}, b"")[0]["session"]

    stream.feed(_read_header(3) + b"abc")
    resp, payload = svc._op_read(
        {"session": session, "offset": 10, "length": 3}, b"")

    assert resp == {"ok": True}
    assert payload == b"abc"
    # Still only the single read_open connect — the read reused the session stream.
    assert svc._connectivity.tau.connect.call_count == 1
    # The per-read request line carried only offset/length (path was sent at open).
    request_line = stream.written.decode().splitlines()[-1]
    assert json.loads(request_line) == {"offset": 10, "length": 3}


def test_read_close_closes_and_drops_session() -> None:
    """``read_close`` closes the stream and removes all session bookkeeping."""
    stream = _FakeStream()
    svc = _service_with_streams(stream)
    session = svc._op_read_open({"path": "/v.mp4"}, b"")[0]["session"]

    resp, _ = svc._op_read_close({"session": session}, b"")

    assert resp == {"ok": True}
    assert stream.closed is True
    assert session not in svc._read_sessions
    assert svc._read_sessions.get(session) is None


def test_sessioned_read_missing_session_is_error() -> None:
    """A read for an unknown session fails cleanly rather than raising."""
    svc = _service_with_streams()

    resp, payload = svc._op_read(
        {"session": "deadbeef", "offset": 0, "length": 5}, b"")

    assert resp["ok"] is False
    assert resp["error"] == "no_read_session"
    assert payload == b""


def test_fresh_read_without_session_opens_one_shot_channel() -> None:
    """A ``read`` with no session keeps the backward-compatible one-shot path."""
    stream = _FakeStream(_read_header(2) + b"hi")
    svc = _service_with_streams(stream)

    resp, payload = svc._op_read(
        {"path": "/photo.raw", "offset": 0, "length": 2}, b"")

    assert resp == {"ok": True}
    assert payload == b"hi"
    assert svc._connectivity.tau.connect.call_count == 1
    # Same wire protocol as a session: {path} open header then one {offset,length}
    # request, and the channel is closed after the single read.
    lines = stream.written.decode().splitlines()
    assert json.loads(lines[0]) == {"path": "/photo.raw"}
    assert json.loads(lines[1]) == {"offset": 0, "length": 2}
    assert stream.closed is True


# ── Buffered read-path tests (header + payload share one stream) ───────────────


def test_header_and_payload_arriving_together_are_split_correctly() -> None:
    """A header and payload delivered in one chunk must not lose the payload.

    ``read_until`` over-reads past the newline; the surplus stays in the
    stream's pushback buffer. If that buffer were ignored the payload would be
    silently dropped.
    """
    stream = _FakeStream(_read_header(5) + b"hello")
    svc = _service_with_streams(stream)

    resp, payload = svc._op_read(
        {"path": "/f.bin", "offset": 0, "length": 5}, b"")

    assert resp == {"ok": True}
    assert payload == b"hello"


def test_session_leftover_survives_across_two_reads() -> None:
    """Two full header+payload pairs fed at once must decode as two reads.

    The pushback buffer lives on the stream object, which outlives an individual
    read, so leftover bytes from the first exchange must still be there for the
    second.
    """
    stream = _FakeStream()
    svc = _service_with_streams(stream)
    session = svc._op_read_open({"path": "/v.mp4"}, b"")[0]["session"]

    stream.feed(_read_header(3) + b"abc" + _read_header(4) + b"wxyz")

    first = svc._op_read({"session": session, "offset": 0, "length": 3}, b"")
    second = svc._op_read({"session": session, "offset": 3, "length": 4}, b"")

    assert first == ({"ok": True}, b"abc")
    assert second == ({"ok": True}, b"wxyz")
    assert svc._connectivity.tau.connect.call_count == 1


def test_read_header_costs_one_buffered_read() -> None:
    """The response header is scanned in one buffered call, not one call per byte."""
    stream = _FakeStream(_read_header(3) + b"abc")
    svc = _service_with_streams(stream)

    svc._op_read({"path": "/f.bin", "offset": 0, "length": 3}, b"")

    # One read_until for the header; the payload needs at most a couple of reads.
    # The old per-byte loop issued ~30 read(1) calls for the header alone.
    assert stream.read_until_calls == 1
    assert stream.read_calls <= 2


def test_one_watchdog_thread_per_read_op() -> None:
    """A read op starts a single stall watchdog spanning header and payload."""
    stream = _FakeStream(_read_header(3) + b"abc")
    svc = _service_with_streams(stream)

    real_thread = threading.Thread
    started: list[str] = []

    def _counting_thread(*args: object, **kwargs: object) -> threading.Thread:
        started.append(str(kwargs.get("name", "")))
        return real_thread(*args, **kwargs)  # type: ignore[arg-type]

    with patch("services.virtual_drive.threading.Thread", _counting_thread):
        svc._op_read({"path": "/f.bin", "offset": 0, "length": 3}, b"")

    assert started.count("vdrive-read-watchdog") == 1


# ── Failure-logging tests ─────────────────────────────────────────────────────
#
# VirtualDrive.exe maps every error string it does not recognise to
# STATUS_IO_DEVICE_ERROR, which Explorer shows as a bare 0x8007045D. The log is
# the ONLY place the real reason survives, so these pin it down.


def test_failed_op_is_logged_with_op_and_path(caplog) -> None:
    """A handled failure logs a WARNING naming the op and the path."""
    svc = _service_with_streams()

    with caplog.at_level(logging.WARNING, logger="services.virtual_drive"):
        _serve_one(svc, {"op": "write", "path": "/Download/big.zip"})

    assert "write" in caplog.text
    assert "/Download/big.zip" in caplog.text
    assert "no_write_session" in caplog.text


def test_op_raising_is_logged_with_traceback(caplog) -> None:
    """An op that raises logs the exception rather than swallowing it.

    The reason is otherwise formatted into the drive_error signal and flattened
    into the response, both of which lose it.
    """
    svc = _service_with_streams()
    svc._dispatch = MagicMock(side_effect=RuntimeError("stream is closed"))

    with caplog.at_level(logging.WARNING, logger="services.virtual_drive"):
        _serve_one(svc, {"op": "write", "path": "/Download/big.zip"})

    assert "stream is closed" in caplog.text
    assert "RuntimeError" in caplog.text  # exc_info=True attached the traceback


def test_successful_op_logs_no_warning(caplog) -> None:
    """A healthy op must not add WARNING noise to the log."""
    svc = _service_with_streams()

    with caplog.at_level(logging.WARNING, logger="services.virtual_drive"):
        _serve_one(svc, {"op": "write_close", "path": "/Download/big.zip"})

    assert caplog.text == ""


# ── Directory-listing cache tests ─────────────────────────────────────────────
#
# WinFsp enumerates a directory one page at a time, but Android answers with the
# whole listing. Without a cache each page cost a full enumeration over TauSync.
# ``connect.side_effect`` is a finite list, so an unexpected extra fetch also
# surfaces as StopIteration — but assert call_count explicitly so a regression
# names itself.


def _listing_stream(names: tuple[str, ...], dir_mtime_ms: int = 111) -> _FakeStream:
    """A stream canned with Android's ``list_full`` response for *names*."""
    return _FakeStream(json.dumps({
        "ok": True,
        "dir_mtime_ms": dir_mtime_ms,
        "entries": [
            {"name": n, "is_dir": False, "size": 0, "mtime_ms": 0} for n in names
        ],
    }).encode("utf-8"))


def test_list_page_second_page_served_from_cache() -> None:
    """Paging through one directory costs exactly one fetch from the phone.

    This is the headline regression: ``_op_list_page`` used to call
    ``_fetch_listing_full`` on every page, so an N-entry folder paid
    ceil(N / limit) complete enumerations.
    """
    svc = _service_with_streams(_listing_stream(("a", "b", "c")))

    first, _ = svc._op_list_page({"path": "/D", "after": None, "limit": 2}, b"")
    second, _ = svc._op_list_page({"path": "/D", "after": "b", "limit": 2}, b"")

    assert [e["name"] for e in first["entries"]] == ["a", "b"]
    assert first["has_more"] is True
    assert [e["name"] for e in second["entries"]] == ["c"]
    assert second["has_more"] is False
    assert svc._connectivity.tau.connect.call_count == 1


def test_list_page_sorts_unsorted_android_entries() -> None:
    """Android lists via File.listFiles() (unordered); the cursor needs sorted names."""
    svc = _service_with_streams(_listing_stream(("c", "a", "b")))

    page, _ = svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")

    assert [e["name"] for e in page["entries"]] == ["a", "b", "c"]
    assert page["next_after"] == "c"


def test_list_page_different_paths_do_not_share_cache() -> None:
    """Each directory is cached under its own key."""
    svc = _service_with_streams(
        _listing_stream(("a",)), _listing_stream(("z",)))

    one, _ = svc._op_list_page({"path": "/A", "after": None, "limit": 10}, b"")
    two, _ = svc._op_list_page({"path": "/B", "after": None, "limit": 10}, b"")

    assert [e["name"] for e in one["entries"]] == ["a"]
    assert [e["name"] for e in two["entries"]] == ["z"]
    assert svc._connectivity.tau.connect.call_count == 2


def test_list_page_failure_errors_and_is_not_cached() -> None:
    """A failed listing must error, not render as an empty folder, and not cache.

    Returning ``{"ok": True, "entries": []}`` on a timeout made Explorer show the
    directory as empty instead of retrying.
    """
    failed = _FakeStream(json.dumps({"ok": False, "error": "not_found"}).encode())
    svc = _service_with_streams(failed, _listing_stream(("a",)))

    bad, _ = svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")
    assert bad["ok"] is False

    good, _ = svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")
    assert [e["name"] for e in good["entries"]] == ["a"]
    assert svc._connectivity.tau.connect.call_count == 2


def test_list_page_refetches_after_ttl_expiry() -> None:
    """An expired listing is refetched rather than served stale."""
    svc = _service_with_streams(
        _listing_stream(("a",)), _listing_stream(("a", "b")))
    svc._listings._ttl_s = 0.0

    svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")
    again, _ = svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")

    assert [e["name"] for e in again["entries"]] == ["a", "b"]
    assert svc._connectivity.tau.connect.call_count == 2


# ── Write-session offset tests ────────────────────────────────────────────────
#
# The write path is append-only end to end: one TauSync stream here, a sequential
# FileOutputStream on the phone. Neither can seek, so a chunk that doesn't
# continue where the previous one stopped has nowhere correct to go.


def test_sequential_writes_stream_through_in_order() -> None:
    """Explorer's sequential copy passes straight through, offsets advancing."""
    stream = _FakeStream()
    svc = _service_with_streams(stream)
    svc._op_write_open({"path": "/D/big.zip"}, b"")

    first, _ = svc._op_write({"path": "/D/big.zip", "offset": 0}, b"abc")
    second, _ = svc._op_write({"path": "/D/big.zip", "offset": 3}, b"de")

    assert first["ok"] is True
    assert second["ok"] is True
    # written[0] is the {"path": ...} header line write_open sends
    assert stream.written.endswith(b"abcde")
    assert svc._write_sessions.get("/D/big.zip").next_offset == 5


def test_out_of_order_write_is_refused_not_appended(caplog) -> None:
    """A seeking write must fail loudly instead of landing at the wrong offset.

    Appending it anyway is the silent-corruption case: the bytes go to the end of
    the temp file, the op reports success, and the finished file is wrong.
    """
    stream = _FakeStream()
    svc = _service_with_streams(stream)
    svc._op_write_open({"path": "/D/big.zip"}, b"")
    svc._op_write({"path": "/D/big.zip", "offset": 0}, b"abc")

    with caplog.at_level(logging.WARNING, logger="services.virtual_drive"):
        resp, _ = svc._op_write({"path": "/D/big.zip", "offset": 99}, b"XX")

    assert resp == {"ok": False, "error": "io_error"}
    assert not stream.written.endswith(b"XX")
    assert svc._write_sessions.get("/D/big.zip").next_offset == 3
    assert "out of order" in caplog.text


def test_write_without_offset_is_accepted() -> None:
    """An offset-less write (older VirtualDrive.exe) still streams through."""
    stream = _FakeStream()
    svc = _service_with_streams(stream)
    svc._op_write_open({"path": "/D/big.zip"}, b"")

    resp, _ = svc._op_write({"path": "/D/big.zip"}, b"abc")

    assert resp["ok"] is True
    assert stream.written.endswith(b"abc")


def test_write_open_restarts_the_offset_counter() -> None:
    """A second write session for the same path starts counting from zero again."""
    svc = _service_with_streams(_FakeStream(), _FakeStream())
    svc._op_write_open({"path": "/D/big.zip"}, b"")
    svc._op_write({"path": "/D/big.zip", "offset": 0}, b"abc")

    svc._op_write_open({"path": "/D/big.zip"}, b"")
    resp, _ = svc._op_write({"path": "/D/big.zip", "offset": 0}, b"z")

    assert resp["ok"] is True


def test_write_close_invalidates_parent_listing() -> None:
    """Finalizing a write makes the parent listing stale (size/mtime changed)."""
    svc = _service_with_streams(
        _listing_stream(("a",)), _listing_stream(("a", "new.txt")))

    svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")
    svc._op_write_close({"path": "/D/new.txt"}, b"")
    after, _ = svc._op_list_page({"path": "/D", "after": None, "limit": 10}, b"")

    assert [e["name"] for e in after["entries"]] == ["a", "new.txt"]
    assert svc._connectivity.tau.connect.call_count == 2


def test_delete_of_directory_drops_cached_subtree() -> None:
    """Deleting a directory orphans every listing beneath it."""
    svc = _service_with_streams(
        _listing_stream(("x",)),                                  # warm /A/B
        _FakeStream(json.dumps({"ok": True}).encode()),           # the delete op
        _listing_stream(("y",)),                                  # forced refetch
    )

    svc._op_list_page({"path": "/A/B", "after": None, "limit": 10}, b"")
    assert "/A/B" in svc._listings

    svc._op_delete({"path": "/A"}, b"")
    assert "/A/B" not in svc._listings

    again, _ = svc._op_list_page({"path": "/A/B", "after": None, "limit": 10}, b"")
    assert [e["name"] for e in again["entries"]] == ["y"]
