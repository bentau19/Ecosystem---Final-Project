"""
Public API for perceptual-similarity grouping and quality-based best-photo selection.

Pipeline
--------
1. Compute a **dHash** (difference hash) for every image — pure PIL, no extra deps.
2. Build similarity groups using **Union-Find**: two images whose hashes differ
   by ≤ ``threshold`` Hamming bits are merged into the same group (transitively,
   so burst-shot chains are captured in one group).
3. Within each group, **score** every image on sharpness, resolution, and exposure
   and return the highest-scoring one as the "best".
4. Optionally **copy** the best photos to an output directory via ``save_best_photos``.

Entry points
------------
``find_similar_groups(image_paths, threshold)``  → ``list[list[Path]]``
``pick_best(group)``                             → ``Path``
``deduplicate_to_best(image_paths, threshold)``  → ``dict[Path, list[Path]]``
``save_best_photos(image_paths, output_dir, threshold)`` → ``list[Path]``
"""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image

from _quality import score_image

# ---------------------------------------------------------------------------
# Supported extensions
# ---------------------------------------------------------------------------

_IMAGE_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif",
})


# ---------------------------------------------------------------------------
# Perceptual hashing (dHash)
# ---------------------------------------------------------------------------

def _dhash(img: Image.Image, hash_size: int = 8) -> int:
    """
    Computes a difference hash (dHash) for a PIL image.

    Resizes the image to ``(hash_size + 1) × hash_size`` grayscale, then
    encodes horizontal brightness gradients as a ``hash_size²``-bit integer.
    Adjacent-pixel comparisons capture local structure robustly against minor
    colour shifts, JPEG re-compression, and small crops.

    Args:
        img: PIL Image to hash (any mode — converted to grayscale internally).
        hash_size: Controls hash length — produces ``hash_size²`` bits total.
                   Default 8 → 64-bit hash.

    Returns:
        Integer dHash value.
    """
    resized = img.convert("L").resize(
        (hash_size + 1, hash_size), Image.LANCZOS
    )
    pixels = list(resized.getdata())
    bits = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def _hamming_distance(h1: int, h2: int) -> int:
    """
    Returns the Hamming distance between two integer hashes.

    Counts the number of bit positions that differ.

    Args:
        h1: First hash value.
        h2: Second hash value.

    Returns:
        Non-negative integer — number of differing bits.
    """
    return bin(h1 ^ h2).count("1")


def _compute_hashes(image_paths: list[Path]) -> list[tuple[Path, int]]:
    """
    Opens and hashes every image, silently skipping unreadable files.

    Args:
        image_paths: Paths to image files.

    Returns:
        List of ``(path, dhash)`` tuples for images that opened successfully.
    """
    result: list[tuple[Path, int]] = []
    for path in image_paths:
        try:
            with Image.open(path) as img:
                result.append((path, _dhash(img)))
        except Exception:
            pass  # corrupt or unreadable — skip silently
    return result


# ---------------------------------------------------------------------------
# Union-Find (disjoint set)
# ---------------------------------------------------------------------------

class _UnionFind:
    """
    Simple Union-Find with path compression and union-by-rank.

    Used to cluster similar images transitively without O(n³) pair-checking.
    """

    def __init__(self, n: int) -> None:
        """
        Initializes n singleton sets labeled 0 … n-1.

        Args:
            n: Number of elements.
        """
        self._parent: list[int] = list(range(n))
        self._rank: list[int] = [0] * n

    def find(self, x: int) -> int:
        """
        Returns the root of the set containing ``x`` (with path compression).

        Args:
            x: Element index.

        Returns:
            Root index of the set.
        """
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        """
        Merges the sets containing ``x`` and ``y``.

        Args:
            x: First element index.
            y: Second element index.
        """
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def groups(self) -> list[list[int]]:
        """
        Returns all disjoint sets as lists of element indices.

        Returns:
            List of groups; each group is a list of integer indices.
        """
        buckets: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self._parent)):
            buckets[self.find(i)].append(i)
        return list(buckets.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_similar_groups(
        image_paths: list[Path],
        threshold: int = 10,
) -> list[list[Path]]:
    """
    Clusters image paths into groups of perceptually similar images.

    Two images are considered similar when their dHash Hamming distance is
    at or below ``threshold``.  Groups are formed **transitively** — if A~B
    and B~C then {A, B, C} form one group even if A and C differ by more than
    the threshold on their own.

    Unreadable or corrupt images are silently excluded from all groups.

    Args:
        image_paths: Paths to the image files to compare.
        threshold: Maximum Hamming distance (0–64 for an 8-bit dHash) to
                   consider two images similar.  Lower = stricter matching.
                   Default 10 handles JPEG re-compression and minor crops well.

    Returns:
        List of groups; each group is a non-empty list of similar Paths.
        Images with no similar peers appear as singleton groups ``[path]``.
    """
    hashed = _compute_hashes(image_paths)
    n = len(hashed)
    if n == 0:
        return []

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if _hamming_distance(hashed[i][1], hashed[j][1]) <= threshold:
                uf.union(i, j)

    return [[hashed[idx][0] for idx in group] for group in uf.groups()]


def pick_best(group: list[Path]) -> Path:
    """
    Returns the highest-quality image from a group of similar images.

    Quality is a weighted composite scored by ``_checkers._quality.score_image``:
    - Sharpness  (50 %) — Laplacian variance; higher = crisper
    - Resolution (30 %) — pixel count; higher = more detail
    - Exposure   (20 %) — mean brightness closeness to ideal range [60, 190]

    Args:
        group: Non-empty list of image Paths from the same similarity group.

    Returns:
        Path to the best-scoring image in the group.

    Raises:
        ValueError: If ``group`` is empty.
    """
    if not group:
        raise ValueError("group must contain at least one image")

    scored = [(score_image(path), path) for path in group]
    return max(scored, key=lambda t: t[0])[1]


def deduplicate_to_best(
        image_paths: list[Path],
        threshold: int = 10,
) -> dict[Path, list[Path]]:
    """
    One-call pipeline: groups similar images and selects the best from each group.

    Combines ``find_similar_groups`` and ``pick_best`` into a single operation.

    Args:
        image_paths: All image Paths to process.
        threshold: Hamming distance threshold passed to ``find_similar_groups``
                   (default 10).

    Returns:
        Mapping of ``best_image → [inferior_duplicates]``.
        Images with no similar peers map to an empty list.

    Example::

        result = deduplicate_to_best(list(Path("photos/").glob("*.jpg")))
        for best, discarded in result.items():
            for path in discarded:
                path.unlink()   # delete the inferior near-duplicates
    """
    groups = find_similar_groups(image_paths, threshold)
    result: dict[Path, list[Path]] = {}
    for group in groups:
        best = pick_best(group)
        result[best] = [p for p in group if p != best]
    return result
