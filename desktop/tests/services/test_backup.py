"""Unit tests for services.backup — BackupService public interface.

All tests mock:
  * The TauSync transport (no real network)
  * Classifier.classify (replaces the three-stage screening pipeline)

Wire format reminder
--------------------
Manifest (Android → PC on ``backup_manifest``)::

    {"file_count": N, "files_bytes": S, "classify": true|false}

Per-file metadata (Android → PC on ``backup_slot_meta_{i}``)::

    {"name": "photo.jpg", "size": 12345}   (compact JSON — no newline delimiter needed)

Per-file bytes (Android → PC on ``backup_slot_data_{i}``)::

    [raw file bytes — exactly size bytes]

Per-file transfer result (PC → Android on ``backup_file_result_{i}``, sent
for every slot regardless of the manifest's ``classify`` flag)::

    "succ" | "fail"

"fail" is reserved for transport/IO problems; PC-local screening rejections
(corrupt/duplicate/filtered) are reported as "succ" since the transfer
itself completed.  The corresponding signal is ``file_skipped``, not
``file_failed`` — the latter is only emitted for transport/IO errors.

Entry point change
------------------
``BackupService.start()`` now only sets the ``_is_running`` flag.  The
manifest listener is driven by ``receive_manifest()`` (called by
``PhoneRequestService`` when it sees ``backup_manifest`` in
``get_peer_waiting_words()``).  All tests therefore call
``svc.receive_manifest()`` right after ``svc.start()``.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from classifer import Classifier, ClassificationVerdict
from domain.dto.backup_session_prompt import BackupSessionPromptDTO
from domain.enums.backup_channels import BackupChannels
from image_classifer import ClassificationResult
from services.backup import BackupService


# ---------------------------------------------------------------------------
# Wire-format helpers
# ---------------------------------------------------------------------------


def _manifest_json(
        file_count: int,
        files_bytes: int,
        classify: bool = True,
) -> str:
    """Return the JSON string Android writes on ``backup_manifest``.

    Args:
        file_count:  Number of files in the session.
        files_bytes: Total combined byte size of all files.
        classify:    Whether the PC should send per-file classify results.
    """
    return json.dumps({
        "file_count":  file_count,
        "files_bytes": files_bytes,
        "classify":    classify,
    })


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_stream_cm(stream_mock: MagicMock) -> MagicMock:
    """Wrap *stream_mock* in a context-manager shell for ``with tau.connect(…) as s:``."""
    cm = MagicMock()
    cm.__enter__.return_value = stream_mock
    cm.__exit__.return_value = False
    return cm


def _make_meta_stream(name: str, size: int, mtime: int = 0) -> MagicMock:
    """Return a stream mock for ``backup_slot_meta_N``.

    ``read_line()`` returns a newline-terminated JSON header that
    :meth:`~services.backup.BackupService._get_file_metadata` can parse.

    Args:
        name:  File display name (e.g. ``"photo.jpg"``).
        size:  File size in bytes.
        mtime: Last-modified time in milliseconds since epoch.  Defaults to
               ``0`` (epoch), which maps to ``photos/1970/01-January/`` for
               all-media backups.
    """
    stream = MagicMock()
    header_line = json.dumps({"name": name, "size": size, "mtime": mtime}).encode() + b"\n"
    stream.read_line.return_value = header_line
    return stream


def _make_data_stream(content: bytes) -> MagicMock:
    """Return a stream mock for ``backup_slot_data_N``.

    ``read(n)`` returns successive chunks of *content* then returns ``b""``
    (EOF), matching the chunk-loop in
    :meth:`~services.backup.BackupService._download_file_to_cache`.

    Args:
        content: Raw file bytes to deliver.
    """
    stream = MagicMock()
    remaining = bytearray(content)

    def _fake_read(n: int) -> bytes:
        chunk = bytes(remaining[:n])
        del remaining[:n]
        return chunk

    stream.read.side_effect = _fake_read
    return stream


def _make_tau(channel_map: dict[str, MagicMock], file_count: int = 1) -> MagicMock:
    """Return a mock TauSync that dispatches ``connect()`` by channel name/prefix.

    Also configures ``get_peer_waiting_words()`` to return the concrete
    ``backup_slot_meta_{i}`` channel names so that ``_get_files`` can
    discover and spawn all *file_count* slot threads.

    Args:
        channel_map: Maps channel name or prefix → stream mock.
            Matched longest-key-first so prefixes (e.g. ``"backup_slot_meta_"``)
            work correctly.
        file_count: Number of files in the session.  Controls how many
            ``backup_slot_meta_{i}`` names are returned by
            ``get_peer_waiting_words``.
    """
    tau = MagicMock()
    sorted_keys = sorted(channel_map.keys(), key=len, reverse=True)

    def _connect(word: str, **_kwargs) -> MagicMock:
        for key in sorted_keys:
            if word == key or word.startswith(key):
                return _make_stream_cm(channel_map[key])
        return _make_stream_cm(MagicMock())

    tau.connect.side_effect = _connect

    # Return concrete meta-slot channel names so _get_files discovers all slots.
    # The service de-duplicates via spawned_channels, so returning all at once is safe.
    tau.get_peer_waiting_words.return_value = [
        f"{BackupChannels.BACKUP_FILE_META_SLOT}{i}" for i in range(file_count)
    ]
    return tau


def _make_one_shot_manifest(data: bytes) -> MagicMock:
    """Return a manifest stream mock that delivers *data* once then blocks forever.

    In production, ``tau.connect("backup_manifest")`` blocks until Android
    sends a new manifest.  Without this helper the instant-returning mock lets
    the listener loop spin hundreds of times, spawning extra coordinators and
    corrupting test assertions.

    Args:
        data: Raw manifest bytes to deliver on the first ``read_all()`` call.
    """
    _delivered = threading.Event()
    stream = MagicMock()

    def _read_all() -> bytes:
        if not _delivered.is_set():
            _delivered.set()
            return data
        threading.Event().wait()   # block forever — daemon thread is killed at test end
        return b""

    stream.read_all.side_effect = _read_all
    return stream


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_service(tmp_path):
    """Factory fixture: creates a BackupService with a mocked connectivity."""
    services: list[BackupService] = []

    def factory(tau: MagicMock) -> BackupService:
        mock_conn = MagicMock()
        mock_conn.tau = tau
        svc = BackupService(connectivity=mock_conn)
        services.append(svc)
        return svc

    yield factory

    for svc in services:
        svc.stop()


# ---------------------------------------------------------------------------
# manifest_received signal
# ---------------------------------------------------------------------------


def test_manifest_received_emits_prompt_dto(
        qtbot: QtBot, make_service,
) -> None:
    """``manifest_received`` fires with a correctly populated BackupSessionPromptDTO."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(file_count=2, files_bytes=1536, classify=True).encode()
    )
    tau = _make_tau({"backup_manifest": manifest_stream}, file_count=2)

    svc = make_service(tau)
    received: list[BackupSessionPromptDTO] = []
    svc.manifest_received.connect(
        lambda n, s, c, ss: received.append(BackupSessionPromptDTO(n, s, c, ss))
    )

    svc.start()
    svc.receive_manifest()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    assert received[0].file_count == 2
    assert received[0].total_size_bytes == 1536
    assert received[0].classify is True


