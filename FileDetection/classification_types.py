from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Lightweight, torch-free result types for the classification pipeline.
#
# These live in their own module (rather than inside image_classifer.py) so that
# callers needing only the verdict/result types — e.g. classifer.py and the
# desktop BackupService — can import them WITHOUT pulling in torch/torchvision.
# Importing torch costs ~2.4s; keeping it out of the startup import path keeps
# the desktop app launching fast. image_classifer.py re-exports both names for
# backward compatibility.


class ClassificationVerdict(Enum):
    """Three-way outcome of :func:`classify_image` / :meth:`Classifier.classify`.

    The underlying model is binary (label ``0`` = "filter"/unwanted, label
    ``1`` = "keep" — matching the alphabetical class ordering
    ``filter < keep`` produced by
    :class:`~image_classification_dataset.ImageClassificationDataset`).
    :func:`classify_image` turns the raw ``pr(remove)`` probability into one
    of the three values below.

    Attributes:
        ACCEPTED: ``pr(remove) <= 0.5`` — confidently wanted. The file passed
            all screening stages and should be saved.
        REJECTED: ``pr(remove) > 0.95`` — confidently unwanted. The file
            should be discarded (exact duplicate, or confidently flagged by
            the ML classifier).
        NEEDS_REVIEW: ``0.5 < pr(remove) <= 0.95`` — the model's argmax
            already says "remove", but it isn't confident enough to act
            automatically. The caller should ask the user whether to keep or
            discard the file.
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


@dataclass
class ClassificationResult:
    """Outcome of a single image classification.

    Attributes:
        verdict: The three-way :class:`ClassificationVerdict`.
        confidence: Raw ``pr(remove)`` probability reported by the model.
    """

    verdict: ClassificationVerdict
    confidence: float
