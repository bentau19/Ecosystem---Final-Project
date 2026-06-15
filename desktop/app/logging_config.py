import logging
import logging.handlers
from pathlib import Path


def configure_logging() -> None:
    """Configure application-wide logging for SyncDose.

    Sets up two handlers on the root logger:

    * A :class:`~logging.handlers.RotatingFileHandler` writing ``DEBUG``+
      messages to ``data/syncdose.log`` (5 MB per file, 3 backups kept).
    * A :class:`~logging.StreamHandler` writing ``INFO``+ to the console so
      developers get concise output without every debug trace.

    Idempotent — if the root logger already has handlers attached (e.g. the
    function is called twice during testing) the second call is a no-op.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Rotating file handler ─────────────────────────────────────────────────
    log_path = Path(__file__).resolve().parent.parent / "data" / "syncdose.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
