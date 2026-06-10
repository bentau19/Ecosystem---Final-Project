"""Unit tests for similar_photos.py — _dhash() and _hamming_distance()."""

from pathlib import Path

from PIL import Image

from similar_photos import (
    _dhash,
    _hamming_distance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_solid_png(path: Path, brightness: int = 128, size: tuple[int, int] = (50, 50)) -> Path:
    """Solid single-colour PNG — produces dHash of 0 (all pixels equal, no gradient)."""
    img = Image.new("RGB", size, color=(brightness, brightness, brightness))
    img.save(str(path), format="PNG")
    return path


def _save_gradient_png(path: Path, size: tuple[int, int] = (100, 100)) -> Path:
    """Right-to-left gradient: bright on left, dark on right → all dHash bits = 1."""
    w, h = size
    pixels = [int(255 * (w - 1 - x) / max(w - 1, 1)) for _ in range(h) for x in range(w)]
    img = Image.new("L", (w, h))
    img.putdata(pixels)
    img.convert("RGB").save(str(path), format="PNG")
    return path


# ---------------------------------------------------------------------------
# dhash
# ---------------------------------------------------------------------------

def test_dhash_returns_int() -> None:
    img = Image.new("RGB", (20, 20), color=(100, 100, 100))
    assert isinstance(_dhash(img), int)


def test_dhash_same_image_same_hash() -> None:
    img = Image.new("RGB", (20, 20), color=(200, 150, 100))
    assert _dhash(img) == _dhash(img)


def test_dhash_in_64bit_range() -> None:
    img = Image.new("RGB", (20, 20), color=(128, 128, 128))
    h = _dhash(img)
    assert 0 <= h < 2 ** 64


def test_dhash_small_hash_size_produces_smaller_value() -> None:
    img = Image.new("RGB", (20, 20), color=(50, 50, 50))
    h = _dhash(img, hash_size=4)
    assert 0 <= h < 2 ** 16


def test_dhash_uniform_and_reversed_gradient_differ() -> None:
    uniform = Image.new("RGB", (50, 50), color=(128, 128, 128))
    w, h = 50, 50
    pixels = [int(255 * (w - 1 - x) / (w - 1)) for _ in range(h) for x in range(w)]
    grad = Image.new("L", (w, h))
    grad.putdata(pixels)
    assert _dhash(uniform) != _dhash(grad.convert("RGB"))


# ---------------------------------------------------------------------------
# hamming_distance
# ---------------------------------------------------------------------------

def test_hamming_identical_is_zero() -> None:
    assert _hamming_distance(0b1010, 0b1010) == 0


def test_hamming_single_bit_difference() -> None:
    assert _hamming_distance(0b1010, 0b1011) == 1


def test_hamming_nibble_difference() -> None:
    assert _hamming_distance(0b11110000, 0b00001111) == 8


def test_hamming_64bit_max_distance() -> None:
    assert _hamming_distance(0, 2 ** 64 - 1) == 64


def test_hamming_is_symmetric() -> None:
    assert _hamming_distance(0xFF00, 0x00FF) == _hamming_distance(0x00FF, 0xFF00)


def test_hamming_zero_with_power_of_two_is_one() -> None:
    assert _hamming_distance(0, 1) == 1
    assert _hamming_distance(0, 2) == 1
    assert _hamming_distance(0, 4) == 1
