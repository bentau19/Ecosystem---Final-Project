"""Unit tests for checkers/zip_based.py — check_zip()."""

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from checkers.zip_based import check_zip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_zip(tmp_path: Path, name: str = "valid.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("hello.txt", "hello world")
    return path


# ---------------------------------------------------------------------------
# Valid ZIPs
# ---------------------------------------------------------------------------

def test_valid_zip_single_entry_returns_false(tmp_path: Path) -> None:
    path = _make_valid_zip(tmp_path)
    assert check_zip(path) is False


def test_valid_zip_multiple_entries_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "multi.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.txt", "aaa")
        zf.writestr("b.txt", "bbb")
        zf.writestr("nested/c.txt", "ccc")
    assert check_zip(path) is False


def test_valid_zip_no_entries_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "empty_entries.zip"
    with zipfile.ZipFile(path, "w"):
        pass
    assert check_zip(path) is False


# ---------------------------------------------------------------------------
# Corrupt / invalid ZIPs
# ---------------------------------------------------------------------------

def test_empty_file_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "empty.zip"
    path.touch()
    assert check_zip(path) is True


def test_garbage_bytes_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "garbage.zip"
    path.write_bytes(b"\x00\xff\xaa\xbb" * 50)
    assert check_zip(path) is True


def test_nonexistent_path_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "missing.zip"
    assert check_zip(path) is True


def test_bad_crc_returns_true(tmp_path: Path) -> None:
    path = _make_valid_zip(tmp_path, "bad_crc.zip")
    with patch.object(zipfile, "ZipFile") as MockZipFile:
        ctx = MockZipFile.return_value.__enter__.return_value
        ctx.testzip.return_value = "corrupt_entry.txt"
        result = check_zip(path)
    assert result is True


def test_truncated_zip_returns_true(tmp_path: Path) -> None:
    valid = _make_valid_zip(tmp_path, "original.zip")
    truncated = tmp_path / "truncated.zip"
    truncated.write_bytes(valid.read_bytes()[:10])
    assert check_zip(truncated) is True
