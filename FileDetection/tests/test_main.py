"""Unit tests for main.py — _init_db, _files_equal, _has_duplicate_hash, check_for_duplicates."""

import sqlite3
from pathlib import Path

import pytest

from main import _files_equal, _has_duplicate_hash, _init_db, check_for_duplicates


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Fresh SQLite database initialised with the files schema."""
    path = tmp_path / "test.db"
    path.touch()  # _init_db calls unlink() before recreating — file must exist
    _init_db(path)
    return path


# ---------------------------------------------------------------------------
# _files_equal
# ---------------------------------------------------------------------------

def test_files_equal_identical_content_returns_true(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"hello world")
    b.write_bytes(b"hello world")
    assert _files_equal(a, b) is True


def test_files_equal_different_content_returns_false(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"hello")
    b.write_bytes(b"world")
    assert _files_equal(a, b) is False


def test_files_equal_empty_files_returns_true(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.touch()
    b.touch()
    assert _files_equal(a, b) is True


def test_files_equal_different_lengths_returns_false(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"short")
    b.write_bytes(b"short but longer")
    assert _files_equal(a, b) is False


def test_files_equal_large_identical_files_returns_true(tmp_path: Path) -> None:
    data = b"x" * (200 * 1024)  # 200 KB — spans multiple 65536-byte chunks
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(data)
    b.write_bytes(data)
    assert _files_equal(a, b) is True


def test_files_equal_large_files_differing_at_end_returns_false(tmp_path: Path) -> None:
    base = b"a" * (200 * 1024)
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(base)
    b.write_bytes(base[:-1] + b"Z")
    assert _files_equal(a, b) is False


# ---------------------------------------------------------------------------
# _init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_files_table(tmp_path: Path) -> None:
    path = tmp_path / "new.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
        ).fetchone()
    assert row is not None


def test_init_db_schema_has_expected_columns(tmp_path: Path) -> None:
    path = tmp_path / "schema.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    assert {"file_path", "file_name", "file_hash"} <= columns


def test_init_db_resets_previously_inserted_data(tmp_path: Path) -> None:
    path = tmp_path / "reset.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO files VALUES ('p', 'n', X'00')")
        conn.commit()
    # Re-init: file exists from sqlite3.connect above, so unlink() succeeds
    _init_db(path)
    with sqlite3.connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# _has_duplicate_hash
# ---------------------------------------------------------------------------

def test_has_duplicate_hash_first_file_returns_none(tmp_path: Path, db_path: Path) -> None:
    f = tmp_path / "unique.bin"
    f.write_bytes(b"unique content abc 12345")
    result = _has_duplicate_hash(db_path, f)
    assert result is None


def test_has_duplicate_hash_first_file_is_inserted(tmp_path: Path, db_path: Path) -> None:
    f = tmp_path / "new.bin"
    f.write_bytes(b"brand new content xyz")
    _has_duplicate_hash(db_path, f)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 1


def test_has_duplicate_hash_second_identical_file_returns_original_path(
    tmp_path: Path, db_path: Path
) -> None:
    f1 = tmp_path / "file1.bin"
    f2 = tmp_path / "file2.bin"
    content = b"same content xyz 99999"
    f1.write_bytes(content)
    f2.write_bytes(content)
    _has_duplicate_hash(db_path, f1)
    result = _has_duplicate_hash(db_path, f2)
    assert result is not None
    result_strs = [str(p) for p in result]
    assert str(f1) in result_strs


def test_has_duplicate_hash_does_not_insert_when_duplicate_found(
    tmp_path: Path, db_path: Path
) -> None:
    f1 = tmp_path / "f1.bin"
    f2 = tmp_path / "f2.bin"
    data = b"duplicate data here"
    f1.write_bytes(data)
    f2.write_bytes(data)
    _has_duplicate_hash(db_path, f1)
    _has_duplicate_hash(db_path, f2)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 1  # only f1 inserted; f2 was not


# ---------------------------------------------------------------------------
# check_for_duplicates
# ---------------------------------------------------------------------------

def test_check_for_duplicates_unique_file_returns_false(tmp_path: Path, db_path: Path) -> None:
    f = tmp_path / "unique.bin"
    f.write_bytes(b"totally unique data 12345 abcde")
    assert check_for_duplicates(db_path, f) is False


def test_check_for_duplicates_exact_duplicate_returns_true(tmp_path: Path, db_path: Path) -> None:
    f1 = tmp_path / "original.bin"
    f2 = tmp_path / "copy.bin"
    content = b"duplicate file content xyz 77777"
    f1.write_bytes(content)
    f2.write_bytes(content)
    check_for_duplicates(db_path, f1)  # registers f1
    assert check_for_duplicates(db_path, f2) is True


def test_check_for_duplicates_registers_first_occurrence(tmp_path: Path, db_path: Path) -> None:
    f = tmp_path / "new.bin"
    f.write_bytes(b"brand new unique content 42")
    check_for_duplicates(db_path, f)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 1
