# ---------------------------------------------------------------------------
# Stage 1 — exact duplicate detection  (files table)
# ---------------------------------------------------------------------------
import sqlite3
from pathlib import Path

import xxhash


def _files_equal(file_path1: Path, file_path2: Path) -> bool:
    # Compare both files in 64 KB chunks so large files never fully load into
    # memory simultaneously. Returns True if every byte matches, False on the
    # first difference or when file lengths differ (a short read on one side
    # makes b1 != b2).
    chunk: int = 65536  # 64 KB
    with open(file_path1, "rb") as file1, open(file_path2, "rb") as file2:
        while True:
            b1, b2 = file1.read(chunk), file2.read(chunk)
            if b1 != b2:
                return False
            if not b1:
                return True


def check_for_duplicates(db_path: Path, file_path: Path, dest_path: Path) -> bool:
    """Check whether *file_path* is a byte-exact copy of an already-registered file.

    Uses a two-step approach for efficiency:

    1. **Fast content-hash lookup** (indexed) — rules out most non-duplicates
       in O(log n) without reading the candidate files.
    2. **Byte-by-byte comparison** against hash-collision candidates — confirms
       true equality and guards against the (astronomically unlikely) collision.

    Candidates whose registered path no longer exists on disk (e.g. discarded
    after a post-copy review) are ignored.

    If no confirmed duplicate is found, *dest_path* (the file's permanent
    save location for this session) is registered for future lookups.

    Args:
        db_path:   Path to the SQLite database.
        file_path: Path to the incoming file to check (e.g. a temp cache file).
        dest_path: Permanent destination path the file will be saved to,
                   registered as this content's identity if not a duplicate.

    Returns:
        ``True`` if a byte-identical copy already exists in the database;
        ``False`` otherwise.
    """
    h: xxhash.xxh3_128 = xxhash.xxh3_128()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    content_digest: bytes = h.digest()

    db = sqlite3.connect(db_path)
    try:
        cursor = db.cursor()
        cursor.execute(
            "SELECT file_path FROM files WHERE file_hash_content = ?",
            (content_digest,),
        )
        candidates = [Path(row[0]) for row in cursor.fetchall()]

        for candidate in candidates:
            if not candidate.exists():
                # Stale registration (file moved/deleted since) — ignore.
                continue
            if _files_equal(candidate, file_path):
                return True

        cursor.execute(
            "INSERT INTO files (file_path, file_name, file_hash_content)"
            " VALUES (?, ?, ?)",
            (str(dest_path), dest_path.stem, content_digest),
        )
        db.commit()
        return False
    finally:
        db.close()
