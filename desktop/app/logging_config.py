import logging
import logging.handlers
import os
import sys
from pathlib import Path


def configure_logging() -> None:
    """Configure application-wide logging for SyncDose.

    Sets up two handlers on the root logger:

    * A :class:`~logging.handlers.RotatingFileHandler` writing ``DEBUG``+
      messages to ``syncdose.log`` (5 MB per file, 3 backups kept).
      - Frozen build: ``%APPDATA%\\SyncDose\\syncdose.log`` (always writable).
      - Dev (source): ``desktop/data/syncdose.log`` (easy to inspect locally).
    * A :class:`~logging.StreamHandler` writing ``INFO``+ to the console so
      developers get concise output without every debug trace.

    The root logger is set to ``DEBUG`` so the per-handler levels above are what
    actually decide what is written. It must not be raised to ``INFO``: the root
    level filters records *before* any handler sees them, so an ``INFO`` root
    silently discards every ``DEBUG`` record and the file handler's ``DEBUG``
    level becomes unreachable — which is exactly how the virtual drive's per-op
    ``req:``/``resp:`` traces went missing when a failure needed diagnosing.
    Set ``SYNCDOSE_LOG_LEVEL=INFO`` to opt back into a quiet log.

    Idempotent — if the root logger already has handlers attached (e.g. the
    function is called twice during testing) the second call is a no-op.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    level_name = os.environ.get("SYNCDOSE_LOG_LEVEL", "DEBUG").upper()
    root.setLevel(getattr(logging, level_name, logging.DEBUG))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Rotating file handler ─────────────────────────────────────────────────
    # Frozen (PyInstaller): write to %APPDATA%\SyncDose\ which is always
    # writable without admin rights.  Source dev: write to desktop/data/ so
    # logs are easy to find next to the code.
    if getattr(sys, "frozen", False):
        log_path = Path(os.environ["APPDATA"]) / "SyncDose" / "syncdose.log"
    else:
        log_path = Path(__file__).parent.parent / "data" / "syncdose.log"
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
