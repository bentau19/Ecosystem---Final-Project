"""
Three-stage incoming-file pipeline backed by a local SQLite database.

Pipeline
--------
1. **Exact duplicate** — ``check_for_duplicates(db_path, file_path) -> bool``
   Content-hash (xxh3_128) lookup against the ``files`` table.
   Registers every new file seen; rejects byte-identical repeats.

2. **Visual similarity** — ``process_image(db_path, file_path, threshold)``
   dHash + quality-score check against the ``visual_groups`` table.
   Keeps the best-quality representative per perceptual group;
   discards inferior near-duplicates.

3. **ML classification** (future, ``image_classifier.py``)
   Content-based rejection of unwanted images.

Schema
------
::

    files (
        file_path         TEXT  PRIMARY KEY,  -- every file registered (Stage 1)
        file_name         TEXT  NOT NULL,
        file_hash_content BLOB  NOT NULL      -- xxh3_128 digest (16 bytes)
    )
    INDEX idx_content_hash ON files(file_hash_content)

    visual_groups (
        file_hash_visual  INTEGER  PRIMARY KEY,  -- founding dHash = group ID
        best_path         TEXT     NOT NULL,     -- current best image path
        file_name         TEXT     NOT NULL,     -- stem of best image
        quality_score     REAL     NOT NULL      -- composite quality of best
    )
"""

import sqlite3
from pathlib import Path

from file_duplicates import check_for_duplicates
from image_classifer import is_wanted
from similar_photos import process_image


# ---------------------------------------------------------------------------
# DB lifecycle
# ---------------------------------------------------------------------------

def _init_db(db_path: Path) -> None:
    """
    Resets and re-creates the SQLite database at *db_path*.

    Deletes any existing file and creates both the ``files`` table (Stage 1,
    exact-dup detection) and the ``visual_groups`` table (Stage 2, visual-similarity selection).

    Args:
        db_path: Filesystem path for the SQLite file.  Any existing data
                 is discarded.
    """
    Path(db_path).unlink()

    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                file_path         TEXT  PRIMARY KEY,
                file_name         TEXT  NOT NULL,
                file_hash_content BLOB  NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_content_hash ON files(file_hash_content);

            CREATE TABLE IF NOT EXISTS visual_groups (
                file_hash_visual  INTEGER  PRIMARY KEY,
                best_path         TEXT     NOT NULL,
                file_name         TEXT     NOT NULL,
                quality_score     REAL     NOT NULL
            );
        """)
        db.commit()


def main() -> None:
    """Initializes a fresh test database at ``test.db``."""
    db_path: Path = Path("test.db")
    _init_db(db_path)

    file: Path = Path(
        "C:\\Users\\Lavi\\OneDrive - Bar-Ilan University - Students\\Programming\\Projects\\Ecosystem\\FileDetection\\dataset\\test\\filter\\20686.jpg")

    if check_for_duplicates(db_path, file):
        return
    if not is_wanted(file):
        return

    # TODO: handle later after sending file and ect is completed
    # processed_img: tuple[Path, bool, Path | None] = process_image(db_path, file)
    #
    # if not processed_img[1]:
    #     return
    #
    # if processed_img[2] is None:


if __name__ == "__main__":
    main()
