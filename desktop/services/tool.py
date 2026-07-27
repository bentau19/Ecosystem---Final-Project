import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from domain.entities.tool import ToolEntity
from repositories.tool import ToolRepository
from services.lifecycle import LifecycleFlag


class ToolService(LifecycleFlag, QObject):
    """Service wrapper around :class:`~repositories.tool.ToolRepository`.

    Re-emits repository mutation signals as service-level signals so viewmodels
    can subscribe without importing the repositories layer.  Reads and writes go
    against a small in-memory JSON-backed store, so the accessors run inline (no
    background executor is needed to read tools).

    Signals:
        tool_added (Signal[object]): Forwarded from ``ToolRepository.entity_saved``;
            carries the saved :class:`~domain.entities.tool.ToolEntity`.
        tool_deleted (Signal[str]): Forwarded from ``ToolRepository.entity_deleted``;
            carries the deleted tool's title.
    """

    tool_added: Signal = Signal(object)
    tool_deleted: Signal = Signal(str)

    def __init__(
            self,
            repository: ToolRepository,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the service and wire repository mutation signals.

        Args:
            repository: The shared :class:`~repositories.tool.ToolRepository`.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._repository: ToolRepository = repository
        self._repository.entity_saved.connect(self.tool_added)
        self._repository.entity_deleted.connect(self.tool_deleted)

        # Retained so the service satisfies the Lifecycle protocol used by the
        # app-exit shutdown poll; there is no background work to run.
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._is_running: threading.Event = threading.Event()
        self._init_lifecycle()
        self._lifecycle_lock: threading.Lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a daemon thread (fire-and-forget)."""
        threading.Thread(target=self._stop, daemon=True).start()

    # ── Reads / writes (synchronous — the store is in-memory) ───────────────────

    def get_all(self) -> list[ToolEntity]:
        """Return all stored tools."""
        return self._repository.get_all()

    def get_by_id(self, title: str) -> ToolEntity | None:
        """Return the tool with the given title, or ``None`` if absent."""
        return self._repository.get_by_id(title)

    def save_tool(self, entity: ToolEntity) -> None:
        """Persist a tool (upsert keyed on title).

        Emits:
            tool_added: Forwarded from the repository after the write.
        """
        self._repository.save(entity)

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _start(self) -> None:
        # Guard against double-start with the lifecycle lock.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._is_running.set()
            self._mark_started()

    def _stop(self) -> None:
        # Clear the running flag then release the executor.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            executor = self._executor
            executor.shutdown(wait=True, cancel_futures=True)
            self._mark_stopped()
