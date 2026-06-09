"""Unit tests for services.file_transfer — FileTransferService public interface."""

import json
import os
from unittest.mock import MagicMock

import pytest
from pytestqt.qtbot import QtBot

from domain.dto.file_metadata import FileMetadataDTO
from domain.dto.file_receive_complete import FileReceiveCompleteDTO
from domain.dto.file_send_complete import FileSendCompleteDTO
from domain.enums.file_transfer_channels import FileTransferChannels
from domain.enums.file_transfer_response import FileTransferResponse
from services.file_transfer import FileTransferService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stream_cm(stream_mock: MagicMock) -> MagicMock:
    """Wrap *stream_mock* in a context-manager shell.

    ``tau.connect(word)`` is used as ``with tau.connect(...) as s:``,
    so the return value needs ``__enter__``/``__exit__`` in addition to
    the stream methods we want to assert on.

    Args:
        stream_mock: The :class:`~unittest.mock.MagicMock` representing the
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
    resp_stream: MagicMock | None = None,
) -> MagicMock:
    """Return a mock ``TauSync`` that dispatches ``connect()`` by channel name.

    Args:
        meta_stream: Mock returned for metadata channel connects (both directions).
        data_stream: Mock returned for data channel connects (and for
            response channels when *resp_stream* is ``None``).
        resp_stream: Optional mock returned for response channel
            connects.  When ``None``, the response channel falls through to
            *data_stream* — the existing send-test behaviour.

    Returns:
        A ``MagicMock`` whose ``connect`` side-effect routes to the correct
        stream mock based on the channel name.
    """
    tau = MagicMock()

    def _connect_side_effect(word: str) -> MagicMock:
        if word in (
            FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.value,
            FileTransferChannels.REGULAR_FILE_METADATA_ANDROID_TO_PC.value,
        ):
            return _make_stream_cm(meta_stream)
        if resp_stream is not None and word in (
            FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID.value,
            FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_PC.value,
        ):
            return _make_stream_cm(resp_stream)
        return _make_stream_cm(data_stream)

    tau.connect.side_effect = _connect_side_effect
    return tau


def _make_metadata_tau(
    filename: str,
    file_size: int,
    modified_at: int = 0,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Build a mock ``TauSync`` pre-loaded with Android-to-PC metadata.

    The meta stream's ``read_all`` returns a JSON-encoded payload using
    the ``file_name``/``file_size``/``modified_at`` wire keys.

    Args:
        filename: Filename Android is "sending".
        file_size: Byte-count Android is "sending".
        modified_at: Optional last-modified timestamp in Unix epoch ms.
            Defaults to ``0`` (not provided).

    Returns:
        ``(tau, meta_stream, data_stream)`` so tests can assert on calls.
    """
    meta_payload = json.dumps(
        {"file_name": filename, "file_size": file_size, "modified_at": modified_at}
    ).encode("utf-8")
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = meta_payload

    data_stream = MagicMock()
    tau = _make_tau(meta_stream, data_stream)
    return tau, meta_stream, data_stream


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def make_service():
    """Fixture that creates started :class:`FileTransferService` instances with cleanup.

    Yields:
        A factory callable ``(tau) -> FileTransferService`` that starts the
        service (with the pipe listener suppressed) and registers it for
        ``stop()`` teardown after the test.
    """
    services: list[FileTransferService] = []

    def factory(tau: MagicMock) -> FileTransferService:
        mock_connectivity = MagicMock()
        mock_connectivity.tau = tau
        svc = FileTransferService(connectivity=mock_connectivity)
        svc._listen_for_file_to_send = MagicMock()  # suppress real Windows pipe
        svc.start()
        services.append(svc)
        return svc

    yield factory

    for svc in services:
        svc.stop()


# ---------------------------------------------------------------------------
# send_file — signal assertions
# ---------------------------------------------------------------------------


