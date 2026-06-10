import sqlite3
import threading
from pathlib import Path

from PIL import Image

from file_duplicates import check_for_duplicates
from image_classifer import ClassificationResult, ClassificationVerdict, classify_image


class Classifier:
    """Three-stage incoming-file screening pipeline backed by a local SQLite database.

    Pipeline:
        1. **Exact duplicate** — ``check_for_duplicates(db_path, file_path, dest_path) -> bool``.
           Content-hash (xxh3_128) lookup against the ``files`` table.
           Registers every new file seen; rejects byte-identical repeats.

        2. **Visual similarity** — ``process_image(db_path, file_path, threshold)``.
           dHash + quality-score check against the ``visual_groups`` table.
           Keeps the best-quality representative per perceptual group;
           discards inferior near-duplicates.

        3. **ML confidence** (``image_classifer.py``).
           Content-based screening of unwanted images via :func:`classify_image`.
           Three outcomes are possible, surfaced through
           :class:`ClassificationVerdict`:

           * ``pr(remove) > 0.95`` → :attr:`ClassificationVerdict.REJECTED`
           * ``0.5 < pr(remove) <= 0.95`` (argmax says "remove" but unsure) →
             :attr:`ClassificationVerdict.NEEDS_REVIEW` — the caller should
             ask the user whether to keep or discard the file.
           * ``pr(remove) <= 0.5`` → :attr:`ClassificationVerdict.ACCEPTED`

    Schema::

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

    def __init__(self, db_path: Path) -> None:
        """Initialize the classifier and (re)create its SQLite database.

        Args:
            db_path: Filesystem path for the SQLite database file. Any
                existing file at this path is deleted and recreated.
        """
        self.db_path: Path = db_path
        self._db_lock: threading.Lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        # Delete any existing file at db_path and recreate it with both the
        # "files" table (Stage 1, exact-dup detection) and the
        # "visual_groups" table (Stage 2, visual-similarity selection).
        with self._db_lock:
            if self.db_path.exists():
                Path(self.db_path).unlink()

            db = sqlite3.connect(self.db_path)

            try:
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
            finally:
                db.close()

    @staticmethod
    def _is_image(path: Path) -> bool:
        try:
            with Image.open(path) as img:
                img.verify()  # Verify image integrity
            return True
        except Exception:
            return False

    def classify(self, file: Path, dest_path: Path, use_ml: bool = False) -> ClassificationResult:
        """Run *file* through the screening pipeline.

        Args:
            file: Path to the cached incoming file.
            dest_path: Permanent destination path the file will be saved to,
                registered as this content's identity if not a duplicate.
            use_ml: Whether to run the ML image classifier (stage 3). When
                ``False``, only the exact-duplicate check (stage 1) runs.

        Returns:
            A :class:`ClassificationResult` whose ``verdict`` is
            :attr:`ClassificationVerdict.ACCEPTED` if the file should be saved,
            :attr:`ClassificationVerdict.REJECTED` if it should be discarded
            (duplicate, or confidently unwanted), or
            :attr:`ClassificationVerdict.NEEDS_REVIEW` if the ML classifier's
            argmax favors "remove" but isn't confident enough — the caller
            should ask the user. ``confidence`` carries ``pr(remove)`` when
            the ML stage ran, otherwise ``0.0``.
        """
        with self._db_lock:
            if check_for_duplicates(self.db_path, file, dest_path):
                return ClassificationResult(ClassificationVerdict.REJECTED, 0)
        if not use_ml:
            return ClassificationResult(ClassificationVerdict.ACCEPTED, 0)
        if self._is_image(file):
            result = classify_image(file)
            if result.verdict is ClassificationVerdict.REJECTED:
                return ClassificationResult(ClassificationVerdict.REJECTED, result.confidence)
            if result.verdict is ClassificationVerdict.NEEDS_REVIEW:
                return ClassificationResult(ClassificationVerdict.NEEDS_REVIEW, result.confidence)
        return ClassificationResult(ClassificationVerdict.ACCEPTED, 0)