def test_manifest_received_classify_false(
        qtbot: QtBot, make_service,
) -> None:
    """``classify=false`` in the manifest is forwarded correctly."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(file_count=1, files_bytes=512, classify=False).encode()
    )
    tau = _make_tau({"backup_manifest": manifest_stream}, file_count=1)

    svc = make_service(tau)
    received: list[BackupSessionPromptDTO] = []
    svc.manifest_received.connect(
        lambda n, s, c, ss: received.append(BackupSessionPromptDTO(n, s, c, ss))
    )

    svc.start()
    svc.receive_manifest()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    assert received[0].classify is False


def test_manifest_received_skipped_on_bad_json(
        qtbot: QtBot, make_service,
) -> None:
    """A malformed manifest is silently skipped — service does not crash or emit."""
    manifest_stream = MagicMock()
    manifest_stream.read_all.return_value = b"NOT_JSON{"

    tau = _make_tau({"backup_manifest": manifest_stream})
    svc = make_service(tau)

    received: list = []
    svc.manifest_received.connect(lambda n, s, c, ss: received.append((n, s, c, ss)))

    svc.start()
    svc.receive_manifest()
    qtbot.wait(300)
    assert received == []


def test_manifest_received_large_total_bytes_no_overflow(
        qtbot: QtBot, make_service,
) -> None:
    """``manifest_received`` must not overflow when total_size_bytes > INT32_MAX.

    Regression for a libshiboken OverflowError that fired when Android reported
    a backup session larger than ~2 GB (the signed int32 ceiling).  The signal
    parameter was widened to ``qint64`` to fix this.
    """
    large_size = 6_000_000_000  # ~5.6 GB — exceeds signed int32 max (2_147_483_647)
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(file_count=3, files_bytes=large_size, classify=False).encode()
    )
    tau = _make_tau({"backup_manifest": manifest_stream}, file_count=3)

    svc = make_service(tau)
    received: list[tuple[int, int, bool]] = []
    svc.manifest_received.connect(lambda n, s, c, ss: received.append((n, s, c)))

    svc.start()
    svc.receive_manifest()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    file_count, total_bytes, classify = received[0]
    assert file_count == 3
    assert total_bytes == large_size  # must survive the Qt int32 boundary
    assert classify is False


# ---------------------------------------------------------------------------
# Dest handshake — proceed / cancel_session
# ---------------------------------------------------------------------------


def test_proceed_sends_ready_ack(qtbot: QtBot, make_service, tmp_path) -> None:
    """After ``proceed()`` the service writes ``"ready"`` on ``backup_ready_pc``."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    ready_stream = MagicMock()
    meta_stream = _make_meta_stream("f.jpg", 4)
    data_stream = _make_data_stream(b"DATA")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   ready_stream,
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    ready_stream.write_string.assert_called_once_with("ready")


