"""Unit tests for VirtualDriveService._page_entries pagination.

Critical invariant: ``next_after`` is ALWAYS a string, never ``None``.

VirtualDrive.exe's C++ ``ReadDirectory`` reads this field with nlohmann
``j.value("next_after", "")``, which falls back to the default ONLY when the key
is absent. A present-but-``null`` value makes ``get<std::string>()`` throw
``type_error.302``; that exception escapes the WinFsp callback and terminates the
(un-rebuildable) binary, tearing the drive down with "the I/O operation has been
aborted" on every empty folder. So an empty/last page must serialise
``next_after`` as ``""`` — never ``None``.
"""

import json
from unittest.mock import MagicMock

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
        if n is None or n < 0:
            n = len(self._buf)
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
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
