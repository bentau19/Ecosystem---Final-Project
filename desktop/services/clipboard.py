"""
Clipboard sync service.

Two-directional clipboard sync between Android and Desktop:

Android → PC  (manual)
    PhoneRequestService detects that Android is waiting on
    CLIPBOARD_ANDROID_TO_PC and calls :meth:`receive`.  The user must
    explicitly press the "Clipboard Sync" button in the Android app.

PC → Android  (automatic)
    MainWindow connects ``QClipboard.dataChanged`` to a thin slot that
    calls :meth:`on_clipboard_changed`.  All sync logic — hash comparison,
    anti-loop guard, and the send decision — lives here in the service,
    not in the View.

Anti-loop guard
---------------
``_last_synced_hash`` (SHA-256) records the last content synced in
*either* direction:

* Android → PC: hash is set inside ``_receive()`` *before* emitting
  ``clipboard_text_received``.  When MainWindow's slot calls setText(),
  Qt fires ``dataChanged`` immediately, but ``on_clipboard_changed``
  will find the hash already matching and skip the echo send.

* PC → Android: hash is updated in ``on_clipboard_changed`` before
  spawning the send thread, so a second ``dataChanged`` for the same
  content is silently dropped.

Architecture note
-----------------
All network I/O runs on daemon background threads.  QClipboard is a Qt
UI object — it must only be touched on the main thread.  This service
never calls QClipboard directly; instead it emits ``clipboard_text_received``
so that a main-thread slot (wired in MainWindow) does the actual setText().
"""
import hashlib
import json
import threading

from PySide6.QtCore import QObject, Signal

from domain.enums.clipboard_channels import ClipboardChannels
from services.connectivity import ConnectivityService


class ClipboardService(QObject):
    """Two-directional clipboard sync service over TauSync.

    Signals:
        clipboard_text_received (Signal[str]): Emitted when Android sends
            plain text.  Connect to a main-thread slot that calls
            ``QApplication.clipboard().setText(text)``.
    """

    # ── Signals ───────────────────────────────────────────────────────────────
    clipboard_text_received: Signal = Signal(str)

    def __init__(
        self,
        connectivity: ConnectivityService,
        parent: QObject | None = None,
    ) -> None:
        """Initialise with the shared connectivity service.

        Args:
            connectivity: Application-level connectivity service;
                ``connectivity.tau`` is accessed per-call so reconnects
                are handled transparently.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._connectivity = connectivity
        self._threads_lock = threading.Lock()
        self._threads: list[threading.Thread] = []

        # SHA-256 digest of the last clipboard content synced in either direction.
        # Updated here — not in the View — so all sync logic stays in one place.
        self._last_synced_hash: str = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def receive(self) -> None:
        """Open the clipboard channel and read incoming content from Android.

        Called by PhoneRequestService when it detects Android is waiting
        on CLIPBOARD_ANDROID_TO_PC.  Spawns a daemon thread so the
        PhoneRequestService poll loop is never blocked.
        """
        t = threading.Thread(target=self._receive, daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def on_clipboard_changed(self, text: str) -> None:
        """React to a PC clipboard change and push to Android if the content is new.

        Called by MainWindow's thin ``_on_clipboard_changed`` slot whenever
        ``QClipboard.dataChanged`` fires.  All sync logic lives here so the
        View stays free of business logic.

        The SHA-256 hash guard prevents echoing back content that just
        arrived *from* Android (``_receive`` pre-sets the hash before
        emitting ``clipboard_text_received``).

        Args:
            text: Current plain-text content of the PC clipboard.
        """
        if not text:
            return
        current_hash = hashlib.sha256(text.encode()).hexdigest()
        if current_hash == self._last_synced_hash:
            print("[ClipboardService] Clipboard sync: ignore — content identical")
            return
        self._last_synced_hash = current_hash
        t = threading.Thread(target=self._send_to_android, args=(text,), daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    # ── Private ───────────────────────────────────────────────────────────────

    def _receive(self) -> None:
        """Background worker: connect, read JSON, emit the appropriate signal."""
        try:
            tau = self._connectivity.tau
            with tau.connect(ClipboardChannels.CLIPBOARD_ANDROID_TO_PC.value) as stream:
                raw = stream.read_all().decode("utf-8")

            payload: dict = json.loads(raw)
            content_type: str = payload.get("type", "")
            content: str = payload.get("content", "")

            if content_type == "text":
                incoming_hash = hashlib.sha256(content.encode()).hexdigest()
                if incoming_hash == self._last_synced_hash:
                    return
                self._last_synced_hash = incoming_hash
                self.clipboard_text_received.emit(content)
            # Future: elif content_type == "image": handle base64 image

        except Exception as exc:
            print(f"[ClipboardService] Error receiving clipboard: {exc}")

    def _send_to_android(self, text: str) -> None:
        """Background worker: connect, write JSON payload, close channel."""
        try:
            payload = json.dumps({"type": "text", "content": text})
            tau = self._connectivity.tau
            with tau.connect(ClipboardChannels.CLIPBOARD_PC_TO_ANDROID.value) as stream:
                stream.write_string(payload)
        except Exception as exc:
            print(f"[ClipboardService] Error sending clipboard to Android: {exc}")
