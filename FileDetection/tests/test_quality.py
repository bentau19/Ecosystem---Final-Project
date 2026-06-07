"""Unit tests for quality.py — score_image(), _sharpness_score(), _resolution_score(), _exposure_score()."""

from pathlib import Path

import pytest
from PIL import Image

from quality import _exposure_score, _resolution_score, _sharpness_score, score_image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid(brightness: int, width: int = 50, height: int = 50) -> Image.Image:
    return Image.new("L", (width, height), color=brightness)


def _checkerboard(size: int = 50) -> Image.Image:
    pixels = [255 if (x + y) % 2 == 0 else 0 for y in range(size) for x in range(size)]
    img = Image.new("L", (size, size))
    img.putdata(pixels)
    return img


def _save_png(tmp_path: Path, img: Image.Image, name: str = "img.png") -> Path:
    path = tmp_path / name
    img.convert("RGB").save(str(path), format="PNG")
    return path


# ---------------------------------------------------------------------------
# score_image
# ---------------------------------------------------------------------------

def test_score_image_unreadable_path_returns_zero(tmp_path: Path) -> None:
    assert score_image(tmp_path / "ghost.png") == 0.0


def test_score_image_empty_file_returns_zero(tmp_path: Path) -> None:
    path = tmp_path / "empty.png"
    path.touch()
    assert score_image(path) == 0.0


def test_score_image_garbage_bytes_returns_zero(tmp_path: Path) -> None:
    path = tmp_path / "garbage.png"
    path.write_bytes(b"\x00\x01\x02\x03" * 50)
    assert score_image(path) == 0.0


def test_score_image_valid_image_returns_nonnegative(tmp_path: Path) -> None:
    path = _save_png(tmp_path, _solid(128))
    assert score_image(path) >= 0.0


def test_score_image_well_exposed_image_scores_higher_than_black(tmp_path: Path) -> None:
    mid_gray = _save_png(tmp_path, _solid(128), "mid.png")
    black = _save_png(tmp_path, _solid(0), "black.png")
    assert score_image(mid_gray) > score_image(black)


# ---------------------------------------------------------------------------
# _sharpness_score
# ---------------------------------------------------------------------------

def test_sharpness_uniform_image_is_zero() -> None:
    assert _sharpness_score(_solid(128)) == pytest.approx(0.0, abs=1e-6)


def test_sharpness_checkerboard_exceeds_uniform() -> None:
    assert _sharpness_score(_checkerboard()) > _sharpness_score(_solid(128))


def test_sharpness_returns_nonnegative() -> None:
    assert _sharpness_score(_solid(0)) >= 0.0


def test_sharpness_accepts_rgb_image() -> None:
    img = Image.new("RGB", (20, 20), color=(100, 150, 200))
    result = _sharpness_score(img)
    assert isinstance(result, float)
    assert result >= 0.0


def test_sharpness_uniform_black_equals_uniform_white() -> None:
    assert _sharpness_score(_solid(0)) == pytest.approx(_sharpness_score(_solid(255)), abs=1e-6)


# ---------------------------------------------------------------------------
# _resolution_score
# ---------------------------------------------------------------------------

def test_resolution_at_reference_equals_one() -> None:
    img = Image.new("L", (4000, 3000))
    assert _resolution_score(img) == pytest.approx(1.0)


def test_resolution_tiny_image_is_less_than_one() -> None:
    score = _resolution_score(Image.new("L", (100, 100)))
    assert 0.0 < score < 1.0


def test_resolution_larger_than_reference_capped_at_one() -> None:
    img = Image.new("L", (8000, 6000))  # 48 MP — well above 12 MP
    assert _resolution_score(img) == pytest.approx(1.0)


def test_resolution_half_reference_scores_half() -> None:
    img = Image.new("L", (2000, 3000))  # 6 MP = half of 12 MP
    assert _resolution_score(img) == pytest.approx(0.5, abs=0.01)


def test_resolution_single_pixel_is_near_zero() -> None:
    img = Image.new("L", (1, 1))
    assert _resolution_score(img) < 0.001


# ---------------------------------------------------------------------------
# _exposure_score
# ---------------------------------------------------------------------------

def test_exposure_mid_gray_returns_one() -> None:
    assert _exposure_score(_solid(125)) == pytest.approx(1.0)


def test_exposure_at_lower_boundary_returns_one() -> None:
    assert _exposure_score(_solid(60)) == pytest.approx(1.0)


def test_exposure_at_upper_boundary_returns_one() -> None:
    assert _exposure_score(_solid(190)) == pytest.approx(1.0)


def test_exposure_pure_black_returns_zero() -> None:
    assert _exposure_score(_solid(0)) == pytest.approx(0.0)


def test_exposure_pure_white_returns_zero() -> None:
    assert _exposure_score(_solid(255)) == pytest.approx(0.0)


def test_exposure_underexposed_is_between_zero_and_one() -> None:
    score = _exposure_score(_solid(30))  # below ideal min (60)
    assert 0.0 < score < 1.0


def test_exposure_overexposed_is_between_zero_and_one() -> None:
    score = _exposure_score(_solid(220))  # above ideal max (190)
    assert 0.0 < score < 1.0


def test_exposure_returns_float() -> None:
    assert isinstance(_exposure_score(_solid(128)), float)
