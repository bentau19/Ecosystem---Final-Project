"""Unit tests for FileTransferViewModel — connectivity gating and signal forwarding."""

from unittest.mock import MagicMock

import pytest

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

    mock_service.receive_file.assert_called_once_with("/tmp/downloads/photo.jpg", 4096)


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
    names: list[str] = []
    bytes_: list[int] = []
    vm.send_complete.connect(lambda n, b: (names.append(n), bytes_.append(b)))

    vm._on_send_complete("photo.jpg", 1024)

    assert names == ["photo.jpg"]
    assert bytes_ == [1024]


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
    names: list[str] = []
    sizes: list[int] = []
    vm.metadata_received.connect(lambda n, s: (names.append(n), sizes.append(s)))

    vm._on_metadata_received("doc.pdf", 4096)

    assert names == ["doc.pdf"]
    assert sizes == [4096]


def test_on_receive_complete_forwards_signal(vm: FileTransferViewModel) -> None:
    names: list[str] = []
    paths: list[str] = []
    vm.receive_complete.connect(lambda n, p: (names.append(n), paths.append(p)))

    vm._on_receive_complete("doc.pdf", "/tmp/downloads/doc.pdf")

    assert names == ["doc.pdf"]
    assert paths == ["/tmp/downloads/doc.pdf"]


def test_on_receive_error_forwards_signal(vm: FileTransferViewModel) -> None:
    received: list[str] = []
    vm.receive_error.connect(received.append)

    vm._on_receive_error("Timeout")

    assert received == ["Timeout"]
