"""
Unit tests for similar_photos.py.

Covers: dhash, hamming_distance, _UnionFind, group_by_hash,
        find_similar_groups, pick_best, deduplicate_to_best, save_best_photos,
        SimilarPhotoAccumulator (including seed_entries).
"""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from similar_photos import (
    SimilarPhotoAccumulator,
    _UnionFind,
    deduplicate_to_best,
    _dhash,
    find_similar_groups,
    group_by_hash,
    _hamming_distance,
    pick_best,
    save_best_photos,
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


# ---------------------------------------------------------------------------
# group_by_hash
# ---------------------------------------------------------------------------

def test_group_by_hash_empty_input_returns_empty() -> None:
    assert group_by_hash([], threshold=10) == []


def test_group_by_hash_identical_hashes_produce_one_group(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    hashed = [(a, 0b1010), (b, 0b1010)]  # same hash → distance 0
    groups = group_by_hash(hashed, threshold=10)
    assert len(groups) == 1
    assert set(groups[0]) == {a, b}


def test_group_by_hash_distant_hashes_produce_separate_groups(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    hashed = [(a, 0), (b, 2**64 - 1)]  # 64-bit Hamming distance
    groups = group_by_hash(hashed, threshold=10)
    assert len(groups) == 2


def test_group_by_hash_transitivity(tmp_path: Path) -> None:
    """A~B and B~C → all three in one group even if A and C differ by > threshold."""
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    # A=0b00, B=0b01 (dist 1), C=0b11 (dist 1 from B, dist 2 from A)
    hashed = [(a, 0b00), (b, 0b01), (c, 0b11)]
    groups = group_by_hash(hashed, threshold=1)
    assert len(groups) == 1
    assert set(groups[0]) == {a, b, c}


# ---------------------------------------------------------------------------
# find_similar_groups
# ---------------------------------------------------------------------------

def test_find_similar_groups_identical_images_one_group(tmp_path: Path) -> None:
    a = _save_solid_png(tmp_path / "a.png")
    b = _save_solid_png(tmp_path / "b.png")  # same pixels → same dHash
    groups = find_similar_groups([a, b], threshold=10)
    assert len(groups) == 1
    assert set(groups[0]) == {a, b}


def test_find_similar_groups_dissimilar_images_separate_groups(tmp_path: Path) -> None:
    solid    = _save_solid_png(tmp_path / "solid.png")
    gradient = _save_gradient_png(tmp_path / "gradient.png")
    groups   = find_similar_groups([solid, gradient], threshold=10)
    assert len(groups) == 2


def test_find_similar_groups_unreadable_file_dropped(tmp_path: Path) -> None:
    good = _save_solid_png(tmp_path / "good.png")
    bad  = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    groups = find_similar_groups([good, bad], threshold=10)
    # bad is dropped; only good remains — one singleton group
    all_paths = [p for g in groups for p in g]
    assert bad not in all_paths
    assert good in all_paths


def test_find_similar_groups_empty_list_returns_empty() -> None:
    assert find_similar_groups([]) == []


# ---------------------------------------------------------------------------
# pick_best
# ---------------------------------------------------------------------------

def test_pick_best_returns_highest_scoring_path(tmp_path: Path) -> None:
    low  = _save_solid_png(tmp_path / "low.png")
    high = _save_solid_png(tmp_path / "high.png")
    scores = {str(low): 1.0, str(high): 9.0}
    with patch("similar_photos.score_image", side_effect=lambda p: scores[str(p)]):
        assert pick_best([low, high]) == high


def test_pick_best_single_element_returns_it(tmp_path: Path) -> None:
    p = _save_solid_png(tmp_path / "only.png")
    with patch("similar_photos.score_image", return_value=5.0):
        assert pick_best([p]) == p


# ---------------------------------------------------------------------------
# deduplicate_to_best
# ---------------------------------------------------------------------------

def test_deduplicate_to_best_keys_are_best_paths(tmp_path: Path) -> None:
    a = _save_solid_png(tmp_path / "a.png")
    b = _save_solid_png(tmp_path / "b.png")
    scores = {str(a): 3.0, str(b): 7.0}
    with patch("similar_photos.score_image", side_effect=lambda p: scores[str(p)]):
        result = deduplicate_to_best([a, b], threshold=10)
    assert b in result          # b is best
    assert a not in result      # a is not a key
    assert a in result[b]       # but a is in b's group


def test_deduplicate_to_best_dissimilar_images_separate_keys(tmp_path: Path) -> None:
    solid    = _save_solid_png(tmp_path / "solid.png")
    gradient = _save_gradient_png(tmp_path / "gradient.png")
    with patch("similar_photos.score_image", return_value=5.0):
        result = deduplicate_to_best([solid, gradient], threshold=10)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# save_best_photos
# ---------------------------------------------------------------------------

def test_save_best_photos_creates_output_dir_and_copies_file(tmp_path: Path) -> None:
    src     = _save_solid_png(tmp_path / "src.png")
    out_dir = tmp_path / "output"
    with patch("similar_photos.score_image", return_value=5.0):
        saved = save_best_photos([src], out_dir, threshold=10)
    assert out_dir.exists()
    assert len(saved) == 1
    assert saved[0].exists()
    assert saved[0].read_bytes() == src.read_bytes()


def test_save_best_photos_only_best_per_group_copied(tmp_path: Path) -> None:
    a = _save_solid_png(tmp_path / "a.png")
    b = _save_solid_png(tmp_path / "b.png")  # same dHash group
    out_dir = tmp_path / "out"
    scores = {str(a): 2.0, str(b): 8.0}
    with patch("similar_photos.score_image", side_effect=lambda p: scores[str(p)]):
        saved = save_best_photos([a, b], out_dir, threshold=10)
    assert len(saved) == 1
    assert saved[0].name == "b.png"


# ---------------------------------------------------------------------------
# SimilarPhotoAccumulator — seed_entries
# ---------------------------------------------------------------------------

def test_accumulator_default_init_starts_empty() -> None:
    acc = SimilarPhotoAccumulator()
    assert acc.size() == 0


def test_accumulator_none_seed_behaves_same_as_default() -> None:
    acc = SimilarPhotoAccumulator(seed_entries=None)
    assert acc.size() == 0


def test_accumulator_seed_entries_initialises_groups(tmp_path: Path) -> None:
    p = tmp_path / "seeded.png"
    _save_solid_png(p)
    acc = SimilarPhotoAccumulator(threshold=10, seed_entries=[(p, 0, 5.0)])
    assert acc.size() == 1
    assert acc.current_bests() == [p]


def test_accumulator_seed_entry_similar_incoming_lower_score_rejected(tmp_path: Path) -> None:
    seeded = tmp_path / "seeded.png"
    newcomer = tmp_path / "newcomer.png"
    _save_solid_png(seeded)
    _save_solid_png(newcomer)  # same dHash as seeded (solid colour)

    acc = SimilarPhotoAccumulator(threshold=10, seed_entries=[(seeded, 0, 9.0)])
    with patch("similar_photos.score_image", return_value=3.0):
        winner, is_new_best = acc.add(newcomer)

    assert is_new_best is False
    assert winner == seeded
    assert acc.size() == 1


def test_accumulator_seed_entry_dissimilar_incoming_creates_new_group(tmp_path: Path) -> None:
    seeded   = tmp_path / "seeded.png"
    gradient = tmp_path / "gradient.png"
    _save_solid_png(seeded)
    _save_gradient_png(gradient)

    acc = SimilarPhotoAccumulator(threshold=10, seed_entries=[(seeded, 0, 5.0)])
    with patch("similar_photos.score_image", return_value=5.0):
        _, is_new_best = acc.add(gradient)

    assert is_new_best is True
    assert acc.size() == 2
