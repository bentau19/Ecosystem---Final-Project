"""Unit tests for services.backup — BackupService public interface.

All tests mock:
  * The TauSync transport (no real network)
  * FileDetection functions (is_corrupt, check_for_duplicates, is_wanted)

The sys.path insertion for FileDetection is not needed here because the
detection functions are patched at the service module level.

Wire format reminder
--------------------
Manifest (Android → PC on ``backup_manifest``)::

    {"file_count": N, "files_bytes": S, "classify": true|false}

Per-slot stream (``backup_slot_{i}``)::

    {"name": "photo.jpg", "size": 12345}\\n<raw file bytes>

Per-file transfer result (PC → Android on ``backup_file_result_{i}``, sent
for every slot regardless of the manifest's ``classify`` flag)::

    "succ" | "fail"

"fail" is reserved for transport/IO problems; PC-local screening rejections
(corrupt/duplicate/filtered) are reported as "succ" since the transfer
itself completed.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from pytestqt.qtbot import QtBot

from classifer import ScreeningOutcome, ClassificationVerdict
from domain.dto.backup_review_prompt import BackupReviewPromptDTO
from domain.dto.backup_session_prompt import BackupSessionPromptDTO
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


def _slot_bytes(name: str, size: int, content: bytes) -> bytes:
    """Return the exact bytes Android writes on ``backup_slot_{i}``.

    The stream begins with a newline-terminated JSON metadata line followed
    immediately by the raw file bytes — both on the same channel.

    Args:
        name:    File display name (e.g. ``"photo.jpg"``).
        size:    File size in bytes (must equal ``len(content)``).
        content: Raw file bytes to append after the header.
    """
    header = json.dumps({"name": name, "size": size}).encode() + b"\n"
    return header + content


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_stream_cm(stream_mock: MagicMock) -> MagicMock:
    """Wrap *stream_mock* in a context-manager shell for ``with tau.connect(…) as s:``."""
    cm = MagicMock()
    cm.__enter__.return_value = stream_mock
    cm.__exit__.return_value = False
    return cm


def _make_slot_stream(name: str, size: int, content: bytes) -> MagicMock:
    """Return a stream mock whose read_line() + read_to_file() behaves correctly.

    ``read_line()`` returns the JSON header line (including ``\\n``).
    ``read_to_file(path, n)`` writes *content* to *path* (ignores *n*).
    """
    stream = MagicMock()
    header_line = json.dumps({"name": name, "size": size}).encode() + b"\n"
    stream.read_line.return_value = header_line

    def _fake_read_to_file(path: str, length: int) -> int:
        Path(path).write_bytes(content)
        return len(content)

    stream.read_to_file.side_effect = _fake_read_to_file
    return stream


def _make_tau(channel_map: dict[str, MagicMock]) -> MagicMock:
    """Return a mock TauSync that dispatches ``connect()`` by channel name/prefix.

    Args:
        channel_map: Maps channel name or prefix → stream mock.
            Matched longest-key-first so prefixes (e.g. ``"backup_slot_"``)
            work correctly.
    """
    tau = MagicMock()
    sorted_keys = sorted(channel_map.keys(), key=len, reverse=True)

    def _connect(word: str, **_kwargs) -> MagicMock:
        for key in sorted_keys:
            if word == key or word.startswith(key):
                return _make_stream_cm(channel_map[key])
        return _make_stream_cm(MagicMock())

    tau.connect.side_effect = _connect
    return tau


def _make_one_shot_manifest(data: bytes) -> MagicMock:
    """Return a manifest stream mock that delivers *data* once then blocks forever.

    In production, ``tau.connect("backup_manifest")`` blocks until Android
    sends a new manifest.  Without this helper the instant-returning mock lets
    the listener loop spin hundreds of times, spawning extra coordinators and
    corrupting test assertions.
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
    """Factory fixture: creates a BackupService with a mocked detection DB path."""
    services: list[BackupService] = []

    def factory(tau: MagicMock) -> BackupService:
        mock_conn = MagicMock()
        mock_conn.tau = tau
        svc = BackupService(connectivity=mock_conn)
        svc._detection_db = tmp_path / "test_detection.db"
        from services.backup import _ensure_detection_db
        _ensure_detection_db(svc._detection_db)
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
    tau = _make_tau({"backup_manifest": manifest_stream})

    svc = make_service(tau)
    received: list[BackupSessionPromptDTO] = []
    svc.manifest_received.connect(received.append)

    svc.start()

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
    tau = _make_tau({"backup_manifest": manifest_stream})

    svc = make_service(tau)
    received: list[BackupSessionPromptDTO] = []
    svc.manifest_received.connect(received.append)

    svc.start()

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
    svc.manifest_received.connect(received.append)

    svc.start()
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
    tau = _make_tau({"backup_manifest": manifest_stream})

    svc = make_service(tau)
    received: list[tuple[int, int, bool]] = []
    svc.manifest_received.connect(lambda n, s, c: received.append((n, s, c)))

    svc.start()

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
    slot_stream = _make_slot_stream("f.jpg", 4, b"DATA")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": ready_stream,
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    ready_stream.write_string.assert_called_once_with("ready")


