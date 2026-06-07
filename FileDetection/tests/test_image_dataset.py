"""Unit tests for image_classification_dataset.py — ImageClassificationDataset."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from image_classification_dataset import ImageClassificationDataset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_file(path: Path, size: tuple[int, int] = (10, 10)) -> None:
    """Save a minimal valid RGB JPEG or PNG to path (PIL infers format from extension)."""
    Image.new("RGB", size, color=(128, 128, 128)).save(str(path))


def _setup_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Create dataset/filter and dataset/keep under tmp_path."""
    filter_dir = tmp_path / "dataset" / "filter"
    keep_dir = tmp_path / "dataset" / "keep"
    filter_dir.mkdir(parents=True)
    keep_dir.mkdir(parents=True)
    return filter_dir, keep_dir


# ---------------------------------------------------------------------------
# __len__
# ---------------------------------------------------------------------------

def test_empty_folders_give_zero_length(tmp_path: Path) -> None:
    _setup_dirs(tmp_path)
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    assert len(dataset) == 0


def test_length_counts_images_in_both_folders(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(filter_dir / "a.jpg")
    _make_image_file(filter_dir / "b.png")
    _make_image_file(keep_dir / "c.jpg")
    _make_image_file(keep_dir / "d.jpg")
    _make_image_file(keep_dir / "e.jpg")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    assert len(dataset) == 5


def test_non_image_files_are_excluded(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(filter_dir / "a.jpg")
    (filter_dir / "readme.txt").write_text("ignore me")
    (filter_dir / "data.csv").write_text("col1,col2")
    (keep_dir / "notes.md").write_text("# notes")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    assert len(dataset) == 1


def test_mp4_extension_excluded(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(filter_dir / "a.jpg")
    (keep_dir / "video.mp4").write_bytes(b"\x00" * 10)
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    assert len(dataset) == 1


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def test_keep_images_have_label_one(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(keep_dir / "a.jpg")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    _img, label = dataset[0]
    assert label == 1


def test_filter_images_have_label_zero(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(filter_dir / "a.jpg")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    _img, label = dataset[0]
    assert label == 0


# ---------------------------------------------------------------------------
# __getitem__
# ---------------------------------------------------------------------------

def test_getitem_returns_pil_image_and_int(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(keep_dir / "img.jpg")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    img, label = dataset[0]
    assert isinstance(img, Image.Image)
    assert isinstance(label, int)


def test_getitem_image_is_rgb(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(keep_dir / "img.jpg")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset()
    img, _label = dataset[0]
    assert img.mode == "RGB"


def test_getitem_applies_transform(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(keep_dir / "img.jpg")
    transform = MagicMock(side_effect=lambda x: x)
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset(transform=transform)
    dataset[0]
    transform.assert_called_once()


def test_getitem_no_transform_returns_pil_image(tmp_path: Path) -> None:
    filter_dir, keep_dir = _setup_dirs(tmp_path)
    _make_image_file(keep_dir / "img.png")
    with patch("image_classification_dataset.__file__", str(tmp_path / "fake.py")):
        dataset = ImageClassificationDataset(transform=None)
    img, _label = dataset[0]
    assert isinstance(img, Image.Image)
