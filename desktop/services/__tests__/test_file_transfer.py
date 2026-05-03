"""Unit tests for services.file_transfer — FileTransferService public interface."""

import json
import os
import threading
from unittest.mock import MagicMock

import pytest
from pytestqt.qtbot import QtBot

from domain.enums.file_transfer_channels import FileTransferChannels
from services.file_transfer import FileTransferService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stream_cm(stream_mock: MagicMock) -> MagicMock:
    """Wrap *stream_mock* in a context-manager shell.

    ``tau.connect(word)`` must be used as ``with tau.connect(...) as s:``,
    so the return value needs ``__enter__``/``__exit__`` in addition to the
    stream methods we want to assert on.

    Args:
        stream_mock: The :class:`~unittest.mock.MagicMock` that represents the
            open ``TauSyncStream``.

    Returns:
        A ``MagicMock`` whose ``__enter__`` yields *stream_mock* and whose
        ``__exit__`` is a no-op.
    """
    cm = MagicMock()
    cm.__enter__.return_value = stream_mock
    cm.__exit__.return_value = False
    return cm


def _make_tau(
    meta_stream: MagicMock,
    data_stream: MagicMock,
) -> MagicMock:
    """Return a mock ``TauSync`` that dispatches ``connect()`` by meeting-word.

    Args:
        meta_stream: Mock returned for ``FileTransferChannels.REGULAR_FILE_METADATA`` connects.
        data_stream: Mock returned for ``FileTransferChannels.REGULAR_FILE_DATA`` connects.

    Returns:
        A ``MagicMock`` whose ``connect`` side-effect routes to the correct
        stream mock based on the word argument.
    """
    tau = MagicMock()

    def _connect_side_effect(word: str) -> MagicMock:
        if word == FileTransferChannels.REGULAR_FILE_METADATA:
            return _make_stream_cm(meta_stream)
        return _make_stream_cm(data_stream)

    tau.connect.side_effect = _connect_side_effect
    return tau


def _make_service(tau: MagicMock) -> FileTransferService:
    """Construct a :class:`FileTransferService` backed by a mock transport.

    Args:
        tau: Mock :class:`~tausync_py.TauSync` instance to inject via a mock
            :class:`~services.connectivity.ConnectivityService`.

    Returns:
        A :class:`FileTransferService` ready for testing.
    """
    mock_connectivity = MagicMock()
    mock_connectivity.tau = tau
    return FileTransferService(connectivity=mock_connectivity)


# ---------------------------------------------------------------------------
# send_file — signal assertions
# ---------------------------------------------------------------------------


