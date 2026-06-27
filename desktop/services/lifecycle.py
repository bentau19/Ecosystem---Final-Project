"""Shared start/stop lifecycle contract for background services.

Every long-running service in :mod:`services` has the same lifecycle shape: a
public ``start()`` / ``stop()`` that hand off to daemon threads, and an
``is_active`` flag that stays ``True`` from ``start()`` until teardown has fully
finished. Two pieces live here so that shape is declared once:

* :class:`Lifecycle` — the *structural* type the DI root
  (:class:`app.app_state.AppState`) depends on, so it can drive the app-exit
  shutdown poll (``stop_all`` / ``any_active``) without importing any concrete
  service class.
* :class:`LifecycleFlag` — a mixin supplying the ``_stopped`` event plumbing and
  the ``is_active`` property, so each service no longer re-declares the same
  ``threading.Event`` bookkeeping.
"""

import threading
from typing import Protocol, runtime_checkable


@runtime_checkable
class Lifecycle(Protocol):
    """Structural contract for a startable / stoppable background service.

    A service satisfies :class:`Lifecycle` simply by exposing ``start()``,
    ``stop()`` and the ``is_active`` property — no explicit subclassing is
    required. The DI root holds its services as a ``tuple[Lifecycle, ...]`` and
    polls :attr:`is_active` while shutting the application down.
    """

    def start(self) -> None:
        """Start the service (typically on a background thread)."""
        ...

    def stop(self) -> None:
        """Begin teardown; fire-and-forget — :attr:`is_active` reports completion."""
        ...

    @property
    def is_active(self) -> bool:
        """``True`` from ``start()`` until teardown has fully finished."""
        ...


class LifecycleFlag:
    """Mixin providing the shared started/stopped flag for background services.

    Centralises the ``_stopped`` :class:`threading.Event` that each service used
    to declare inline. The flag begins in the *stopped* state (the service is not
    running until ``start()`` is called); a service calls :meth:`_mark_started`
    from its ``_start`` and :meth:`_mark_stopped` once ``_stop`` has fully
    drained. The public :attr:`is_active` reads the flag, satisfying the
    :class:`Lifecycle` contract.

    Use as a plain-``object`` mixin placed *before* ``QObject`` in a service's
    bases. It defines no ``__init__`` — services call :meth:`_init_lifecycle`
    explicitly in their own constructor — which keeps it clear of the
    Qt/Shiboken metaclass and safe to mix into both ``QObject`` and plain
    services.
    """

    _stopped: threading.Event

    def _init_lifecycle(self) -> None:
        # Create the flag in the stopped state (service not yet started).
        self._stopped = threading.Event()
        self._stopped.set()

    def _mark_started(self) -> None:
        # Called from _start once the service is running.
        self._stopped.clear()

    def _mark_stopped(self) -> None:
        # Called from _stop once teardown has fully finished.
        self._stopped.set()

    @property
    def is_active(self) -> bool:
        """``True`` from ``start()`` until ``_stop()`` has fully finished.

        Polled by the app-exit shutdown sequence
        (:meth:`app.app_state.AppState.any_active`).
        """
        return not self._stopped.is_set()
