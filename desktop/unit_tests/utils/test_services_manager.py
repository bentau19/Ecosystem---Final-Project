"""Unit tests for utils.services_manager — ServicesManager."""

from unittest.mock import MagicMock, patch

import pytest

from services.file_transfer import FileTransferService
from utils.services_manager import ServicesManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_connectivity_service() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_device_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def manager(
    mock_connectivity_service: MagicMock,
    mock_device_repo: MagicMock,
) -> ServicesManager:
    with (
        patch(
            "utils.services_manager.ConnectivityService",
            return_value=mock_connectivity_service,
        ),
        patch("utils.services_manager.repository_manager") as mock_rm,
    ):
        mock_rm.device_repository = mock_device_repo
        return ServicesManager()


# ---------------------------------------------------------------------------
# Service attributes
# ---------------------------------------------------------------------------


def test_manager_exposes_connectivity_service(
    manager: ServicesManager,
    mock_connectivity_service: MagicMock,
) -> None:
    assert manager.connectivity_service is mock_connectivity_service


def test_manager_exposes_file_transfer_service(manager: ServicesManager) -> None:
    assert isinstance(manager.file_transfer_service, FileTransferService)


# ---------------------------------------------------------------------------
# Service instantiation
# ---------------------------------------------------------------------------


def test_manager_instantiates_connectivity_service() -> None:
    with (
        patch("utils.services_manager.ConnectivityService") as mock_cls,
        patch("utils.services_manager.repository_manager"),
    ):
        ServicesManager()

    mock_cls.assert_called_once()


def test_manager_passes_device_repository_to_connectivity_service() -> None:
    with (
        patch("utils.services_manager.ConnectivityService") as mock_cls,
        patch("utils.services_manager.repository_manager") as mock_rm,
    ):
        mock_rm.device_repository = MagicMock()
        ServicesManager()

    mock_cls.assert_called_once_with()


# ---------------------------------------------------------------------------
# FileTransferService wiring
# ---------------------------------------------------------------------------


def test_manager_passes_connectivity_service_to_file_transfer_service(
    manager: ServicesManager,
    mock_connectivity_service: MagicMock,
) -> None:
    """FileTransferService must receive the live ConnectivityService, not a tau snapshot.

    This matters because ConnectivityService replaces ``_tau`` on every
    reconnect.  Injecting the service (not the tau snapshot) lets
    FileTransferService always read ``connectivity.tau`` at call-time.
    """
    assert manager.file_transfer_service._connectivity is mock_connectivity_service
