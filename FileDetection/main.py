import sqlite3
from pathlib import Path

import xxhash


def _init_db(db_path: Path) -> None:
    Path(db_path).unlink()

    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS files
            (
            file_path TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_hash BINARY ( 16)
        )
                       """)
        db.commit()


def _has_duplicate_hash(db_path: Path, file_path: Path) -> list[Path] | None:
    h: xxhash.xxh3_128 = xxhash.xxh3_128()
    #   get from DB

    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(65536), b""):
            h.update(chunk)
    digest: bytes = h.digest()

    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute("""SELECT *
                          FROM files
                          WHERE file_hash = ?""", (digest,))
        rows = cursor.fetchall()
        if not rows:
            file_name: str = file_path.stem
            cursor.execute("""INSERT INTO files (file_path, file_name, file_hash)
                              VALUES (?, ?, ?)""", (str(file_path), file_name, digest))
            db.commit()
            return None
        else:
            return [Path(row[0]) for row in rows]


def _files_equal(file_path1, file_path2):
    chunk = 65536  # 64 KB
    with open(file_path1, 'rb') as file1, open(file_path2, 'rb') as file2:
        while True:
            b1, b2 = file1.read(chunk), file2.read(chunk)
            if b1 != b2:
                return False
            if not b1:
                return True


def check_for_duplicates(db_path: Path, file_path: Path) -> bool:
    duplicates: list[Path] | None = _has_duplicate_hash(db_path, file_path)
    if not duplicates:
        return False
    return any(_files_equal(f, file_path) for f in duplicates)


def main():
    db_path: Path = Path("test.db")
    _init_db(db_path)


if __name__ == '__main__':
    main()
