"""Shared SQLite connection helper for repositories."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def sqlite_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection to *db_path*, closing it on exit.

    ``sqlite3.Connection`` is itself a context manager, but its
    ``__exit__`` only commits or rolls back the active transaction — it
    never closes the connection or releases the underlying file handle.
    This helper guarantees the connection is closed when the ``with``
    block exits, whether normally or via an exception.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Yields:
        An open ``sqlite3.Connection``. The connection is always closed
        when the context exits. Wrap statements that need
        commit-on-success / rollback-on-exception in a nested
        ``with conn:`` block.
    """
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()
