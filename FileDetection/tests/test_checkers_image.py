"""Unit tests for checkers/image.py — check_image()."""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageFile

from checkers.image import check_image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _write_valid_png(tmp_path: Path, name: str = "valid.png") -> Path:
    path = tmp_path / name
    path.write_bytes(_make_valid_png_bytes())
    return path


def _make_valid_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color=(100, 200, 50)).save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Valid images
# ---------------------------------------------------------------------------

def test_valid_png_returns_false(tmp_path: Path) -> None:
    path = _write_valid_png(tmp_path)
    assert check_image(path) is False


def test_valid_jpeg_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "valid.jpg"
    path.write_bytes(_make_valid_jpeg_bytes())
    assert check_image(path) is False


# ---------------------------------------------------------------------------
# Corrupt / invalid inputs
# ---------------------------------------------------------------------------

def test_empty_file_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "empty.png"
    path.touch()
    assert check_image(path) is True


def test_garbage_bytes_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "garbage.jpg"
    path.write_bytes(b"\x00\x01\x02\x03\x04\x05" * 100)
    assert check_image(path) is True


def test_truncated_png_returns_true(tmp_path: Path) -> None:
    valid_bytes = _make_valid_png_bytes()
    path = tmp_path / "truncated.png"
    path.write_bytes(valid_bytes[:20])
    assert check_image(path) is True


def test_text_file_with_image_extension_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "fake.png"
    path.write_text("this is not an image file")
    assert check_image(path) is True


# ---------------------------------------------------------------------------
# LOAD_TRUNCATED_IMAGES restoration
# ---------------------------------------------------------------------------

def test_load_truncated_images_restored_after_success(tmp_path: Path) -> None:
    original = ImageFile.LOAD_TRUNCATED_IMAGES
    path = _write_valid_png(tmp_path)
    check_image(path)
    assert ImageFile.LOAD_TRUNCATED_IMAGES == original


def test_load_truncated_images_restored_after_failure(tmp_path: Path) -> None:
    original = ImageFile.LOAD_TRUNCATED_IMAGES
    path = tmp_path / "garbage.jpg"
    path.write_bytes(b"not an image at all")
    check_image(path)
    assert ImageFile.LOAD_TRUNCATED_IMAGES == original


def test_load_truncated_images_set_to_false_before_decode(tmp_path: Path) -> None:
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    path = _write_valid_png(tmp_path)
    check_image(path)
    assert ImageFile.LOAD_TRUNCATED_IMAGES is True  # restored to True after call