def test_cancel_session_prevents_ready_ack(
        qtbot: QtBot, make_service,
) -> None:
    """``cancel_session()`` before ``proceed()`` sends ``"reject"`` (not ``"ready"``) on ``backup_ready_pc``.

    The service must unblock Android immediately so it doesn't wait 120 s for a
    ready ack that will never come.  The rejection token tells Android to abort
    the current session cleanly rather than treating the timeout as a network error.
    """
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    ready_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   ready_stream,
        "backup_slot_meta_": MagicMock(),
        "backup_slot_data_": MagicMock(),
    }, file_count=1)

    svc = make_service(tau)
    received: list = []
    svc.manifest_received.connect(lambda n, s, c, ss: received.append((n, s, c, ss)))
    svc.start()
    svc.receive_manifest()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    qtbot.wait(100)

    svc.cancel_session()
    qtbot.wait(300)

    # "reject" must be sent so Android's waitForPcReady() unblocks immediately.
    ready_stream.write_string.assert_called_once_with("reject")
    # "ready" must never be written — the session was cancelled before proceed().
    assert all(
        call.args != ("ready",)
        for call in ready_stream.write_string.call_args_list
    )


# ---------------------------------------------------------------------------
# Happy path — file_registered, file_complete, backup_complete
# ---------------------------------------------------------------------------


