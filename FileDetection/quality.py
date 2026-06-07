"""
Image quality scoring for similar-photo selection.

Exposes a single public function:
    ``score_image(image_path: Path) -> float``

Score is a weighted composite of three criteria:

  Sharpness  (50 %) — Laplacian variance of the grayscale pixel array.
                       Higher variance = more high-frequency detail = crisper.
  Resolution (30 %) — pixel count relative to a 12-MP reference baseline.
                       Capped at 1.0 so megapixels beyond 12 MP don't dominate.
  Exposure   (20 %) — how close the mean brightness is to the ideal window
                       [60, 190].  Fully dark or fully blown-out images score 0.

All three components are in [0, ∞) for sharpness and [0, 1] for resolution
and exposure, so the composite is dominated by sharpness differences when
comparing images of the same scene — exactly what we want.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REFERENCE_PIXELS: int = 4000 * 3000   # 12 MP normalization baseline
_IDEAL_BRIGHTNESS_MIN: float = 60.0
_IDEAL_BRIGHTNESS_MAX: float = 190.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_image(image_path: Path) -> float:
    """
    Returns a composite quality score for a single image file.

    Higher is better.  Returns 0.0 if the image cannot be opened or decoded
    (treated as lowest-possible quality so it is never chosen as "best").

    Args:
        image_path: Path to the image file to score.

    Returns:
        Non-negative float.  Sharpness is unbounded above; resolution and
        exposure contributions are each in [0, 1].
    """
    try:
        with Image.open(image_path) as img:
            img.load()          # force full decode to catch truncated files
            sharpness  = _sharpness_score(img)
            resolution = _resolution_score(img)
            exposure   = _exposure_score(img)
    except Exception:
        return 0.0

    return 0.5 * sharpness + 0.3 * resolution + 0.2 * exposure


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _sharpness_score(img: Image.Image) -> float:
    """
    Estimates sharpness using the variance of the discrete Laplacian.

    The Laplacian highlights rapid brightness changes (edges, fine texture).
    A blurry image has a near-uniform Laplacian (low variance); a sharp image
    has many strong edges (high variance).

    Computed on the grayscale channel using four-neighbour finite differences
    on all interior pixels — no external convolution library required.

    Args:
        img: PIL Image in any mode.

    Returns:
        Non-negative float — larger means sharper.
    """
    gray = np.array(img.convert("L"), dtype=np.float32)
    # Four-neighbour discrete Laplacian (interior pixels only)
    lap = (
        gray[:-2, 1:-1]       # top
        + gray[2:,  1:-1]     # bottom
        + gray[1:-1, :-2]     # left
        + gray[1:-1,  2:]     # right
        - 4.0 * gray[1:-1, 1:-1]
    )
    return float(np.var(lap))


def _resolution_score(img: Image.Image) -> float:
    """
    Scores image resolution relative to a 12 MP reference.

    A 12-megapixel (or larger) image scores 1.0.  Smaller images score
    proportionally less.  The cap ensures a 48 MP burst shot does not
    overshadow a perfectly sharp 8 MP photo purely on pixel count.

    Args:
        img: PIL Image.

    Returns:
        Float in [0, 1].
    """
    return min(1.0, (img.width * img.height) / _REFERENCE_PIXELS)


def _exposure_score(img: Image.Image) -> float:
    """
    Scores how well-exposed the image is.

    Mean grayscale brightness inside the ideal window [60, 190] scores 1.0.
    Brightness below 60 (underexposed / too dark) or above 190 (overexposed /
    blown-out highlights) is penalised linearly down to 0.0 at the extremes
    (0 and 255 respectively).

    Args:
        img: PIL Image in any mode.

    Returns:
        Float in [0, 1].
    """
    mean_brightness = float(
        np.mean(np.array(img.convert("L"), dtype=np.float32))
    )

    if _IDEAL_BRIGHTNESS_MIN <= mean_brightness <= _IDEAL_BRIGHTNESS_MAX:
        return 1.0

    if mean_brightness < _IDEAL_BRIGHTNESS_MIN:
        deviation = _IDEAL_BRIGHTNESS_MIN - mean_brightness
        return max(0.0, 1.0 - deviation / _IDEAL_BRIGHTNESS_MIN)

    # mean_brightness > _IDEAL_BRIGHTNESS_MAX
    deviation = mean_brightness - _IDEAL_BRIGHTNESS_MAX
    return max(0.0, 1.0 - deviation / (255.0 - _IDEAL_BRIGHTNESS_MAX))
