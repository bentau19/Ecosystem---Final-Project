"""
Unit tests for main.py.

Covers: _init_db, _files_equal, _has_duplicate_hash, check_for_duplicates,
        process_image, find_similar_in_db.
"""

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from main import (
    _files_equal,
    _has_duplicate_hash,
    _init_db,
    check_for_duplicates,
    find_similar_in_db,
    process_image,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Fresh SQLite database initialised with both tables."""
    path = tmp_path / "test.db"
    path.touch()  # _init_db calls unlink() before recreating — file must exist
    _init_db(path)
    return path


@pytest.fixture
def sample_png(tmp_path: Path) -> Path:
    """Minimal valid 16×16 RGB PNG."""
    path = tmp_path / "sample.png"
    Image.new("RGB", (16, 16), color=(128, 64, 32)).save(path)
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
# _init_db — files table
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


def test_init_db_files_schema_has_expected_columns(tmp_path: Path) -> None:
    path = tmp_path / "schema.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    assert {"file_path", "file_name", "file_hash_content"} <= columns


def test_init_db_resets_previously_inserted_data(tmp_path: Path) -> None:
    path = tmp_path / "reset.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO files VALUES ('p', 'n', X'00')")
        conn.commit()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 0


def test_init_db_creates_content_hash_index(tmp_path: Path) -> None:
    path = tmp_path / "idx.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='index' AND name='idx_content_hash'"
        ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# _init_db — visual_groups table
# ---------------------------------------------------------------------------

def test_init_db_creates_visual_groups_table(tmp_path: Path) -> None:
    path = tmp_path / "vg.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='visual_groups'"
        ).fetchone()
    assert row is not None


def test_init_db_visual_groups_schema_has_expected_columns(tmp_path: Path) -> None:
    path = tmp_path / "vg_schema.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(visual_groups)").fetchall()
        }
    assert {"file_hash_visual", "best_path", "file_name", "quality_score"} <= columns


def test_init_db_resets_visual_groups_on_reinit(tmp_path: Path) -> None:
    path = tmp_path / "vg_reset.db"
    path.touch()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO visual_groups VALUES (999, '/p', 'p', 1.0)")
        conn.commit()
    _init_db(path)
    with sqlite3.connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM visual_groups").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# _has_duplicate_hash
# ---------------------------------------------------------------------------

def test_has_duplicate_hash_first_file_returns_none(tmp_path: Path, db_path: Path) -> None:
    f = tmp_path / "unique.bin"
    f.write_bytes(b"unique content abc 12345")
    assert _has_duplicate_hash(db_path, f) is None


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
    assert str(f1) in [str(p) for p in result]


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
    check_for_duplicates(db_path, f1)
    assert check_for_duplicates(db_path, f2) is True


def test_check_for_duplicates_registers_first_occurrence(tmp_path: Path, db_path: Path) -> None:
    f = tmp_path / "new.bin"
    f.write_bytes(b"brand new unique content 42")
    check_for_duplicates(db_path, f)
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# process_image
# ---------------------------------------------------------------------------

def test_process_image_first_image_creates_new_group(
    tmp_path: Path, db_path: Path, sample_png: Path
) -> None:
    winner, is_new_best, displaced = process_image(db_path, sample_png)
    assert is_new_best is True
    assert winner == sample_png
    assert displaced is None
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM visual_groups").fetchone()[0]
    assert count == 1


def test_process_image_unreadable_returns_rejected(tmp_path: Path, db_path: Path) -> None:
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    winner, is_new_best, displaced = process_image(db_path, bad)
    assert is_new_best is False
    assert displaced is None
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM visual_groups").fetchone()[0]
    assert count == 0


def test_process_image_dissimilar_image_creates_separate_group(tmp_path: Path, db_path: Path) -> None:
    # Solid grey vs. full-gradient — very different dHashes
    solid = tmp_path / "solid.png"
    Image.new("RGB", (64, 64), (128, 128, 128)).save(solid)

    gradient_img = Image.new("L", (64, 64))
    gradient_img.putdata([int(255 * x / 63) for _ in range(64) for x in range(64)])
    gradient = tmp_path / "gradient.png"
    gradient_img.convert("RGB").save(gradient)

    process_image(db_path, solid)
    winner, is_new_best, displaced = process_image(db_path, gradient)
    assert is_new_best is True
    assert displaced is None
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM visual_groups").fetchone()[0]
    assert count == 2


def test_process_image_inferior_similar_image_is_rejected(tmp_path: Path, db_path: Path) -> None:
    """Identical pixels → same dHash, same quality; second call is rejected."""
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    Image.new("RGB", (64, 64), (100, 100, 100)).save(img_a)
    Image.new("RGB", (64, 64), (100, 100, 100)).save(img_b)  # same pixels

    process_image(db_path, img_a)
    winner, is_new_best, displaced = process_image(db_path, img_b)

    # same quality score → b does NOT beat a (> not >=)
    assert is_new_best is False
    assert winner == img_a
    assert displaced is None
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM visual_groups").fetchone()[0]
    assert count == 1


def test_process_image_better_image_replaces_existing_and_returns_displaced(
    tmp_path: Path, db_path: Path
) -> None:
    """Higher-resolution image of same scene wins; displaced path returned."""
    small = tmp_path / "small.png"
    large = tmp_path / "large.png"
    # Same solid colour → same dHash; large has more pixels → higher resolution score
    Image.new("RGB", (8, 8),    (90, 90, 90)).save(small)
    Image.new("RGB", (200, 200), (90, 90, 90)).save(large)

    process_image(db_path, small)
    winner, is_new_best, displaced = process_image(db_path, large)

    assert is_new_best is True
    assert winner == large
    assert displaced == small  # small was the old best — caller should delete it

    # DB reflects the new best
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT best_path FROM visual_groups").fetchone()
    assert row is not None
    assert Path(row[0]) == large


# ---------------------------------------------------------------------------
# find_similar_in_db
# ---------------------------------------------------------------------------

def test_find_similar_in_db_empty_db_returns_empty(db_path: Path) -> None:
    assert find_similar_in_db(db_path) == []


def test_find_similar_in_db_single_image_returns_one_group(
    tmp_path: Path, db_path: Path, sample_png: Path
) -> None:
    process_image(db_path, sample_png)
    groups = find_similar_in_db(db_path)
    assert len(groups) == 1
    assert sample_png in groups[0]


def test_find_similar_in_db_two_dissimilar_images_two_groups(
    tmp_path: Path, db_path: Path
) -> None:
    solid = tmp_path / "solid.png"
    Image.new("RGB", (64, 64), (128, 128, 128)).save(solid)

    gradient_img = Image.new("L", (64, 64))
    gradient_img.putdata([int(255 * x / 63) for _ in range(64) for x in range(64)])
    gradient = tmp_path / "gradient.png"
    gradient_img.convert("RGB").save(gradient)

    process_image(db_path, solid)
    process_image(db_path, gradient)

    groups = find_similar_in_db(db_path)
    assert len(groups) == 2