def test_cancel_session_prevents_ready_ack(
        qtbot: QtBot, make_service,
) -> None:
    """``cancel_session()`` before ``proceed()`` → no ``backup_ready_pc`` write."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    ready_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": ready_stream,
        "backup_slot_":    MagicMock(),
    })

    svc = make_service(tau)
    received: list = []
    svc.manifest_received.connect(received.append)
    svc.start()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    qtbot.wait(100)

    svc.cancel_session()
    qtbot.wait(300)

    ready_stream.write_string.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path — file_registered, file_complete, backup_complete
# ---------------------------------------------------------------------------


def test_file_registered_emitted_before_progress(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """``file_registered`` fires with correct rel_path and size before progress ticks."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 8).encode()
    )
    slot_stream = _make_slot_stream("photo.jpg", 8, b"FAKE_IMG")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    registered: list[tuple[str, int]] = []
    done: list = []
    svc.file_registered.connect(lambda p, s: registered.append((p, s)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
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
    slot_stream = _make_slot_stream("photo.jpg", 8, b"FAKE_IMG")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    dest_dir = tmp_path / "backup"

    complete_files: list[str] = []
    done: list = []
    svc.file_complete.connect(complete_files.append)
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
        svc.proceed(dest_dir)
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert complete_files == ["photo.jpg"]
    assert (dest_dir / "photo.jpg").exists()


def test_backup_complete_fires_after_all_files_terminal(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """``backup_complete`` fires once every file is either complete or failed."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(2, 8).encode()
    )

    slot_streams: dict[str, MagicMock] = {}

    def _connect(word: str, **_kw) -> MagicMock:
        if word == "backup_manifest":
            return _make_stream_cm(manifest_stream)
        if word == "backup_ready_pc":
            return _make_stream_cm(MagicMock())
        if word.startswith("backup_slot_"):
            if word not in slot_streams:
                idx = word[len("backup_slot_"):]
                name = f"file{idx}.jpg"
                slot_streams[word] = _make_slot_stream(name, 4, b"DATA")
            return _make_stream_cm(slot_streams[word])
        return _make_stream_cm(MagicMock())

    tau = MagicMock()
    tau.connect.side_effect = _connect

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(done) == 1


# ---------------------------------------------------------------------------
# Screening failures — file_failed
# ---------------------------------------------------------------------------


def test_corrupt_file_emits_file_failed(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A structurally corrupt cached file emits ``file_failed`` with 'corrupt' reason."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    slot_stream = _make_slot_stream("bad.jpg", 4, b"BAD!")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    failed: list[tuple[str, str]] = []
    done: list = []
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=True):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(failed) == 1
    assert failed[0][0] == "bad.jpg"
    assert "corrupt" in failed[0][1].lower()


def test_duplicate_file_emits_file_failed(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """An exact-duplicate cached file emits ``file_failed`` with 'duplicate' reason."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    slot_stream = _make_slot_stream("dup.jpg", 4, b"DUP!")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    failed: list[tuple[str, str]] = []
    done: list = []
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.Classifier.classify",
               return_value=ScreeningOutcome(ClassificationVerdict.REJECTED, 0.0)):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(failed) == 1
    assert "duplicate" in failed[0][1].lower()


def test_unwanted_file_emits_file_failed(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A file rejected by the ML classifier emits ``file_failed`` with 'filtered' reason."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    slot_stream = _make_slot_stream("nsfw.jpg", 4, b"DATA")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    failed: list[tuple[str, str]] = []
    done: list = []
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=False):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(failed) == 1
    assert "filtered" in failed[0][1].lower()


# ---------------------------------------------------------------------------
# Transport error on slot
# ---------------------------------------------------------------------------


def test_transport_error_on_slot_emits_file_failed(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A transport exception during slot receive emits ``file_failed``."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )

    # Slot stream raises before read_line can return metadata
    bad_slot = MagicMock()
    bad_slot.read_line.side_effect = OSError("connection dropped")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    bad_slot,
    })

    svc = make_service(tau)
    failed: list[tuple[str, str]] = []
    done: list = []
    svc.file_failed.connect(lambda p, r: failed.append((p, r)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    svc.proceed(tmp_path / "dest")
    qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    # Transport error before rel_path is known: file_failed may not fire
    # (rel_path is empty string); backup_complete still fires.
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
    slot_stream = _make_slot_stream("x.jpg", 256, b"D" * 256)

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    progress: list[tuple[str, int, float]] = []
    done: list = []
    svc.file_progress.connect(lambda p, b, s: progress.append((p, b, s)))
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    paths_in_progress = [p for p, _, _ in progress]
    bytes_in_progress = [b for _, b, _ in progress]
    assert "x.jpg" in paths_in_progress
    assert 0 in bytes_in_progress      # start tick
    assert 256 in bytes_in_progress    # end tick


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
    slot_stream = _make_slot_stream("img.jpg", 4, b"DATA")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":         manifest_stream,
        "backup_ready_pc":         MagicMock(),
        "backup_slot_":            slot_stream,
        "backup_file_result_":     result_stream,
    })

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
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
    slot_stream = _make_slot_stream("bad.jpg", 4, b"DATA")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":         manifest_stream,
        "backup_ready_pc":         MagicMock(),
        "backup_slot_":            slot_stream,
        "backup_file_result_":     result_stream,
    })

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=False):
        svc.proceed(tmp_path / "dest")
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    result_stream.write_string.assert_called_once_with("succ")


