"""Value objects and registries for VirtualDriveService read/write sessions.

:class:`~services.virtual_drive.VirtualDriveService` keeps one long-lived
TauSync stream per open file handle (streaming reads) and per in-progress write.
Each kind of session bundles a few correlated pieces of state — a stream, a
timestamp, and for reads a per-stream lock. Modelling each as a dataclass and
keeping the add/lookup/drop/reap logic (and its locking) inside a small registry
replaces what were three hand-synchronised parallel dicts on the service, so the
"these must stay in sync" invariant is enforced in exactly one place.
"""

import threading
from dataclasses import dataclass, field
from typing import Any


def _safe_close(stream: Any) -> None:
    # Best-effort stream close; teardown paths must never raise.
    try:
        stream.close()
    except Exception:
        pass


@dataclass
class ReadSession:
    """One persistent virtual-drive read channel.

    Attributes:
        stream: The open TauSync stream the file's bytes are read from.
        lock: Serialises request/response framing on :attr:`stream` —
            foreground reads and background prefetch share the one stream, so
            only a single exchange may be in flight at a time.
        last_active: ``time.monotonic()`` of the most recent read, consulted by
            the idle reaper.
    """

    stream: Any
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_active: float = 0.0


@dataclass
class WriteSession:
    """One in-progress virtual-drive write channel.

    Attributes:
        stream: The open TauSync stream chunks are written into; closing it
            signals Android to rename the temp file to its final path.
        lock: Serialises appends to :attr:`stream`. WinFsp dispatches Write
            callbacks on several threads at once, and the stream is a single
            append-only pipe, so two concurrent chunks would interleave.
        next_offset: File offset the next chunk must start at. Android writes
            the temp file through a sequential ``FileOutputStream`` and cannot
            seek, so a chunk arriving out of order would land at the wrong place
            with no error — tracking the expected offset turns that into a
            refusal instead of a corrupt file.
        started_at: ``time.monotonic()`` when the session opened, consulted by
            the age reaper.
    """

    stream: Any
    lock: threading.Lock = field(default_factory=threading.Lock)
    next_offset: int = 0
    started_at: float = 0.0


class ReadSessionRegistry:
    """Thread-safe registry of :class:`ReadSession` keyed by session id.

    Owns its own lock so a session's stream, per-stream lock, and activity
    timestamp can never drift out of sync. Every mutating method is idempotent.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._sessions: dict[str, ReadSession] = {}

    def add(self, session_id: str, stream: Any, now: float) -> ReadSession:
        """Register a freshly opened *stream* under *session_id* and return it."""
        session = ReadSession(stream=stream, last_active=now)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ReadSession | None:
        """Return the session for *session_id*, or ``None`` if unknown."""
        with self._lock:
            return self._sessions.get(session_id)

    def touch(self, session_id: str, now: float) -> None:
        """Record read activity so the idle reaper leaves an active session alone."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_active = now

    def drop(self, session_id: str) -> bool:
        """Remove and close *session_id*'s stream. Returns ``True`` if it existed."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        _safe_close(session.stream)
        return True

    def stale(self, now: float, idle_timeout: float) -> list[str]:
        """Return ids whose last read is older than *idle_timeout* seconds."""
        with self._lock:
            return [
                sid for sid, session in self._sessions.items()
                if now - session.last_active > idle_timeout
            ]

    def close_all(self) -> None:
        """Close and forget every session (called on service stop)."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            _safe_close(session.stream)

    def __contains__(self, session_id: object) -> bool:
        with self._lock:
            return session_id in self._sessions


class WriteSessionRegistry:
    """Thread-safe registry of :class:`WriteSession` keyed by destination path.

    Mirrors :class:`ReadSessionRegistry` for the write path (the key is the
    file path and the reaper measures total age rather than idle time). Every
    mutating method is idempotent.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._sessions: dict[str, WriteSession] = {}

    def add(self, path: str, stream: Any, now: float) -> WriteSession:
        """Register a freshly opened write *stream* for *path* and return it."""
        session = WriteSession(stream=stream, started_at=now)
        with self._lock:
            self._sessions[path] = session
        return session

    def get(self, path: str) -> WriteSession | None:
        """Return the write session for *path*, or ``None`` if unknown."""
        with self._lock:
            return self._sessions.get(path)

    def drop(self, path: str) -> bool:
        """Remove and close *path*'s stream. Returns ``True`` if it existed."""
        with self._lock:
            session = self._sessions.pop(path, None)
        if session is None:
            return False
        _safe_close(session.stream)
        return True

    def stale(self, now: float, age_timeout: float) -> list[str]:
        """Return paths whose session has been open longer than *age_timeout* seconds."""
        with self._lock:
            return [
                path for path, session in self._sessions.items()
                if now - session.started_at > age_timeout
            ]

    def close_all(self) -> None:
        """Close and forget every session (called on service stop)."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            _safe_close(session.stream)

    def __contains__(self, path: object) -> bool:
        with self._lock:
            return path in self._sessions