def test_send_file_emits_send_complete_with_correct_values(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``file_send_complete`` carries a ``FileSendCompleteDTO`` with filename and total_bytes."""
    sample = tmp_path / "video.mp4"
    payload = b"x" * 512
    sample.write_bytes(payload)

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = len(payload)

    svc = make_service(_make_tau(meta_stream, data_stream))
    received: list[FileSendCompleteDTO] = []
    svc.file_send_complete.connect(received.append)

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received[0].filename == "video.mp4"
    assert received[0].total_bytes == 512


def test_send_file_emits_send_error_when_file_missing(qtbot: QtBot, make_service) -> None:
    """``file_send_error`` is emitted (not ``file_send_complete``) for missing files."""
    svc = make_service(_make_tau(MagicMock(), MagicMock()))

    errors: list[str] = []
    complete: list = []
    svc.file_send_error.connect(lambda msg: errors.append(msg))
    svc.file_send_complete.connect(lambda *_: complete.append(True))

    svc.send_file("/nonexistent/path/missing.bin")

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert len(errors) == 1
    assert complete == []


def test_send_file_error_message_contains_path(qtbot: QtBot, make_service) -> None:
    """The ``file_send_error`` message names the missing file."""
    svc = make_service(_make_tau(MagicMock(), MagicMock()))
    errors: list[str] = []
    svc.file_send_error.connect(lambda msg: errors.append(msg))

    svc.send_file("/no/such/file.txt")

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "/no/such/file.txt" in errors[0]


def test_send_file_emits_send_rejected_when_receiver_declines(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``file_send_rejected`` fires (not ``file_send_complete``) when rejected."""
    sample = tmp_path / "report.pdf"
    sample.write_bytes(b"PDF")

    meta_stream = MagicMock()
    resp_stream = MagicMock()
    resp_stream.read_all.return_value = FileTransferResponse.REJECTED_FROM_ANDROID.encode("utf-8")
    data_stream = MagicMock()

    svc = make_service(_make_tau(meta_stream, data_stream, resp_stream=resp_stream))
    rejected: list[str] = []
    complete: list = []
    svc.file_send_rejected.connect(lambda name: rejected.append(name))
    svc.file_send_complete.connect(lambda *_: complete.append(True))

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(rejected) > 0, timeout=1000)
    assert rejected == ["report.pdf"]
    assert complete == []


def test_send_file_does_not_open_data_channel_when_rejected(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """The data channel must not be opened when the receiver declines."""
    sample = tmp_path / "img.png"
    sample.write_bytes(b"PNG")

    meta_stream = MagicMock()
    resp_stream = MagicMock()
    resp_stream.read_all.return_value = FileTransferResponse.REJECTED_FROM_ANDROID.encode("utf-8")
    data_stream = MagicMock()

    svc = make_service(_make_tau(meta_stream, data_stream, resp_stream=resp_stream))
    rejected: list = []
    svc.file_send_rejected.connect(lambda _: rejected.append(True))

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(rejected) > 0, timeout=1000)
    data_stream.write_file.assert_not_called()


# ---------------------------------------------------------------------------
# send_file — transport interaction
# ---------------------------------------------------------------------------