def test_file_registered_emitted_before_progress(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """``file_registered`` fires with correct name and size before progress ticks."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 8).encode()
    )
    meta_stream = _make_meta_stream("photo.jpg", 8)
    data_stream = _make_data_stream(b"FAKE_IMG")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    registered: list[tuple[str, int]] = []
    done: list = []
    svc.file_registered.connect(lambda p, s, orig_s: registered.append((p, s)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(registered) == 1
    assert registered[0] == ("photo.jpg", 8)


def test_clean_file_emits_file_complete_and_is_saved(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A file that passes all screening is copied to dest_dir and ``file_complete`` fires."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 8).encode()
    )
    meta_stream = _make_meta_stream("photo.jpg", 8)
    data_stream = _make_data_stream(b"FAKE_IMG")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    dest_dir = tmp_path / "backup"

    complete_files: list[str] = []
    done: list = []
    svc.file_complete.connect(lambda name, path: complete_files.append(name))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(dest_dir)
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert complete_files == ["photo.jpg"]
    # All-media backup (no rel_path) → organized into photos/{year}/{MM-MonthName}/
    # mtime defaults to 0 (epoch 1970-01-01) in the test meta stream.
    assert (dest_dir / "photos" / "1970" / "01-January" / "photo.jpg").exists()


def test_backup_complete_fires_after_all_files_terminal(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """``backup_complete`` fires once every file is either complete or failed."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(2, 8).encode()
    )

    meta_streams: dict[str, MagicMock] = {}
    data_streams: dict[str, MagicMock] = {}

    def _connect(word: str, **_kw) -> MagicMock:
        if word == "backup_manifest":
            return _make_stream_cm(manifest_stream)
        if word == "backup_ready_pc":
            return _make_stream_cm(MagicMock())
        if word.startswith(BackupChannels.BACKUP_FILE_META_SLOT):
            if word not in meta_streams:
                idx = word[len(BackupChannels.BACKUP_FILE_META_SLOT):]
                meta_streams[word] = _make_meta_stream(f"file{idx}.jpg", 4)
            return _make_stream_cm(meta_streams[word])
        if word.startswith(BackupChannels.BACKUP_FILE_DATA_SLOT):
            if word not in data_streams:
                data_streams[word] = _make_data_stream(b"DATA")
            return _make_stream_cm(data_streams[word])
        return _make_stream_cm(MagicMock())

    tau = MagicMock()
    tau.connect.side_effect = _connect
    tau.get_peer_waiting_words.return_value = [
        f"{BackupChannels.BACKUP_FILE_META_SLOT}0",
        f"{BackupChannels.BACKUP_FILE_META_SLOT}1",
    ]

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(done) == 1


# ---------------------------------------------------------------------------
# Screening failures — file_skipped (not file_failed)
#
# PC-local screening rejections (duplicate / filtered / confidently unwanted)
# are reported to Android as SUCCESS — the transfer completed; the file just
# wasn't kept locally.  The local signal is ``file_skipped``, not
# ``file_failed``.  The latter is reserved exclusively for transport/IO errors.
# ---------------------------------------------------------------------------


