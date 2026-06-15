import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal

from domain.entities.tool import ToolEntity
from repositories.repository import IRepository
from serializers.tool import ToolSerializer
from utils.db import sqlite_connection
from utils.meta import ABCQObjectMeta

# Seed data — inserted once when the tools table is empty on first launch.
_SEED_TOOLS: list[tuple[str, str, str, bool]] = [
    (
        "Send File to Phone",
        "Send any file from your PC directly to your phone.",
        ":/icons/smartphone.svg",
        True,
    ),
]


class ToolRepository(
    IRepository[ToolEntity, str], QObject, metaclass=ABCQObjectMeta
):
    """Repository for tool entities backed by a SQLite database.

    Each public method opens a short-lived connection so the repository is
    safe to call from any thread.  The ``tools`` table is created — and
    seeded with default tools — on first construction via ``_configure_db``.
    Seeds are only inserted when the table is empty, so user edits are never
    overwritten across restarts.

    Signals:
        entity_saved:   Emitted with the saved ``ToolEntity`` after a
            successful ``save`` call.
        entity_deleted: Emitted with the tool title (``str``) after a
            successful ``delete`` call.
    """

    entity_saved: Signal = Signal(object)
    entity_deleted: Signal = Signal(str)

    def __init__(
            self,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the repository and ensure the backing table exists.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._serializer = ToolSerializer()
        self._db_path = Path(os.environ["APPDATA"]) / "SyncDose" / "app.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path.touch(exist_ok=True)
        self._configure_db()

    def _configure_db(self) -> None:
        # Create the tools table if absent; always ensure seed tools exist via
        # INSERT OR IGNORE so the file-sending tool is present even on existing
        # installs that pre-date the seed list (user edits are never overwritten).
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS tools "
                    "(title TEXT PRIMARY KEY, description TEXT,"
                    " icon_path TEXT, is_enabled BOOLEAN)"
                )
                cursor.executemany(
                    "INSERT OR IGNORE INTO tools (title, description, icon_path, is_enabled) "
                    "VALUES (?, ?, ?, ?)",
                    _SEED_TOOLS,
                )

    def id_exists(self, title: str) -> bool:
        """Check whether a tool with the given title exists in the database.

        Args:
            title: The tool title to look up.

        Returns:
            ``True`` if a matching row exists, ``False`` otherwise.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM tools WHERE title = ?", (title,))
                return cursor.fetchone() is not None

    def get_by_id(self, id: str) -> ToolEntity | None:
        """Return the tool with the given title, or ``None`` if absent.

        Args:
            id: The tool title used as the primary key.

        Returns:
            The matching ``ToolEntity``, or ``None`` if not found.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tools WHERE title = ?", (id,))
                row = cursor.fetchone()
                return self._serializer.deserialize(row)

    def get_all(self) -> list[ToolEntity]:
        """Return all stored tools.

        Returns:
            A list of all ``ToolEntity`` objects in the database.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tools")
                rows = cursor.fetchall()
                return [
                    entity
                    for row in rows
                    if (entity := self._serializer.deserialize(row)) is not None
                ]

    def get_all_enabled(self) -> list[ToolEntity]:
        """Return only tools whose ``is_enabled`` flag is set.

        Returns:
            A list of ``ToolEntity`` objects where ``is_enabled`` is ``True``.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tools WHERE is_enabled = 1")
                rows = cursor.fetchall()
                return [
                    entity
                    for row in rows
                    if (entity := self._serializer.deserialize(row)) is not None
                ]

    def save(self, entity: ToolEntity) -> None:
        """Insert or replace a tool and persist to disk.

        Performs an upsert: if a tool with the same title already exists it
        is overwritten; otherwise a new row is inserted.

        Args:
            entity: The tool to persist.

        Emits:
            entity_saved: With the saved entity after the database write.
        """
        with sqlite_connection(self._db_path) as conn:
            row: tuple[str, str, str, bool] | None = self._serializer.serialize(entity)
            if row is None:
                return
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "REPLACE INTO tools (title, description, icon_path, is_enabled) "
                    "VALUES (?, ?, ?, ?)",
                    row,
                )
            self.entity_saved.emit(entity)

    def delete(self, id: str) -> None:
        """Remove a tool by title and emit the deleted signal.

        Args:
            id: The tool title to remove.

        Emits:
            entity_deleted: With ``id`` after the database write, even if no
                matching row existed.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tools WHERE title = ?", (id,))
            self.entity_deleted.emit(id)
