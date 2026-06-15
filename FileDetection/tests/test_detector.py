"""Unit tests for detector.py — is_corrupt() and _is_empty_or_unreadable()."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from detector import _is_empty_or_unreadable, is_corrupt


# ---------------------------------------------------------------------------
# is_corrupt
# ---------------------------------------------------------------------------

def test_is_corrupt_nonexistent_path_returns_true(tmp_path: Path) -> None:
    result = is_corrupt(tmp_path / "ghost.jpg")
    assert result is True


def test_is_corrupt_empty_file_returns_true(tmp_path: Path) -> None:
    f = tmp_path / "empty.jpg"
    f.touch()
    assert is_corrupt(f) is True


def test_is_corrupt_unknown_extension_nonempty_returns_false(tmp_path: Path) -> None:
    f = tmp_path / "file.xyz"
    f.write_bytes(b"some content here")
    assert is_corrupt(f) is False


def test_is_corrupt_delegates_to_checker_returning_true(tmp_path: Path) -> None:
    f = tmp_path / "image.jpg"
    f.write_bytes(b"fake jpg content")
    mock_checker = MagicMock(return_value=True)
    with patch("detector.get_checker", return_value=mock_checker):
        result = is_corrupt(f)
    assert result is True
    mock_checker.assert_called_once_with(f)


def test_is_corrupt_delegates_to_checker_returning_false(tmp_path: Path) -> None:
    f = tmp_path / "image.jpg"
    f.write_bytes(b"fake jpg content")
    mock_checker = MagicMock(return_value=False)
    with patch("detector.get_checker", return_value=mock_checker):
        result = is_corrupt(f)
    assert result is False
    mock_checker.assert_called_once_with(f)


def test_is_corrupt_no_checker_for_extension_returns_false(tmp_path: Path) -> None:
    f = tmp_path / "archive.tar"
    f.write_bytes(b"tar data")
    with patch("detector.get_checker", return_value=None):
        result = is_corrupt(f)
    assert result is False


# ---------------------------------------------------------------------------
# _is_empty_or_unreadable
# ---------------------------------------------------------------------------

def test_is_empty_or_unreadable_nonexistent_path_returns_true(tmp_path: Path) -> None:
    result = _is_empty_or_unreadable(tmp_path / "missing.txt")
    assert result is True


def test_is_empty_or_unreadable_zero_byte_file_returns_true(tmp_path: Path) -> None:
    f = tmp_path / "zero.txt"
    f.touch()
    assert _is_empty_or_unreadable(f) is True


def test_is_empty_or_unreadable_nonempty_file_returns_false(tmp_path: Path) -> None:
    f = tmp_path / "data.txt"
    f.write_bytes(b"hello")
    assert _is_empty_or_unreadable(f) is False


def test_is_empty_or_unreadable_single_byte_file_returns_false(tmp_path: Path) -> None:
    f = tmp_path / "one.bin"
    f.write_bytes(b"\x00")
    assert _is_empty_or_unreadable(f) is False