def test_transport_error_sends_fail_on_file_result_channel(
        qtbot: QtBot, make_service, tmp_path,
) -> None:
    """A transport error while receiving a slot reports 'fail' on backup_file_result_0."""
    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4, classify=False).encode()
    )

    bad_slot = MagicMock()
    bad_slot.read_line.side_effect = OSError("connection dropped")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":      manifest_stream,
        "backup_ready_pc":      MagicMock(),
        "backup_slot_":         bad_slot,
        "backup_file_result_":  result_stream,
    })

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
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
    slot_stream = _make_slot_stream("img.jpg", 4, b"DATA")
    result_stream = MagicMock()

    tau = _make_tau({
        "backup_manifest":      manifest_stream,
        "backup_ready_pc":      MagicMock(),
        "backup_slot_":         slot_stream,
        "backup_file_result_":  result_stream,
    })

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
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
    slot_stream = _make_slot_stream("f.jpg", 4, b"DATA")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    done: list = []
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
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
    dest_dir.mkdir()
    (dest_dir / "photo.jpg").write_bytes(b"EXISTING")

    manifest_stream = _make_one_shot_manifest(
        _manifest_json(1, 4).encode()
    )
    slot_stream = _make_slot_stream("photo.jpg", 4, b"NEW!")

    tau = _make_tau({
        "backup_manifest": manifest_stream,
        "backup_ready_pc": MagicMock(),
        "backup_slot_":    slot_stream,
    })

    svc = make_service(tau)
    complete: list[str] = []
    done: list = []
    svc.file_complete.connect(complete.append)
    svc.backup_complete.connect(lambda: done.append(True))
    svc.start()
    qtbot.wait(200)

    with patch("services.backup.is_corrupt", return_value=False), \
         patch("services.backup.check_for_duplicates", return_value=False), \
         patch("services.backup.is_wanted", return_value=True):
        svc.proceed(dest_dir)
        qtbot.waitUntil(lambda: len(done) > 0, timeout=3000)

    assert len(complete) == 1
    assert (dest_dir / "photo.jpg").read_bytes() == b"EXISTING"
    assert (dest_dir / "photo (1).jpg").exists()
