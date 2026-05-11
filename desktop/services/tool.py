"""
Tool service.

Wraps the tool repository and re-emits its mutation signals as
service-level signals so viewmodels never import from repositories/.
"""
import threading

from PySide6.QtCore import QObject, Signal

from domain.entities.tool import ToolEntity
from repositories.tool import ToolRepository


class ToolService(QObject):
    """Service wrapper around :class:`~repositories.tool.ToolRepository`.

    Re-emits repository mutation signals as service-level signals so that
    viewmodels can subscribe without importing from the repositories layer.
    All repository I/O is dispatched on background threads via :meth:`_spawn`
    so the GUI thread is never blocked by SQLite calls.

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
    all_enabled_tools_fetched: Signal = Signal(list)    # list[ToolEntity]

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

        self._threads: list[threading.Thread] = []
        self._is_running: threading.Event = threading.Event()
        self._lifecycle_lock: threading.Lock = threading.Lock()
        self._threads_lock: threading.Lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the service on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a background thread, joining all pending workers."""
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
        self._spawn(self._fetch_all_enabled)

    # ── Private lifecycle ──────────────────────────────────────────────────────

    def _start(self) -> None:
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._is_running.set()

    def _stop(self) -> None:
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            pending_threads: list[threading.Thread] = self._get_pending_threads()
            for t in pending_threads:
                if t == threading.current_thread():
                    continue
                t.join()

    def _spawn(self, target, *args) -> None:
        """All thread creation must go through here."""
        if not self._is_running.is_set():
            return  # reject new spawns during teardown
        t = threading.Thread(target=target, args=args, daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def _get_pending_threads(self) -> list[threading.Thread]:
        threads: list[threading.Thread] = []
        while True:
            with self._threads_lock:
                pending_threads = [t for t in self._threads if t.is_alive()]
                if not pending_threads:
                    return threads
                threads.extend(pending_threads)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _fetch_all_enabled(self) -> None:
        tools = self._repository.get_all_enabled()
        self.all_enabled_tools_fetched.emit(tools)
