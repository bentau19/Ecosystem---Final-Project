"""Unit tests for utils.services_manager — ServicesManager."""

from unittest.mock import MagicMock, patch

import pytest

from utils.services_manager import ServicesManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_connectivity_service() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def manager(mock_connectivity_service: MagicMock) -> ServicesManager:
    with patch(
        "utils.services_manager.ConnectivityService",
        return_value=mock_connectivity_service,
    ):
        return ServicesManager()


# ---------------------------------------------------------------------------
# Service attributes
# ---------------------------------------------------------------------------


def test_manager_exposes_connectivity_service(
    manager: ServicesManager, mock_connectivity_service: MagicMock
) -> None:
    assert manager.connectivity_service is mock_connectivity_service


# ---------------------------------------------------------------------------
# Service instantiation
# ---------------------------------------------------------------------------


def test_manager_instantiates_connectivity_service() -> None:
    with patch("utils.services_manager.ConnectivityService") as mock_cls:
        ServicesManager()

    mock_cls.assert_called_once()


def test_manager_passes_no_args_to_connectivity_service() -> None:
    with patch("utils.services_manager.ConnectivityService") as mock_cls:
        ServicesManager()

    mock_cls.assert_called_once_with()
