"""Unit tests for similar_photos.py — _dhash, _hamming_distance, _UnionFind, SimilarPhotoAccumulator."""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from similar_photos import (
    SimilarPhotoAccumulator,
    _UnionFind,
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
# _dhash
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
# _hamming_distance
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


# ---------------------------------------------------------------------------
# _UnionFind
# ---------------------------------------------------------------------------

def test_unionfind_initial_each_element_is_own_root() -> None:
    uf = _UnionFind(5)
    for i in range(5):
        assert uf.find(i) == i


def test_unionfind_union_merges_roots() -> None:
    uf = _UnionFind(4)
    uf.union(0, 1)
    assert uf.find(0) == uf.find(1)


def test_unionfind_unrelated_elements_stay_separate() -> None:
    uf = _UnionFind(4)
    uf.union(0, 1)
    assert uf.find(2) != uf.find(0)
    assert uf.find(3) != uf.find(0)


def test_unionfind_transitivity() -> None:
    uf = _UnionFind(3)
    uf.union(0, 1)
    uf.union(1, 2)
    assert uf.find(0) == uf.find(1) == uf.find(2)


def test_unionfind_groups_contains_all_elements() -> None:
    uf = _UnionFind(4)
    uf.union(0, 1)
    all_elements = sorted(e for g in uf.groups() for e in g)
    assert all_elements == [0, 1, 2, 3]


def test_unionfind_two_merges_produce_two_groups() -> None:
    uf = _UnionFind(4)
    uf.union(0, 1)
    uf.union(2, 3)
    assert len(uf.groups()) == 2


def test_unionfind_single_element() -> None:
    uf = _UnionFind(1)
    assert uf.find(0) == 0
    assert len(uf.groups()) == 1


def test_unionfind_union_self_is_idempotent() -> None:
    uf = _UnionFind(3)
    uf.union(1, 1)
    assert len(uf.groups()) == 3


def test_unionfind_all_merged_gives_one_group() -> None:
    uf = _UnionFind(5)
    for i in range(4):
        uf.union(i, i + 1)
    assert len(uf.groups()) == 1


# ---------------------------------------------------------------------------
# SimilarPhotoAccumulator
# ---------------------------------------------------------------------------

def test_accumulator_starts_empty() -> None:
    acc = SimilarPhotoAccumulator()
    assert acc.size() == 0
    assert acc.current_bests() == []


def test_accumulator_first_add_creates_new_group(tmp_path: Path) -> None:
    path = _save_solid_png(tmp_path / "a.png")
    acc = SimilarPhotoAccumulator(threshold=10)
    with patch("similar_photos.score_image", return_value=5.0):
        winner, is_new = acc.add(path)
    assert winner == path
    assert is_new is True
    assert acc.size() == 1


def test_accumulator_identical_image_lower_score_not_new_best(tmp_path: Path) -> None:
    path_a = _save_solid_png(tmp_path / "a.png")
    path_b = _save_solid_png(tmp_path / "b.png")  # same pixels → same dHash
    acc = SimilarPhotoAccumulator(threshold=10)
    with patch("similar_photos.score_image", return_value=8.0):
        acc.add(path_a)
    with patch("similar_photos.score_image", return_value=3.0):
        winner, is_new = acc.add(path_b)
    assert winner == path_a
    assert is_new is False
    assert acc.size() == 1


def test_accumulator_identical_image_higher_score_becomes_new_best(tmp_path: Path) -> None:
    path_a = _save_solid_png(tmp_path / "a.png")
    path_b = _save_solid_png(tmp_path / "b.png")
    acc = SimilarPhotoAccumulator(threshold=10)
    with patch("similar_photos.score_image", return_value=3.0):
        acc.add(path_a)
    with patch("similar_photos.score_image", return_value=8.0):
        winner, is_new = acc.add(path_b)
    assert winner == path_b
    assert is_new is True
    assert acc.size() == 1


def test_accumulator_dissimilar_image_creates_new_group(tmp_path: Path) -> None:
    path_a = _save_solid_png(tmp_path / "a.png")
    path_b = _save_gradient_png(tmp_path / "b.png")
    acc = SimilarPhotoAccumulator(threshold=10)
    with patch("similar_photos.score_image", return_value=5.0):
        acc.add(path_a)
        acc.add(path_b)
    assert acc.size() == 2


def test_accumulator_unreadable_image_rejected_no_state_change(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.png"
    bad_path.write_bytes(b"not an image at all")
    acc = SimilarPhotoAccumulator(threshold=10)
    winner, is_new = acc.add(bad_path)
    assert winner == bad_path
    assert is_new is False
    assert acc.size() == 0


def test_accumulator_nonexistent_path_rejected(tmp_path: Path) -> None:
    acc = SimilarPhotoAccumulator(threshold=10)
    bad_path = tmp_path / "missing.png"
    winner, is_new = acc.add(bad_path)
    assert winner == bad_path
    assert is_new is False
    assert acc.size() == 0


def test_accumulator_current_bests_has_one_entry_per_group(tmp_path: Path) -> None:
    path_a = _save_solid_png(tmp_path / "a.png")
    path_b = _save_gradient_png(tmp_path / "b.png")
    acc = SimilarPhotoAccumulator(threshold=10)
    with patch("similar_photos.score_image", return_value=5.0):
        acc.add(path_a)
        acc.add(path_b)
    bests = acc.current_bests()
    assert len(bests) == 2
    assert path_a in bests
    assert path_b in bests


def test_accumulator_group_hash_anchored_to_founder(tmp_path: Path) -> None:
    """After a best-swap the group hash stays as the founder's; new arrivals still match."""
    path_a = _save_solid_png(tmp_path / "a.png")
    path_b = _save_solid_png(tmp_path / "b.png")
    path_c = _save_solid_png(tmp_path / "c.png")
    acc = SimilarPhotoAccumulator(threshold=10)
    with patch("similar_photos.score_image", return_value=1.0):
        acc.add(path_a)
    with patch("similar_photos.score_image", return_value=9.0):
        acc.add(path_b)  # b wins, but stored hash remains a's
    with patch("similar_photos.score_image", return_value=5.0):
        winner, is_new = acc.add(path_c)  # c has same hash as a → same group, b still wins
    assert acc.size() == 1
    assert is_new is False
    assert winner == path_b


def test_accumulator_concurrent_adds_do_not_raise(tmp_path: Path) -> None:
    """Concurrent adds from multiple threads must not raise or corrupt internal state."""
    paths = [_save_solid_png(tmp_path / f"img_{i}.png") for i in range(8)]
    acc = SimilarPhotoAccumulator(threshold=10)
    errors: list[Exception] = []

    def add_image(p: Path) -> None:
        try:
            acc.add(p)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    with patch("similar_photos.score_image", return_value=5.0):
        threads = [threading.Thread(target=add_image, args=(p,)) for p in paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert not errors
    assert 1 <= acc.size() <= len(paths)
