"""Unit tests for utils.repository_manger — RepositoryManager."""

from unittest.mock import MagicMock, patch

import pytest

from utils.repository_manger import RepositoryManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_tool_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_device_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_prev_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def manager(
    mock_tool_repo: MagicMock,
    mock_device_repo: MagicMock,
    mock_prev_repo: MagicMock,
) -> RepositoryManager:
    with (
        patch("utils.repository_manger.ToolRepository", return_value=mock_tool_repo),
        patch("utils.repository_manger.DeviceInfoRepository", return_value=mock_device_repo),
        patch("utils.repository_manger.PreviousDeviceRepository", return_value=mock_prev_repo),
    ):
        return RepositoryManager()


# ---------------------------------------------------------------------------
# Repository attributes
# ---------------------------------------------------------------------------


def test_manager_exposes_tools_repository(
    manager: RepositoryManager, mock_tool_repo: MagicMock
) -> None:
    assert manager.tools_repository is mock_tool_repo


def test_manager_exposes_device_repository(
    manager: RepositoryManager, mock_device_repo: MagicMock
) -> None:
    assert manager.device_repository is mock_device_repo


def test_manager_exposes_previous_device_repository(
    manager: RepositoryManager, mock_prev_repo: MagicMock
) -> None:
    assert manager.previous_device_repository is mock_prev_repo


# ---------------------------------------------------------------------------
# Repository instantiation
# ---------------------------------------------------------------------------


def test_manager_instantiates_tool_repository() -> None:
    with (
        patch("utils.repository_manger.ToolRepository") as mock_tool_cls,
        patch("utils.repository_manger.DeviceInfoRepository"),
        patch("utils.repository_manger.PreviousDeviceRepository"),
    ):
        RepositoryManager()

    mock_tool_cls.assert_called_once()


def test_manager_instantiates_device_info_repository() -> None:
    with (
        patch("utils.repository_manger.ToolRepository"),
        patch("utils.repository_manger.DeviceInfoRepository") as mock_device_cls,
        patch("utils.repository_manger.PreviousDeviceRepository"),
    ):
        RepositoryManager()

    mock_device_cls.assert_called_once()


def test_manager_instantiates_previous_device_repository() -> None:
    with (
        patch("utils.repository_manger.ToolRepository"),
        patch("utils.repository_manger.DeviceInfoRepository"),
        patch("utils.repository_manger.PreviousDeviceRepository") as mock_prev_cls,
    ):
        RepositoryManager()

    mock_prev_cls.assert_called_once()


def test_manager_repositories_are_distinct_objects(manager: RepositoryManager) -> None:
    assert manager.tools_repository is not manager.device_repository
    assert manager.device_repository is not manager.previous_device_repository
    assert manager.tools_repository is not manager.previous_device_repository
