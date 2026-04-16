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
def manager(
    mock_tool_repo: MagicMock,
    mock_device_repo: MagicMock,
) -> RepositoryManager:
    with (
        patch("utils.repository_manger.ToolRepository", return_value=mock_tool_repo),
        patch("utils.repository_manger.DeviceRepository", return_value=mock_device_repo),
    ):
        return RepositoryManager()


# ---------------------------------------------------------------------------
# Repository attributes
# ---------------------------------------------------------------------------


def test_manager_exposes_tools_repository(
    manager: RepositoryManager,
    mock_tool_repo: MagicMock,
) -> None:
    assert manager.tools_repository is mock_tool_repo


def test_manager_exposes_device_repository(
    manager: RepositoryManager,
    mock_device_repo: MagicMock,
) -> None:
    assert manager.device_repository is mock_device_repo


# ---------------------------------------------------------------------------
# Repository instantiation
# ---------------------------------------------------------------------------


def test_manager_instantiates_tool_repository() -> None:
    with (
        patch("utils.repository_manger.ToolRepository") as mock_tool_cls,
        patch("utils.repository_manger.DeviceRepository"),
    ):
        RepositoryManager()

    mock_tool_cls.assert_called_once()


def test_manager_instantiates_device_repository() -> None:
    with (
        patch("utils.repository_manger.ToolRepository"),
        patch("utils.repository_manger.DeviceRepository") as mock_device_cls,
    ):
        RepositoryManager()

    mock_device_cls.assert_called_once()


def test_manager_repositories_are_distinct_objects(manager: RepositoryManager) -> None:
    assert manager.tools_repository is not manager.device_repository