def test_send_file_emits_send_started_with_filename(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """``file_send_started`` carries the bare filename (not the full path)."""
    sample = tmp_path / "report.pdf"
    sample.write_bytes(b"PDF content")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = len(b"PDF content")

    svc = _make_service(_make_tau(meta_stream, data_stream))
    received: list[str] = []
    svc.file_send_started.connect(lambda name: received.append(name))

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == ["report.pdf"]


def test_send_file_emits_send_complete_with_correct_values(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """``file_send_complete`` carries ``(filename, total_bytes)``."""
    sample = tmp_path / "video.mp4"
    payload = b"x" * 512
    sample.write_bytes(payload)

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = len(payload)

    svc = _make_service(_make_tau(meta_stream, data_stream))
    received: list[tuple] = []
    svc.file_send_complete.connect(lambda name, n: received.append((name, n)))

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == [("video.mp4", 512)]


def test_send_file_emits_send_error_when_file_missing(qtbot: QtBot) -> None:
    """``file_send_error`` is emitted (not ``file_send_complete``) for missing files."""
    meta_stream = MagicMock()
    data_stream = MagicMock()
    svc = _make_service(_make_tau(meta_stream, data_stream))

    errors: list[str] = []
    complete: list = []
    svc.file_send_error.connect(lambda msg: errors.append(msg))
    svc.file_send_complete.connect(lambda *_: complete.append(True))

    svc.send_file("/nonexistent/path/missing.bin")

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert len(errors) == 1
    assert complete == []


def test_send_file_error_message_contains_path(qtbot: QtBot) -> None:
    """The ``file_send_error`` message names the missing file."""
    meta_stream = MagicMock()
    data_stream = MagicMock()
    svc = _make_service(_make_tau(meta_stream, data_stream))
    errors: list[str] = []
    svc.file_send_error.connect(lambda msg: errors.append(msg))

    svc.send_file("/no/such/file.txt")

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "/no/such/file.txt" in errors[0]


def test_send_file_does_not_emit_started_when_file_missing(qtbot: QtBot) -> None:
    """``file_send_started`` must not fire when the source file does not exist."""
    meta_stream = MagicMock()
    data_stream = MagicMock()
    svc = _make_service(_make_tau(meta_stream, data_stream))

    started: list = []
    errors: list[str] = []
    svc.file_send_started.connect(lambda _: started.append(True))
    svc.file_send_error.connect(lambda msg: errors.append(msg))

    svc.send_file("/ghost.bin")

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert started == []


# ---------------------------------------------------------------------------
# send_file — transport interaction
# ---------------------------------------------------------------------------


def test_send_file_opens_meta_channel_first(qtbot: QtBot, tmp_path) -> None:
    """``file_meta`` channel must be opened before ``file_data``."""
    sample = tmp_path / "img.png"
    sample.write_bytes(b"PNG")

    call_order: list[str] = []
    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 3

    tau = MagicMock()

    def _connect(word: str) -> MagicMock:
        call_order.append(word)
        if word == FileTransferChannels.REGULAR_FILE_METADATA:
            return _make_stream_cm(meta_stream)
        return _make_stream_cm(data_stream)

    tau.connect.side_effect = _connect
    svc = _make_service(tau)

    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    assert call_order == [FileTransferChannels.REGULAR_FILE_METADATA, FileTransferChannels.REGULAR_FILE_DATA]


def test_send_file_metadata_contains_correct_filename(qtbot: QtBot, tmp_path) -> None:
    """The JSON payload on ``file_meta`` must include the exact filename."""
    sample = tmp_path / "notes.txt"
    sample.write_text("hello")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 5

    svc = _make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    # Extract the JSON string passed to write_string
    written_json: str = meta_stream.write_string.call_args[0][0]
    meta: dict = json.loads(written_json)
    assert meta["name"] == "notes.txt"


def test_send_file_metadata_contains_correct_size(qtbot: QtBot, tmp_path) -> None:
    """The JSON payload on ``file_meta`` must include the exact file size in bytes."""
    sample = tmp_path / "data.bin"
    sample.write_bytes(b"\x00" * 2048)

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 2048

    svc = _make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    written_json: str = meta_stream.write_string.call_args[0][0]
    meta: dict = json.loads(written_json)
    assert meta["size"] == 2048


def test_send_file_flushes_meta_stream(qtbot: QtBot, tmp_path) -> None:
    """The meta stream must be explicitly flushed so the peer receives it promptly."""
    sample = tmp_path / "flush_test.txt"
    sample.write_text("hi")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 2

    svc = _make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    meta_stream.flush.assert_called_once()


def test_send_file_calls_write_file_on_data_stream(qtbot: QtBot, tmp_path) -> None:
    """The data stream must use ``write_file`` to send raw bytes."""
    sample = tmp_path / "archive.zip"
    sample.write_bytes(b"PK")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 2

    svc = _make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    data_stream.write_file.assert_called_once_with(str(sample))


def test_send_file_emits_error_when_transport_raises(qtbot: QtBot, tmp_path) -> None:
    """A transport exception must surface via ``file_send_error``, not propagate."""
    sample = tmp_path / "broken.bin"
    sample.write_bytes(b"data")

    meta_stream = MagicMock()
    meta_stream.write_string.side_effect = RuntimeError("connection lost")
    data_stream = MagicMock()

    svc = _make_service(_make_tau(meta_stream, data_stream))
    errors: list[str] = []
    svc.file_send_error.connect(lambda msg: errors.append(msg))

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "connection lost" in errors[0]


# ---------------------------------------------------------------------------
# receive_file — signal assertions
# ---------------------------------------------------------------------------


def _make_receive_tau(
    filename: str,
    file_size: int,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Build a mock ``TauSync`` pre-loaded with receive-side metadata.

    Args:
        filename: Filename the peer is "sending".
        file_size: Byte-count the peer is "sending".

    Returns:
        ``(tau, meta_stream, data_stream)`` so tests can assert on stream calls.
    """
    meta_payload = json.dumps({"name": filename, "size": file_size}).encode("utf-8")
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = meta_payload

    data_stream = MagicMock()
    # read_to_file writes to disk; mock it to be a no-op.
    data_stream.read_to_file.return_value = file_size

    tau = _make_tau(meta_stream, data_stream)
    return tau, meta_stream, data_stream


def test_receive_file_emits_receive_started_with_filename(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """``file_receive_started`` carries the filename from the peer's metadata."""
    tau, _, _ = _make_receive_tau("photo.jpg", 4096)
    svc = _make_service(tau)

    received: list[str] = []
    svc.file_receive_started.connect(lambda name: received.append(name))
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == ["photo.jpg"]


def test_receive_file_emits_receive_complete_with_filename_and_path(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """``file_receive_complete`` carries ``(filename, absolute_dest_path)``."""
    tau, _, _ = _make_receive_tau("music.mp3", 8192)
    svc = _make_service(tau)

    received: list[tuple] = []
    svc.file_receive_complete.connect(
        lambda name, path: received.append((name, path))
    )
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    name, path = received[0]
    assert name == "music.mp3"
    assert path == os.path.join(str(tmp_path), "music.mp3")


def test_receive_file_calls_read_to_file_with_correct_length(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """``read_to_file`` must be called with the byte-count from the metadata."""
    tau, _, data_stream = _make_receive_tau("doc.pdf", 3333)
    svc = _make_service(tau)

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    call_args = data_stream.read_to_file.call_args
    _, length = call_args[0]  # positional: (dest_path, length)
    assert length == 3333


def test_receive_file_saves_to_dest_dir(qtbot: QtBot, tmp_path) -> None:
    """The destination path passed to ``read_to_file`` must be inside *dest_dir*."""
    tau, _, data_stream = _make_receive_tau("backup.tar.gz", 1024)
    svc = _make_service(tau)

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    dest_path, _ = data_stream.read_to_file.call_args[0]
    assert dest_path.startswith(str(tmp_path))
    assert dest_path.endswith("backup.tar.gz")


def test_receive_file_creates_dest_dir_if_missing(qtbot: QtBot, tmp_path) -> None:
    """The destination directory is created automatically when it does not exist."""
    new_dir = str(tmp_path / "deep" / "nested" / "dir")
    tau, _, _ = _make_receive_tau("file.bin", 10)
    svc = _make_service(tau)

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(new_dir)

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    assert os.path.isdir(new_dir)


def test_receive_file_emits_error_on_bad_metadata(qtbot: QtBot, tmp_path) -> None:
    """Malformed JSON on the meta channel must surface via ``file_receive_error``."""
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = b"NOT_JSON{"
    data_stream = MagicMock()

    svc = _make_service(_make_tau(meta_stream, data_stream))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert len(errors) == 1


def test_receive_file_does_not_emit_complete_on_error(qtbot: QtBot, tmp_path) -> None:
    """``file_receive_complete`` must not fire when metadata parsing fails."""
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = b"{}"  # missing required keys
    data_stream = MagicMock()

    svc = _make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    errors: list[str] = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert complete == []


def test_receive_file_emits_error_when_transport_raises(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """A transport exception on the data channel must surface via ``file_receive_error``."""
    meta_payload = json.dumps({"name": "crash.bin", "size": 100}).encode("utf-8")
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = meta_payload

    data_stream = MagicMock()
    data_stream.read_to_file.side_effect = OSError("network dropped")

    svc = _make_service(_make_tau(meta_stream, data_stream))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_file(str(tmp_path))

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "network dropped" in errors[0]


# ---------------------------------------------------------------------------
# Live-transport access — the tau staleness design
# ---------------------------------------------------------------------------


def test_service_reads_tau_from_connectivity_at_call_time(
    qtbot: QtBot,
    tmp_path,
) -> None:
    """``connectivity.tau`` must be accessed at transfer time, not at construction.

    This verifies the fix for the staleness bug: if ``ConnectivityService``
    replaces ``_tau`` after ``ServicesManager`` was built, the
    ``FileTransferService`` must use the *new* transport, not the one it saw
    at construction.
    """
    sample = tmp_path / "staleness_test.bin"
    sample.write_bytes(b"hello")

    original_meta = MagicMock()
    original_data = MagicMock()
    original_tau = _make_tau(original_meta, original_data)

    new_meta = MagicMock()
    new_data = MagicMock()
    new_data.write_file.return_value = 5
    new_tau = _make_tau(new_meta, new_data)

    mock_connectivity = MagicMock()
    mock_connectivity.tau = original_tau  # tau at construction time
    svc = FileTransferService(connectivity=mock_connectivity)

    # Simulate a reconnect: ConnectivityService swaps out _tau.
    mock_connectivity.tau = new_tau

    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    # The NEW transport's streams were used, not the original ones.
    new_meta.write_string.assert_called_once()
    original_meta.write_string.assert_not_called()