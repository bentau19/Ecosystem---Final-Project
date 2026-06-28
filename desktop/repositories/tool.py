import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from domain.entities.tool import ToolEntity
from domain.tool_catalog import SEED_TOOLS
from repositories.repository import IRepository
from serializers.tool import ToolSerializer
from utils.meta import ABCQObjectMeta
from utils.paths import data_dir


class ToolRepository(
    IRepository[ToolEntity, str], QObject, metaclass=ABCQObjectMeta
):
    """Repository for tool entities backed by a JSON file (``tools.json``).

    The whole tool list lives in a single JSON array on disk.  It is loaded
    into an in-memory dict (keyed by title) on construction and re-written
    atomically — via a ``.tmp`` sibling renamed over the real file — on every
    mutation, so a crash mid-write never leaves a corrupt file.  A lock guards
    mutations because ``ToolService`` submits calls on a ``ThreadPoolExecutor``.
    Seed tools are ensured present on construction.

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
            path: Path | None = None,
    ) -> None:
        """Initialize the repository, load the tools file, and seed defaults.

        Args:
            parent: Optional Qt parent object.
            path: Optional override for the ``tools.json`` location (used by
                tests). Defaults to ``data_dir() / "tools.json"``.
        """
        super().__init__(parent)
        self._serializer = ToolSerializer()
        self._path: Path = path if path is not None else data_dir() / "tools.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tools: dict[str, ToolEntity] = self._load()
        self._seed()

    # ── Persistence helpers ──────────────────────────────────────────────────

    def _load(self) -> dict[str, ToolEntity]:
        # Read and deserialize the tool list; a missing or corrupt file yields
        # an empty store rather than crashing the app.
        try:
            if not self._path.exists():
                return {}
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return {}
        tools: dict[str, ToolEntity] = {}
        if isinstance(raw, list):
            for item in raw:
                entity = self._serializer.deserialize(item)
                if entity is not None:
                    tools[entity.title] = entity
        return tools

    def _flush(self) -> None:
        # Atomically write the in-memory tools back to disk.  Best-effort: a
        # read-only path or full disk is swallowed rather than crashing the UI.
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(
                    [self._serializer.serialize(t) for t in self._tools.values()],
                    fh,
                    indent=2,
                )
            tmp.replace(self._path)
        except OSError:
            pass

    def _seed(self) -> None:
        # Ensure each seed tool exists; never overwrites an existing title.
        with self._lock:
            changed = False
            for tool in SEED_TOOLS:
                if tool.title not in self._tools:
                    self._tools[tool.title] = tool
                    changed = True
            if changed:
                self._flush()

    # ── Public API ───────────────────────────────────────────────────────────

    def id_exists(self, title: str) -> bool:
        """Check whether a tool with the given title exists.

        Args:
            title: The tool title to look up.

        Returns:
            ``True`` if a matching tool exists, ``False`` otherwise.
        """
        with self._lock:
            return title in self._tools

    def get_by_id(self, id: str) -> ToolEntity | None:
        """Return the tool with the given title, or ``None`` if absent.

        Args:
            id: The tool title used as the primary key.

        Returns:
            The matching ``ToolEntity``, or ``None`` if not found.
        """
        with self._lock:
            return self._tools.get(id)

    def get_all(self) -> list[ToolEntity]:
        """Return all stored tools.

        Returns:
            A list of all ``ToolEntity`` objects.
        """
        with self._lock:
            return list(self._tools.values())

    def get_all_enabled(self) -> list[ToolEntity]:
        """Return only tools whose ``is_enabled`` flag is set.

        Returns:
            A list of ``ToolEntity`` objects where ``is_enabled`` is ``True``.
        """
        with self._lock:
            return [t for t in self._tools.values() if t.is_enabled]

    def save(self, entity: ToolEntity) -> None:
        """Insert or replace a tool and persist to disk.

        Performs an upsert keyed on ``title``: an existing tool with the same
        title is overwritten; otherwise the tool is added.

        Args:
            entity: The tool to persist.

        Emits:
            entity_saved: With the saved entity after the file write.
        """
        if entity is None:
            return
        with self._lock:
            self._tools[entity.title] = entity
            self._flush()
        self.entity_saved.emit(entity)

    def delete(self, id: str) -> None:
        """Remove a tool by title and emit the deleted signal.

        Args:
            id: The tool title to remove.

        Emits:
            entity_deleted: With ``id`` after the file write, even if no
                matching tool existed.
        """
        with self._lock:
            self._tools.pop(id, None)
            self._flush()
        self.entity_deleted.emit(id)
