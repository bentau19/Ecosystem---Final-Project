"""Unit tests for FileTransferViewModel — connectivity gating and signal forwarding."""

from unittest.mock import MagicMock

import pytest

from domain.dto.file_transfer import (
    FileTransferStatusDTO,
    TransferDirection,
    TransferStatus,
)
from viewmodels.file_transfer import FileTransferViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_service() -> MagicMock:
    svc = MagicMock()
    # Give each signal a real .connect() so wiring in __init__ doesn't blow up
    for attr in (
        "file_send_started", "file_send_complete", "file_send_error",
        "file_receive_started", "file_receive_complete", "file_receive_error",
    ):
        getattr(svc, attr).connect = MagicMock()
    return svc


@pytest.fixture()
def mock_connectivity() -> MagicMock:
    conn = MagicMock()
    conn.device_connected.connect = MagicMock()
    conn.device_disconnected.connect = MagicMock()
    return conn


@pytest.fixture()
def vm(qtbot, mock_service: MagicMock, mock_connectivity: MagicMock) -> FileTransferViewModel:
    return FileTransferViewModel(
        file_transfer_service=mock_service,
        connectivity_service=mock_connectivity,
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_initial_state_is_not_connected(vm: FileTransferViewModel) -> None:
    assert vm.is_device_connected is False


# ---------------------------------------------------------------------------
# Connectivity gating — send_file
# ---------------------------------------------------------------------------


def test_send_file_no_ops_when_not_connected(
    vm: FileTransferViewModel, mock_service: MagicMock
) -> None:
    vm.send_file("/tmp/file.txt")

    mock_service.send_file.assert_not_called()


def test_send_file_delegates_when_connected(
    vm: FileTransferViewModel, mock_service: MagicMock
) -> None:
    vm._on_device_connected()
    vm.send_file("/tmp/file.txt")

    mock_service.send_file.assert_called_once_with("/tmp/file.txt")


# ---------------------------------------------------------------------------
# Connectivity gating — receive_file
# ---------------------------------------------------------------------------


def test_receive_file_no_ops_when_not_connected(
    vm: FileTransferViewModel, mock_service: MagicMock
) -> None:
    vm.receive_file("/tmp/downloads")

    mock_service.receive_file.assert_not_called()


def test_receive_file_delegates_when_connected(
    vm: FileTransferViewModel, mock_service: MagicMock
) -> None:
    vm._on_device_connected()
    vm.receive_file("/tmp/downloads")

    mock_service.receive_file.assert_called_once_with("/tmp/downloads")


# ---------------------------------------------------------------------------
# device_ready_changed
# ---------------------------------------------------------------------------


def test_device_ready_changed_emits_true_on_connect(vm: FileTransferViewModel) -> None:
    received: list[bool] = []
    vm.device_ready_changed.connect(received.append)

    vm._on_device_connected()

    assert received == [True]


def test_device_ready_changed_emits_false_on_disconnect(vm: FileTransferViewModel) -> None:
    vm._on_device_connected()
    received: list[bool] = []
    vm.device_ready_changed.connect(received.append)

    vm._on_device_disconnected()

    assert received == [False]


def test_is_device_connected_reflects_lifecycle(vm: FileTransferViewModel) -> None:
    vm._on_device_connected()
    assert vm.is_device_connected is True

    vm._on_device_disconnected()
    assert vm.is_device_connected is False


# ---------------------------------------------------------------------------
# Signal forwarding — send
# ---------------------------------------------------------------------------


def test_on_send_started_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[str] = []
    vm.send_started.connect(received.append)

    vm._on_send_started("photo.jpg")

    assert received == ["photo.jpg"]


def test_on_send_started_emits_status_dto(vm: FileTransferViewModel) -> None:
    received: list[FileTransferStatusDTO] = []
    vm.transfer_status_changed.connect(received.append)

    vm._on_send_started("photo.jpg")

    assert len(received) == 1
    dto = received[0]
    assert dto.filename == "photo.jpg"
    assert dto.direction == TransferDirection.SEND
    assert dto.status == TransferStatus.STARTED


def test_on_send_complete_forwards_signal(vm: FileTransferViewModel) -> None:
    names: list[str] = []
    bytes_: list[int] = []
    vm.send_complete.connect(lambda n, b: (names.append(n), bytes_.append(b)))

    vm._on_send_complete("photo.jpg", 1024)

    assert names == ["photo.jpg"]
    assert bytes_ == [1024]


def test_on_send_complete_emits_status_dto_with_bytes(vm: FileTransferViewModel) -> None:
    received: list[FileTransferStatusDTO] = []
    vm.transfer_status_changed.connect(received.append)

    vm._on_send_complete("photo.jpg", 2048)

    dto = received[0]
    assert dto.status == TransferStatus.COMPLETE
    assert dto.detail == "2048"


def test_on_send_error_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[str] = []
    vm.send_error.connect(received.append)

    vm._on_send_error("Connection lost")

    assert received == ["Connection lost"]


def test_on_send_error_emits_status_dto(vm: FileTransferViewModel) -> None:
    received: list[FileTransferStatusDTO] = []
    vm.transfer_status_changed.connect(received.append)

    vm._on_send_error("Connection lost")

    dto = received[0]
    assert dto.direction == TransferDirection.SEND
    assert dto.status == TransferStatus.ERROR
    assert dto.detail == "Connection lost"


# ---------------------------------------------------------------------------
# Signal forwarding — receive
# ---------------------------------------------------------------------------


def test_on_receive_started_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[str] = []
    vm.receive_started.connect(received.append)

    vm._on_receive_started("doc.pdf")

    assert received == ["doc.pdf"]


def test_on_receive_complete_emits_status_dto_with_dest_path(vm: FileTransferViewModel) -> None:
    received: list[FileTransferStatusDTO] = []
    vm.transfer_status_changed.connect(received.append)

    vm._on_receive_complete("doc.pdf", "/tmp/downloads/doc.pdf")

    dto = received[0]
    assert dto.status == TransferStatus.COMPLETE
    assert dto.detail == "/tmp/downloads/doc.pdf"
    assert dto.direction == TransferDirection.RECEIVE


def test_on_receive_error_emits_status_dto(vm: FileTransferViewModel) -> None:
    received: list[FileTransferStatusDTO] = []
    vm.transfer_status_changed.connect(received.append)

    vm._on_receive_error("Timeout")

    dto = received[0]
    assert dto.direction == TransferDirection.RECEIVE
    assert dto.status == TransferStatus.ERROR
    assert dto.detail == "Timeout"