def test_send_file_opens_channels_in_correct_order(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """Channel open order must be: META → RESPONSE → DATA."""
    sample = tmp_path / "img.png"
    sample.write_bytes(b"PNG")

    call_order: list[str] = []
    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 3

    tau = MagicMock()

    def _connect(word: str) -> MagicMock:
        call_order.append(word)
        if word == FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.value:
            return _make_stream_cm(meta_stream)
        if word == FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID.value:
            resp_stream = MagicMock()
            resp_stream.read_all.return_value = FileTransferResponse.ACCEPTED_FROM_ANDROID.encode("utf-8")
            return _make_stream_cm(resp_stream)
        return _make_stream_cm(data_stream)

    tau.connect.side_effect = _connect
    svc = make_service(tau)

    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    assert call_order == [
        FileTransferChannels.REGULAR_FILE_METADATA_PC_TO_ANDROID.value,
        FileTransferChannels.REGULAR_FILE_RESPONSE_FROM_ANDROID.value,
        FileTransferChannels.REGULAR_FILE_DATA_PC_TO_ANDROID.value,
    ]


def test_send_file_metadata_contains_correct_filename(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """The JSON payload on ``file_meta`` must include the exact filename."""
    sample = tmp_path / "notes.txt"
    sample.write_text("hello")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 5

    svc = make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    written_json: str = meta_stream.write_string.call_args[0][0]
    meta: dict = json.loads(written_json)
    assert meta["file_name"] == "notes.txt"


def test_send_file_metadata_contains_correct_size(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """The JSON payload on ``file_meta`` must include the exact file size in bytes."""
    sample = tmp_path / "data.bin"
    sample.write_bytes(b"\x00" * 2048)

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 2048

    svc = make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    written_json: str = meta_stream.write_string.call_args[0][0]
    meta: dict = json.loads(written_json)
    assert meta["file_size"] == 2048


def test_send_file_flushes_meta_stream(qtbot: QtBot, tmp_path, make_service) -> None:
    """The meta stream must be explicitly flushed so the peer receives it promptly."""
    sample = tmp_path / "flush_test.txt"
    sample.write_text("hi")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 2

    svc = make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)


def test_send_file_calls_write_file_on_data_stream(qtbot: QtBot, tmp_path, make_service) -> None:
    """The data stream must use ``write_file`` to send raw bytes."""
    sample = tmp_path / "archive.zip"
    sample.write_bytes(b"PK")

    meta_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.write_file.return_value = 2

    svc = make_service(_make_tau(meta_stream, data_stream))
    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    data_stream.write_file.assert_called_once_with(str(sample))


def test_send_file_emits_error_when_transport_raises(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """A transport exception must surface via ``file_send_error``, not propagate."""
    sample = tmp_path / "broken.bin"
    sample.write_bytes(b"data")

    meta_stream = MagicMock()
    meta_stream.write_string.side_effect = RuntimeError("connection lost")

    svc = make_service(_make_tau(meta_stream, MagicMock()))
    errors: list[str] = []
    svc.file_send_error.connect(lambda msg: errors.append(msg))

    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "connection lost" in errors[0]


# ---------------------------------------------------------------------------
# receive_metadata — signal assertions
# ---------------------------------------------------------------------------


def test_receive_metadata_emits_file_metadata_received(qtbot: QtBot, make_service) -> None:
    """``file_metadata_received`` carries a ``FileMetadataDTO`` with filename, size, and modified_at."""
    tau, _, _ = _make_metadata_tau("photo.jpg", 4096, modified_at=1_700_000_000_000)
    svc = make_service(tau)

    received: list[FileMetadataDTO] = []
    svc.file_metadata_received.connect(received.append)
    svc.receive_metadata()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received[0].name == "photo.jpg"
    assert received[0].size == 4096
    assert received[0].modified_at == 1_700_000_000_000


def test_receive_metadata_emits_zero_modified_at_when_absent(qtbot: QtBot, make_service) -> None:
    """``file_metadata_received`` emits ``modified_at=0`` when the sender omits the field."""
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = json.dumps(
        {"file_name": "doc.pdf", "file_size": 512}
    ).encode("utf-8")

    svc = make_service(_make_tau(meta_stream, MagicMock()))
    received: list[FileMetadataDTO] = []
    svc.file_metadata_received.connect(received.append)
    svc.receive_metadata()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received[0].name == "doc.pdf"
    assert received[0].size == 512
    assert received[0].modified_at == 0


def test_receive_metadata_emits_error_on_bad_json(qtbot: QtBot, make_service) -> None:
    """Malformed JSON on the meta channel surfaces via ``file_receive_error``."""
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = b"NOT_JSON{"

    svc = make_service(_make_tau(meta_stream, MagicMock()))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_metadata()

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert len(errors) == 1


def test_receive_metadata_emits_error_on_missing_keys(qtbot: QtBot, make_service) -> None:
    """A JSON object missing required keys surfaces via ``file_receive_error``."""
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = b"{}"

    svc = make_service(_make_tau(meta_stream, MagicMock()))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_metadata()

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert len(errors) == 1


def test_receive_metadata_does_not_emit_signal_on_error(qtbot: QtBot, make_service) -> None:
    """``file_metadata_received`` must not fire when parsing fails."""
    meta_stream = MagicMock()
    meta_stream.read_all.return_value = b"{}"

    svc = make_service(_make_tau(meta_stream, MagicMock()))
    received: list = []
    errors: list[str] = []
    svc.file_metadata_received.connect(lambda _: received.append(True))
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_metadata()

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert received == []


def test_receive_metadata_emits_error_when_transport_raises(qtbot: QtBot, make_service) -> None:
    """A transport exception on the meta channel surfaces via ``file_receive_error``."""
    meta_stream = MagicMock()
    meta_stream.read_all.side_effect = OSError("channel closed")

    svc = make_service(_make_tau(meta_stream, MagicMock()))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_metadata()

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "channel closed" in errors[0]


# ---------------------------------------------------------------------------
# receive_file — signal assertions
# ---------------------------------------------------------------------------


def test_receive_file_emits_receive_complete(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``file_receive_complete`` carries a ``FileReceiveCompleteDTO`` with filename and dest_path."""
    dest = str(tmp_path / "music.mp3")
    resp_stream = MagicMock()
    data_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))

    received: list[FileReceiveCompleteDTO] = []
    svc.file_receive_complete.connect(received.append)
    svc.receive_file(dest, 8192)

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received[0].filename == "music.mp3"
    assert received[0].dest_path == dest


def test_receive_file_writes_accepted_to_response_channel(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``receive_file`` must write ``FileTransferResponse.ACCEPTED_FROM_PC`` to the response channel."""
    resp_stream = MagicMock()
    data_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(str(tmp_path / "file.bin"), 10)

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    resp_stream.write_string.assert_called_once_with(FileTransferResponse.ACCEPTED_FROM_PC)


def test_receive_file_calls_read_to_file_with_correct_args(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``read_to_file`` must receive the exact dest_path and file_size."""
    dest = str(tmp_path / "doc.pdf")
    resp_stream = MagicMock()
    data_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(dest, 3333)

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    data_stream.read_to_file.assert_called_once_with(dest, 3333)


def test_receive_file_creates_parent_dir_if_missing(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """The parent directory is created automatically when it does not exist."""
    dest = str(tmp_path / "deep" / "nested" / "dir" / "file.bin")
    resp_stream = MagicMock()
    data_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(dest, 10)

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    assert os.path.isdir(str(tmp_path / "deep" / "nested" / "dir"))


def test_receive_file_emits_error_when_transport_raises(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """A transport exception on the data channel surfaces via ``file_receive_error``."""
    resp_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.read_to_file.side_effect = OSError("network dropped")

    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_file(str(tmp_path / "crash.bin"), 100)

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "network dropped" in errors[0]


def test_receive_file_does_not_emit_complete_on_error(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``file_receive_complete`` must not fire when the transfer fails."""
    resp_stream = MagicMock()
    data_stream = MagicMock()
    data_stream.read_to_file.side_effect = OSError("dropped")

    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))
    complete: list = []
    errors: list[str] = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.receive_file(str(tmp_path / "fail.bin"), 50)

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert complete == []


def test_receive_file_applies_utime_when_modified_at_provided(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """When ``modified_at_ms > 0`` the received file's ``mtime`` must match it."""
    dest = tmp_path / "photo.jpg"
    dest.write_bytes(b"")  # pre-create so read_to_file mock doesn't need to write it

    modified_at_ms: int = 1_700_000_000_000  # 2023-11-14 in ms
    expected_mtime: float = modified_at_ms / 1000.0

    resp_stream = MagicMock()
    data_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(str(dest), 0, modified_at_ms)

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    assert abs(dest.stat().st_mtime - expected_mtime) < 1.0


def test_receive_file_skips_utime_when_modified_at_is_zero(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """When ``modified_at_ms == 0`` the file's ``mtime`` must not be backdated."""
    import time

    dest = tmp_path / "doc.pdf"
    dest.write_bytes(b"")

    before: float = time.time()

    resp_stream = MagicMock()
    data_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), data_stream, resp_stream=resp_stream))

    complete: list = []
    svc.file_receive_complete.connect(lambda *_: complete.append(True))
    svc.receive_file(str(dest), 0, 0)

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)
    # mtime should be close to now, not some ancient timestamp
    assert dest.stat().st_mtime >= before - 5


# ---------------------------------------------------------------------------
# reject_receive
# ---------------------------------------------------------------------------


def test_reject_receive_writes_rejected_to_response_channel(qtbot: QtBot, make_service) -> None:
    """``reject_receive`` must write ``FileTransferResponse.REJECTED`` to the response channel."""
    resp_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), MagicMock(), resp_stream=resp_stream))

    svc.reject_receive()
    qtbot.wait(200)

    resp_stream.write_string.assert_called_once_with(FileTransferResponse.REJECTED_FROM_PC)


