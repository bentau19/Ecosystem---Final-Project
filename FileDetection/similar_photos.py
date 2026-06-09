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

import sqlite3
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


def process_image(
        db_path: Path, file_path: Path, threshold: int = 10
) -> tuple[Path, bool, Path | None]:
    """
    Decides whether an incoming image is the best of its visual group.

    Computes the dHash and quality score for *file_path*, then scans
    ``visual_groups`` for any row whose ``file_hash_visual`` is within
    *threshold* Hamming bits.

    - **No similar group** → INSERT a new row; incoming is kept.
    - **Similar group found, incoming is better** → UPDATE ``best_path`` /
      ``quality_score`` (``file_hash_visual`` PK stays unchanged); incoming kept.
    - **Similar group found, existing is better** → no DB change; incoming discarded.

    Call ``check_for_duplicates`` (Stage 1) before this function.

    Args:
        db_path:   Path to the SQLite database.
        file_path: Path to the incoming image file.
        threshold: Max Hamming distance to consider two images visually similar.
                   Default 10 handles JPEG re-compression and minor crops.

    Returns:
        ``(winner_path, is_new_best, displaced_path)`` where:

        - ``(file_path,     True,  None)``      — new group; nothing displaced.
        - ``(file_path,     True,  old_path)``  — incoming replaced old best;
                                                   caller should delete *old_path*.
        - ``(existing_path, False, None)``      — existing is better;
                                                   caller should discard incoming.
    """
    try:
        with Image.open(file_path) as img:
            new_hash: int = _dhash(img)
    except Exception:
        return file_path, False, None  # unreadable — reject silently

    new_score: float = score_image(file_path)  # PIL/numpy work, outside DB

    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            "SELECT file_hash_visual, best_path, quality_score FROM visual_groups"
        ).fetchall()

    # Hamming scan over stored group hashes — pure integer arithmetic, no I/O
    best_match: tuple[int, Path, float] | None = None
    best_dist: int = threshold + 1

    for group_hash, path_str, score in rows:
        dist = _hamming_distance(new_hash, int(group_hash))
        if dist <= threshold and dist < best_dist:
            best_dist = dist
            best_match = (int(group_hash), Path(path_str), float(score))

    with sqlite3.connect(db_path) as db:
        if best_match is None:
            # No similar group — start a new one; new_hash becomes the PK
            db.execute(
                "INSERT INTO visual_groups"
                " (file_hash_visual, best_path, file_name, quality_score)"
                " VALUES (?, ?, ?, ?)",
                (new_hash, str(file_path), file_path.stem, new_score),
            )
            l
            db.commit()
            return file_path, True, None

        group_hash, existing_path, existing_score = best_match

        if new_score > existing_score:
            # Incoming is better — update best; PK (file_hash_visual) unchanged
            db.execute(
                "UPDATE visual_groups"
                " SET best_path=?, file_name=?, quality_score=?"
                " WHERE file_hash_visual=?",
                (str(file_path), file_path.stem, new_score, group_hash),
            )
            db.commit()

            return file_path, True, existing_path  # caller deletes existing_path

        # Existing representative is still the best
        return existing_path, False, None
