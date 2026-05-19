"""Unit tests for ToolRepository (SQLite-backed)."""

import sqlite3
from pathlib import Path

import pytest

from domain.entities.tool import ToolEntity
from repositories.tool import ToolRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool_enabled() -> ToolEntity:
    return ToolEntity(
        title="hammer",
        description="A tool for driving nails into wood.",
        icon_path="hammer.png",
        is_enabled=True,
    )


@pytest.fixture()
def tool_disabled() -> ToolEntity:
    return ToolEntity(
        title="screwdriver",
        description="A tool for driving screws.",
        icon_path="screwdriver.png",
        is_enabled=False,
    )


@pytest.fixture()
def tool_another_enabled() -> ToolEntity:
    return ToolEntity(
        title="wrench",
        description="A tool for tightening nuts and bolts.",
        icon_path="wrench.png",
        is_enabled=True,
    )


@pytest.fixture()
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ToolRepository:
    """Provide a ToolRepository backed by a temp SQLite database.

    Monkeypatches ``sqlite3.connect`` so all calls within ToolRepository are
    redirected to a fresh, empty database in ``tmp_path`` instead of the
    production file.  Seeds are inserted by ``_configure_db`` as normal.
    """
    db_path = str(tmp_path / "test_tools.db")
    original_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda path, **kw: original_connect(db_path, **kw))
    return ToolRepository()


# ---------------------------------------------------------------------------
# id_exists
# ---------------------------------------------------------------------------


def test_id_exists_returns_false_when_title_not_in_db(
    repository: ToolRepository,
) -> None:
    assert repository.id_exists("nonexistent") is False


def test_id_exists_returns_true_after_save(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    assert repository.id_exists(tool_enabled.title) is True


def test_id_exists_returns_false_for_unknown_title_when_other_entities_exist(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    assert repository.id_exists("nonexistent") is False


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_none_when_title_not_found(
    repository: ToolRepository,
) -> None:
    assert repository.get_by_id("nonexistent") is None


def test_get_by_id_returns_entity_after_save(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    result = repository.get_by_id(tool_enabled.title)

    assert result == tool_enabled


def test_get_by_id_returns_none_when_title_does_not_match(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    assert repository.get_by_id("nonexistent") is None


def test_get_by_id_returns_correct_entity_when_multiple_saved(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
    tool_disabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    repository.save(tool_disabled)

    assert repository.get_by_id(tool_enabled.title) == tool_enabled
    assert repository.get_by_id(tool_disabled.title) == tool_disabled


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


def test_get_all_returns_only_seeded_tools_when_no_extra_saves(
    repository: ToolRepository,
) -> None:
    # The fixture DB is seeded with 10 default tools by _configure_db
    result = repository.get_all()
    assert len(result) == 10


def test_get_all_returns_additional_entity_after_save(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    initial_count = len(repository.get_all())
    repository.save(tool_enabled)

    assert len(repository.get_all()) == initial_count + 1


def test_get_all_excludes_deleted_entities(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
    tool_disabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    repository.save(tool_disabled)

    repository.delete(tool_enabled.title)

    result = repository.get_all()
    assert tool_enabled not in result
    assert tool_disabled in result


# ---------------------------------------------------------------------------
# get_all_enabled
# ---------------------------------------------------------------------------


def test_get_all_enabled_returns_only_enabled_tools(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
    tool_disabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    repository.save(tool_disabled)

    result = repository.get_all_enabled()

    assert tool_enabled in result
    assert tool_disabled not in result


def test_get_all_enabled_excludes_newly_disabled_tool(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    disabled_version = ToolEntity(
        title=tool_enabled.title,
        description=tool_enabled.description,
        icon_path=tool_enabled.icon_path,
        is_enabled=False,
    )
    repository.save(disabled_version)

    result = repository.get_all_enabled()

    assert disabled_version not in result


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_persists_entity_to_db(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    assert repository.get_by_id(tool_enabled.title) == tool_enabled


def test_save_replaces_existing_entity_with_same_title(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    updated = ToolEntity(
        title=tool_enabled.title,
        description="Updated description",
        icon_path="new_icon.png",
        is_enabled=False,
    )
    repository.save(updated)

    assert repository.get_by_id(tool_enabled.title) == updated


def test_save_emits_entity_saved_with_saved_entity(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    received: list[ToolEntity] = []
    repository.entity_saved.connect(lambda e: received.append(e))

    repository.save(tool_enabled)

    assert received == [tool_enabled]


def test_save_emits_entity_saved_once_per_call(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
    tool_disabled: ToolEntity,
) -> None:
    received: list[ToolEntity] = []
    repository.entity_saved.connect(lambda e: received.append(e))

    repository.save(tool_enabled)
    repository.save(tool_disabled)

    assert len(received) == 2
    assert received[0] == tool_enabled
    assert received[1] == tool_disabled


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_entity_from_db(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)

    repository.delete(tool_enabled.title)

    assert repository.get_by_id(tool_enabled.title) is None


def test_delete_only_removes_matching_entity(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
    tool_disabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    repository.save(tool_disabled)

    repository.delete(tool_enabled.title)

    assert repository.get_by_id(tool_disabled.title) == tool_disabled


def test_delete_emits_entity_deleted_signal(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    received: list[str] = []
    repository.entity_deleted.connect(lambda title: received.append(title))

    repository.delete(tool_enabled.title)

    assert received == [tool_enabled.title]


def test_delete_nonexistent_title_still_emits_entity_deleted(
    repository: ToolRepository,
) -> None:
    received: list[str] = []
    repository.entity_deleted.connect(lambda title: received.append(title))

    repository.delete("nonexistent")

    assert received == ["nonexistent"]


def test_delete_all_entities_results_in_only_seeded_tools_removed(
    repository: ToolRepository,
    tool_enabled: ToolEntity,
    tool_disabled: ToolEntity,
) -> None:
    repository.save(tool_enabled)
    repository.save(tool_disabled)

    repository.delete(tool_enabled.title)
    repository.delete(tool_disabled.title)

    titles = {t.title for t in repository.get_all()}
    assert tool_enabled.title not in titles
    assert tool_disabled.title not in titles