def test_corrupt_file_emits_file_skipped(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A file rejected by the classifier emits ``file_skipped`` (not ``file_failed``)."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    meta_stream = _make_meta_stream("bad.jpg", 4)
    data_stream = _make_data_stream(b"BAD!")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    skipped: list[str] = []
    failed: list = []
    done: list = []
    svc.file_skipped.connect(skipped.append)
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.REJECTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert skipped == ["bad.jpg"]
    assert failed == []


def test_duplicate_file_emits_file_skipped(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """An exact-duplicate cached file emits ``file_skipped`` (not ``file_failed``)."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    meta_stream = _make_meta_stream("dup.jpg", 4)
    data_stream = _make_data_stream(b"DUP!")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    skipped: list[str] = []
    failed: list = []
    done: list = []
    svc.file_skipped.connect(skipped.append)
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.REJECTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert skipped == ["dup.jpg"]
    assert failed == []


def test_unwanted_file_emits_file_skipped(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A file rejected by the ML classifier emits ``file_skipped`` (not ``file_failed``)."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    meta_stream = _make_meta_stream("nsfw.jpg", 4)
    data_stream = _make_data_stream(b"DATA")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    skipped: list[str] = []
    failed: list = []
    done: list = []
    svc.file_skipped.connect(skipped.append)
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.REJECTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert skipped == ["nsfw.jpg"]
    assert failed == []


# ---------------------------------------------------------------------------
# Transport error on slot
# ---------------------------------------------------------------------------


def test_transport_error_on_metadata_slot_emits_file_failed(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A transport exception while reading the metadata channel emits ``file_failed``."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )

    # Meta stream raises before read_line can return the header
    bad_meta = MagicMock()
    bad_meta.read_line.side_effect = OSError("connection dropped")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": bad_meta,
    }, file_count=1)

    svc = make_service(tau)
    failed: list[tuple[str, str]] = []
    done: list = []
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    svc.proceed(tmp_path / "dest")
    qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    # backup_complete still fires even when transport fails
    assert len(done) == 1


# ---------------------------------------------------------------------------
# file_progress — emitted at start and end of each slot
# ---------------------------------------------------------------------------


def test_file_progress_emitted_at_slot_start_and_end(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """``file_progress`` fires with bytes=0 at slot start and bytes=size at slot end."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 256).encode()
    )
    meta_stream = _make_meta_stream("x.jpg", 256)
    data_stream = _make_data_stream(b"D" * 256)

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    progress: list[tuple[str, int, float]] = []
    done: list = []
    svc.file_progress.connect(lambda p, b, s: progress.append((p, b, s)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    paths_in_progress = [p for p, _, _ in progress]
    bytes_in_progress = [b for _, b, _ in progress]
    assert "x.jpg" in paths_in_progress
    assert 0 in bytes_in_progress      # start tick (emitted after meta read)
    assert 256 in bytes_in_progress    # end tick (emitted during _copy_from_cache)


# ---------------------------------------------------------------------------
# Per-file transfer result — backup_file_result channel
# ---------------------------------------------------------------------------


def test_clean_file_sends_succ_on_file_result_channel(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A file that passes screening is reported as 'succ' on backup_file_result_0."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4, classify=True).encode()
    )
    meta_stream = _make_meta_stream("img.jpg", 4)
    data_stream = _make_data_stream(b"DATA")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":     manifest_stream,
        "backup_ready_pc":     MagicMock(),
        "backup_slot_meta_":   meta_stream,
        "backup_slot_data_":   data_stream,
        "backup_file_result_": result_stream,
    }, file_count=1)

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    result_stream.write_string.assert_called_once_with("succ")


def test_screened_out_file_still_sends_succ(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A file rejected by content screening still reports 'succ' — the transfer
    itself completed, only the PC's local copy was discarded."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4, classify=True).encode()
    )
    meta_stream = _make_meta_stream("bad.jpg", 4)
    data_stream = _make_data_stream(b"DATA")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":     manifest_stream,
        "backup_ready_pc":     MagicMock(),
        "backup_slot_meta_":   meta_stream,
        "backup_slot_data_":   data_stream,
        "backup_file_result_": result_stream,
    }, file_count=1)

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.REJECTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    result_stream.write_string.assert_called_once_with("succ")


def test_transport_error_sends_fail_on_file_result_channel(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A transport error on the metadata channel reports 'fail' on backup_file_result_0."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4, classify=False).encode()
    )

    bad_meta = MagicMock()
    bad_meta.read_line.side_effect = OSError("connection dropped")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":     manifest_stream,
        "backup_ready_pc":     MagicMock(),
        "backup_slot_meta_":   bad_meta,
        "backup_file_result_": result_stream,
    }, file_count=1)

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    svc.proceed(tmp_path / "dest")
    qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    result_stream.write_string.assert_called_once_with("fail")


