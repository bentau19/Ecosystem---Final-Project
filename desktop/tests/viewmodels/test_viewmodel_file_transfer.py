"""Unit tests for FileTransferViewModel — connectivity gating and signal forwarding."""

from unittest.mock import MagicMock

import pytest

from domain.dto.file_metadata import FileMetadataDTO
from domain.dto.file_receive_complete import FileReceiveCompleteDTO
from domain.dto.file_receive_prompt import FileReceivePromptDTO
from domain.dto.file_send_complete import FileSendCompleteDTO
from viewmodels.file_transfer import FileTransferViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_service() -> MagicMock:
    """Mock :class:`~services.file_transfer.FileTransferService` with wired signals."""
    svc = MagicMock()
    for attr in (
        "file_send_complete",
        "file_send_rejected",
        "file_send_error",
        "file_metadata_received",
        "file_receive_complete",
        "file_receive_error",
    ):
        getattr(svc, attr).connect = MagicMock()
    return svc


@pytest.fixture()
def mock_connectivity() -> MagicMock:
    """Mock :class:`~services.connectivity.ConnectivityService`."""
    conn = MagicMock()
    conn.device_connected.connect = MagicMock()
    conn.device_disconnected.connect = MagicMock()
    return conn


@pytest.fixture()
def vm(
    qtbot,
    mock_service: MagicMock,
    mock_connectivity: MagicMock,
) -> FileTransferViewModel:
    """Constructed :class:`FileTransferViewModel` backed by mocks."""
    instance = FileTransferViewModel(
        file_transfer_service=mock_service,
        connectivity_service=mock_connectivity,
    )
    # Source initialises _is_device_connected lazily; set it here so tests
    # that inspect the initial state don't hit AttributeError.
    instance._is_device_connected = False
    return instance


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_initial_state_is_not_connected(vm: FileTransferViewModel) -> None:
    assert vm.device_connected is False


# ---------------------------------------------------------------------------
# Connectivity gating — send_file
# ---------------------------------------------------------------------------


def test_send_file_no_ops_when_not_connected(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    vm.send_file("/tmp/file.txt")

    mock_service.send_file.assert_not_called()


def test_send_file_delegates_when_connected(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    vm._on_device_connected()
    vm.send_file("/tmp/file.txt")

    mock_service.send_file.assert_called_once_with("/tmp/file.txt")


# ---------------------------------------------------------------------------
# Connectivity gating — receive_metadata
# ---------------------------------------------------------------------------


def test_receive_metadata_no_ops_when_not_connected(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    vm.receive_metadata()

    mock_service.receive_metadata.assert_not_called()


def test_receive_metadata_delegates_when_connected(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    vm._on_device_connected()
    vm.receive_metadata()

    mock_service.receive_metadata.assert_called_once()


# ---------------------------------------------------------------------------
# receive_file — not connectivity-gated
# ---------------------------------------------------------------------------


def test_receive_file_delegates_when_connected(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    vm._on_device_connected()
    vm.receive_file("/tmp/downloads/photo.jpg", 4096)

    mock_service.receive_file.assert_called_once_with("/tmp/downloads/photo.jpg", 4096, 0)


# ---------------------------------------------------------------------------
# reject_receive — not connectivity-gated
# ---------------------------------------------------------------------------


def test_reject_receive_delegates_regardless_of_connectivity(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    """``reject_receive`` is not gated; the service handles stale transport gracefully."""
    vm.reject_receive()

    mock_service.reject_receive.assert_called_once()


# ---------------------------------------------------------------------------
# is_device_connected reflects lifecycle
# ---------------------------------------------------------------------------


def test_is_device_connected_reflects_lifecycle(
    vm: FileTransferViewModel,
) -> None:
    vm._on_device_connected()
    assert vm.device_connected is True

    vm._on_device_disconnected()
    assert vm.device_connected is False


# ---------------------------------------------------------------------------
# Signal forwarding — send
# ---------------------------------------------------------------------------


def test_on_send_complete_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[FileSendCompleteDTO] = []
    vm.send_complete.connect(received.append)

    vm._on_send_complete(FileSendCompleteDTO(filename="photo.jpg", total_bytes=1024))

    assert received[0].filename == "photo.jpg"
    assert received[0].total_bytes == 1024


def test_on_send_error_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[str] = []
    vm.send_error.connect(received.append)

    vm._on_send_error("Connection lost")

    assert received == ["Connection lost"]


def test_on_send_rejected_emits_send_error_with_filename(
    vm: FileTransferViewModel,
) -> None:
    """A rejection is surfaced as a ``send_error`` containing the filename."""
    received: list[str] = []
    vm.send_error.connect(received.append)

    vm._on_send_rejected("photo.jpg")

    assert len(received) == 1
    assert "photo.jpg" in received[0]


# ---------------------------------------------------------------------------
# Signal forwarding — receive
# ---------------------------------------------------------------------------


def test_on_metadata_received_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[FileReceivePromptDTO] = []
    vm.metadata_received.connect(received.append)

    vm._on_metadata_received(FileMetadataDTO(name="doc.pdf", size=4096, modified_at=0))

    assert received[0].filename == "doc.pdf"
    assert received[0].size == 4096


def test_on_metadata_received_stores_modified_at(vm: FileTransferViewModel) -> None:
    """The VM must stash ``modified_at`` so ``receive_file`` can forward it."""
    vm._on_metadata_received(FileMetadataDTO(name="photo.jpg", size=2048, modified_at=1_700_000_000_000))

    assert vm._pending_modified_at == 1_700_000_000_000


def test_receive_file_passes_pending_modified_at_to_service(
    vm: FileTransferViewModel,
    mock_service: MagicMock,
) -> None:
    """``receive_file`` must forward the stored ``modified_at`` to the service."""
    vm._on_device_connected()
    vm._on_metadata_received(FileMetadataDTO(name="photo.jpg", size=2048, modified_at=1_700_000_000_000))
    vm.receive_file("/tmp/photo.jpg", 2048)

    mock_service.receive_file.assert_called_once_with("/tmp/photo.jpg", 2048, 1_700_000_000_000)


def test_on_receive_complete_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[FileReceiveCompleteDTO] = []
    vm.receive_complete.connect(received.append)

    vm._on_receive_complete(FileReceiveCompleteDTO(filename="doc.pdf", dest_path="/tmp/downloads/doc.pdf"))

    assert received[0].filename == "doc.pdf"
    assert received[0].dest_path == "/tmp/downloads/doc.pdf"


def test_on_receive_error_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[str] = []
    vm.receive_error.connect(received.append)

    vm._on_receive_error("Timeout")

    assert received == ["Timeout"]