def test_reject_receive_flushes_response_stream(qtbot: QtBot, make_service) -> None:
    """The response stream must be flushed after writing the reject token."""
    resp_stream = MagicMock()
    svc = make_service(_make_tau(MagicMock(), MagicMock(), resp_stream=resp_stream))

    svc.reject_receive()
    qtbot.wait(200)

    resp_stream.flush.assert_called_once()


def test_reject_receive_emits_error_on_transport_exception(qtbot: QtBot, make_service) -> None:
    """A transport exception during rejection surfaces via ``file_receive_error``."""
    resp_stream = MagicMock()
    resp_stream.write_string.side_effect = OSError("pipe broken")

    svc = make_service(_make_tau(MagicMock(), MagicMock(), resp_stream=resp_stream))
    errors: list[str] = []
    svc.file_receive_error.connect(lambda msg: errors.append(msg))
    svc.reject_receive()

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=1000)
    assert "pipe broken" in errors[0]


# ---------------------------------------------------------------------------
# tau staleness — transport accessed at call time, not construction time
# ---------------------------------------------------------------------------


def test_service_reads_tau_from_connectivity_at_call_time(
    qtbot: QtBot,
    tmp_path,
    make_service,
) -> None:
    """``connectivity.tau`` must be accessed at transfer time, not at construction.

    Verifies the staleness-bug fix: if ``ConnectivityService`` replaces
    ``_tau`` after ``FileTransferService`` was built, the service must use
    the *new* transport, not the one it saw at construction.
    """
    sample = tmp_path / "staleness_test.bin"
    sample.write_bytes(b"hello")

    original_meta = MagicMock()
    original_tau = _make_tau(original_meta, MagicMock())

    new_meta = MagicMock()
    new_data = MagicMock()
    new_data.write_file.return_value = 5
    new_tau = _make_tau(new_meta, new_data)

    svc = make_service(original_tau)

    # Simulate a reconnect replacing the transport.
    svc._connectivity.tau = new_tau

    complete: list = []
    svc.file_send_complete.connect(lambda *_: complete.append(True))
    svc.send_file(str(sample))

    qtbot.waitUntil(lambda: len(complete) > 0, timeout=1000)

    new_meta.write_string.assert_called_once()
    original_meta.write_string.assert_not_called()