def test_file_result_sent_regardless_of_classify_flag(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """``backup_file_result_{i}`` is written even when ``classify=False``."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4, classify=False).encode()
    )
    meta_stream = _make_meta_stream("img.jpg", 4)
    data_stream = _make_data_stream(b"DATA")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":     manifest_stream,
        "backup_ready_pc":     MagicMock(),
        "backup_slot_meta_":   meta_stream,
        "backup_slot_data_":   data_stream,
        "backup_file_result_": result_stream,
    }, file_count=1)

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    result_stream.write_string.assert_called_once_with("succ")


# ---------------------------------------------------------------------------
# Cache cleanup
# ---------------------------------------------------------------------------


def test_cache_dir_deleted_after_successful_backup(
        qtbot: QtBot, make_service, tmp_path, monkeypatch,
) -> None:
    """The temp cache directory is removed after a successful session."""
    import tempfile as _tempfile

    created_cache: list[str] = []
    original_mkdtemp = _tempfile.mkdtemp

    def _tracked_mkdtemp(**kwargs):
        path = original_mkdtemp(**kwargs)
        created_cache.append(path)
        return path

    monkeypatch.setattr("services.backup.tempfile.mkdtemp", _tracked_mkdtemp)

    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    meta_stream = _make_meta_stream("f.jpg", 4)
    data_stream = _make_data_stream(b"DATA")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    for cache in created_cache:
        assert not Path(cache).exists(), f"Cache dir {cache} was not cleaned up"


# ---------------------------------------------------------------------------
# Duplicate filename handling
# ---------------------------------------------------------------------------


def test_duplicate_dest_filename_gets_counter_suffix(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """If dest_dir already contains a file with the same name a counter is appended."""
    dest_dir = tmp_path / "dest"
    # All-media backups land in photos/{year}/{MM-MonthName}/ — mtime=0 (epoch)
    # maps to photos/1970/01-January/.  Pre-create the file there to force a
    # collision so the counter-suffix logic is exercised.
    organized_dir = dest_dir / "photos" / "1970" / "01-January"
    organized_dir.mkdir(parents=True)
    (organized_dir / "photo.jpg").write_bytes(b"EXISTING")

    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    meta_stream = _make_meta_stream("photo.jpg", 4)
    data_stream = _make_data_stream(b"NEW!")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    complete: list[str] = []
    done: list = []
    svc.file_complete.connect(lambda name, path: complete.append(name))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(dest_dir)
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(complete) == 1
    assert (organized_dir / "photo.jpg").read_bytes() == b"EXISTING"
    assert (organized_dir / "photo (1).jpg").exists()


# ---------------------------------------------------------------------------
# All-media organized subdirectory layout
# ---------------------------------------------------------------------------


def test_all_media_photo_organized_into_photos_subdir(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """All-media photos are saved under photos/{year}/{MM-MonthName}/.

    Uses noon local-time on the 15th of a month so the expected folder is
    stable across any UTC offset (no risk of the date rolling into an adjacent
    month due to timezone arithmetic).
    """
    import datetime as _dt

    mtime_ms = int(_dt.datetime(2024, 6, 15, 12, 0, 0).timestamp() * 1000)

    manifest_stream = _make_one_shot_manifest(_manifest_json(1, 8).encode())
    meta_stream = _make_meta_stream("IMG_001.jpg", 8, mtime=mtime_ms)
    data_stream = _make_data_stream(b"FAKE_IMG")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    dest_dir = tmp_path / "backup"
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(dest_dir)
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert (dest_dir / "photos" / "2024" / "06-June" / "IMG_001.jpg").exists()


def test_all_media_video_organized_into_videos_subdir(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """All-media videos are saved under videos/{year}/{MM-MonthName}/."""
    import datetime as _dt

    mtime_ms = int(_dt.datetime(2024, 6, 15, 12, 0, 0).timestamp() * 1000)

    manifest_stream = _make_one_shot_manifest(_manifest_json(1, 16).encode())
    meta_stream = _make_meta_stream("VID_001.mp4", 16, mtime=mtime_ms)
    data_stream = _make_data_stream(b"FAKE_VID_DATA___")

    tau = _make_tau({
        "backup_manifest":   manifest_stream,
        "backup_ready_pc":   MagicMock(),
        "backup_slot_meta_": meta_stream,
        "backup_slot_data_": data_stream,
    }, file_count=1)

    svc = make_service(tau)
    dest_dir = tmp_path / "backup"
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    svc.receive_manifest()
    qtbot.wait(200)

    with patch.object(Classifier, "classify",
                      return_value=ClassificationResult(ClassificationVerdict.ACCEPTED, 0.0)):
        svc.proceed(dest_dir)
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert (dest_dir / "videos" / "2024" / "06-June" / "VID_001.mp4").exists()
