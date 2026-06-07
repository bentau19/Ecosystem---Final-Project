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

import threading
from collections import defaultdict
from pathlib import Path

from PIL import Image

from quality import score_image

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
        (hash_size + 1, hash_size), Image.Resampling.LANCZOS
    )
    pixels: list[int] = list(resized.tobytes())
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
# Incremental / streaming accumulator
# ---------------------------------------------------------------------------

class SimilarPhotoAccumulator:
    """
    Stateful, thread-safe tracker for the best image seen per similarity group.

    Designed for scenarios where images arrive one at a time (or concurrently)
    — for example, streamed from a phone file transfer — rather than being
    available as a complete list upfront.

    Internally stores exactly **one entry per similarity group**: the current
    best-quality representative.  When a new image arrives it is hashed and
    compared against every stored representative; if a similar one is found
    the higher-quality image becomes (or remains) the group's best.

    Example::

        acc = SimilarPhotoAccumulator()

        for path in incoming_transfer():
            winner, is_new_best = acc.add(path)
            if not is_new_best:
                path.unlink()   # inferior duplicate — discard the cached copy
    """

    def __init__(self, threshold: int = 10) -> None:
        """
        Args:
            threshold: Maximum Hamming distance (0–64 for an 8-bit dHash)
                       below which two images are considered similar.
                       Default 10 handles JPEG re-compression and minor crops.
        """
        self._threshold: int = threshold
        # One entry per group: (best_path, dhash_of_best, quality_score_of_best)
        self._entries: list[tuple[Path, int, float]] = []
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, path: Path) -> tuple[Path, bool]:
        """
        Register a single incoming image and compare it against known bests.

        The dHash and quality score are computed *outside* the lock so that
        concurrent calls do not serialise on slow PIL / numpy work.

        Args:
            path: Path to the newly arrived image file (may be a temp cache path).

        Returns:
            ``(winner_path, is_new_best)`` where:

            - ``(path, True)``          — no similar image existed; *path* is now
                                          the representative for its new group.
            - ``(path, True)``          — *path* beat an existing similar image
                                          and has replaced it as the group best.
            - ``(existing_path, False)``— an existing image is already higher
                                          quality; *path* is an inferior duplicate.

            On read/decode failure the image is treated as lowest quality and
            ``(path, False)`` is returned without modifying stored state.
        """
        try:
            with Image.open(path) as img:
                new_hash: int = _dhash(img)
        except Exception:
            return path, False  # unreadable — treat as rejected

        new_score: float = score_image(path)  # slow numpy work, outside lock

        with self._lock:
            best_idx: int | None = None
            best_dist: int = self._threshold + 1

            for i, (_, stored_hash, _) in enumerate(self._entries):
                dist = _hamming_distance(new_hash, stored_hash)
                if dist <= self._threshold and dist < best_dist:
                    best_dist = dist
                    best_idx = i

            if best_idx is None:
                # No similar image known — start a new group.
                self._entries.append((path, new_hash, new_score))
                return path, True

            existing_path, existing_hash, existing_score = self._entries[best_idx]

            if new_score > existing_score:
                # New image is sharper / better exposed — it takes over.
                # Keep existing_hash: the group's identity is anchored to the
                # hash of its founding image so future arrivals always compare
                # against a stable reference, even after the best changes.
                self._entries[best_idx] = (path, existing_hash, new_score)
                return path, True

            # Existing representative is still the best.
            return existing_path, False

    def current_bests(self) -> list[Path]:
        """
        Returns the current best-image path for every tracked group.

        Returns:
            Snapshot list of Paths — one per distinct similarity group.
        """
        with self._lock:
            return [path for path, _, _ in self._entries]

    def size(self) -> int:
        """
        Returns the number of distinct similarity groups tracked so far.

        Returns:
            Non-negative integer.
        """
        with self._lock:
            return len(self._entries)
