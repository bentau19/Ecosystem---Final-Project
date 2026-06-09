# ---------------------------------------------------------------------------
# Stage 1 — exact duplicate detection  (files table)
# ---------------------------------------------------------------------------
import sqlite3
from pathlib import Path

import xxhash


def _has_duplicate_hash(db_path: Path, file_path: Path) -> list[Path] | None:
    """
    Checks whether any row in ``files`` shares the content hash of *file_path*.

    If no match is found the file is inserted and ``None`` is returned.
    If one or more matches exist their paths are returned so the caller can
    confirm byte equality via ``_files_equal``.

    The content-hash lookup hits ``idx_content_hash`` — O(log n).

    Args:
        db_path:   Path to the SQLite database.
        file_path: Path to the file being checked.

    Returns:
        ``None`` if the file was not a duplicate (it has been inserted).
        A non-empty list of ``Path`` objects for every file that shares the
        same content hash.
    """
    h: xxhash.xxh3_128 = xxhash.xxh3_128()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    content_digest: bytes = h.digest()

    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute(
            "SELECT file_path FROM files WHERE file_hash_content = ?",
            (content_digest,),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                "INSERT INTO files (file_path, file_name, file_hash_content)"
                " VALUES (?, ?, ?)",
                (str(file_path), file_path.stem, content_digest),
            )
            db.commit()
            return None
        return [Path(row[0]) for row in rows]


def _files_equal(file_path1: Path, file_path2: Path) -> bool:
    """
    Returns ``True`` if both files have identical byte contents.

    Reads both files in 64 KB chunks so large files never fully load into
    memory simultaneously.

    Args:
        file_path1: Path to the first file.
        file_path2: Path to the second file.

    Returns:
        ``True`` if every byte matches; ``False`` on the first difference or
        when file lengths differ.
    """
    chunk: int = 65536  # 64 KB
    with open(file_path1, "rb") as file1, open(file_path2, "rb") as file2:
        while True:
            b1, b2 = file1.read(chunk), file2.read(chunk)
            if b1 != b2:
                return False
            if not b1:
                return True


def check_for_duplicates(db_path: Path, file_path: Path) -> bool:
    """
    Returns ``True`` if *file_path* is a byte-exact copy of an already-registered file.

    Uses a two-step approach for efficiency:

    1. **Fast content-hash lookup** (indexed) — rules out most non-duplicates
       in O(log n) without reading the candidate files.
    2. **Byte-by-byte comparison** against hash-collision candidates — confirms
       true equality and guards against the (astronomically unlikely) collision.

    Args:
        db_path:   Path to the SQLite database.
        file_path: Path to the incoming file to check.

    Returns:
        ``True`` if a byte-identical copy already exists in the database;
        ``False`` otherwise.
    """
    duplicates: list[Path] | None = _has_duplicate_hash(db_path, file_path)
    if not duplicates:
        return False
    return any(_files_equal(f, file_path) for f in duplicates)
