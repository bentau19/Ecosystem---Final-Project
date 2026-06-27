import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from domain.entities.tool import ToolEntity
from repositories.tool import ToolRepository
from services.lifecycle import LifecycleFlag


class ToolService(LifecycleFlag, QObject):
    """Service wrapper around :class:`~repositories.tool.ToolRepository`.

    Re-emits repository mutation signals as service-level signals so that
    viewmodels can subscribe without importing from the repositories layer.
    All repository I/O is submitted to :attr:`_executor` so the GUI thread
    is never blocked by SQLite calls.

    Signals:
        tool_added (Signal[object]): Forwarded from
            ``ToolRepository.entity_saved``; carries the saved
            :class:`~domain.entities.tool.ToolEntity`.
        tool_deleted (Signal[str]): Forwarded from
            ``ToolRepository.entity_deleted``; carries the deleted tool's
            title string.
        all_enabled_tools_fetched (Signal[list]): Emitted with
            ``list[ToolEntity]`` when :meth:`fetch_all_enabled` completes.
    """

    tool_added: Signal = Signal(object)
    tool_deleted: Signal = Signal(str)
    all_enabled_tools_fetched: Signal = Signal(list)  # list[ToolEntity]

    def __init__(
            self,
            repository: ToolRepository,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the service and wire repository mutation signals.

        The background worker infrastructure is set up here but the service
        is not started automatically.  Call :meth:`start` explicitly (e.g.
        from ``ToolViewModel.__init__``) before calling :meth:`fetch_all_enabled`.

        Args:
            repository: The shared :class:`~repositories.tool.ToolRepository`
                instance from the application's DI root.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._repository: ToolRepository = repository
        self._repository.entity_saved.connect(self.tool_added)
        self._repository.entity_deleted.connect(self.tool_deleted)

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

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_all_enabled(self) -> None:
        """Fetch all enabled tools on a background thread.

        Gated on :attr:`_is_running` — call :meth:`start` before invoking
        this method (``ToolViewModel`` does so during construction).

        Emits:
            all_enabled_tools_fetched: With the list of
                :class:`~domain.entities.tool.ToolEntity` objects whose
                ``is_enabled`` flag is ``True``.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._fetch_all_enabled)

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
        # Clear the running flag then wait for all submitted work to finish.
        # The executor reference is captured inside the lock so a concurrent
        # _start() (which swaps self._executor) can never have its fresh pool
        # shut down by this stop.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            executor = self._executor
            executor.shutdown(wait=True, cancel_futures=True)
            self._mark_stopped()

    def _fetch_all_enabled(self) -> None:
        # Retrieve enabled tools from the repository and emit the result.
        tools = self._repository.get_all_enabled()
        self.all_enabled_tools_fetched.emit(tools)
