from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image
from torch.utils.data import Dataset


class ImageClassificationDataset(Dataset):
    """Training dataset of "filter" (unwanted) vs. "keep" (wanted) images.

    Samples are loaded from ``dataset/filter`` (label 0) and ``dataset/keep``
    (label 1) relative to this file, matching the alphabetical class
    ordering ``filter < keep`` referenced by
    :class:`~image_classifer.ClassificationVerdict`.

    Attributes:
        CLASSES: Maps integer labels to their human-readable class name.
    """

    CLASSES: dict[int, str] = {0: "filter", 1: "keep"}

    def __init__(self, transform: Callable[[Image.Image], Any] | None = None) -> None:
        """Discover sample images and store the optional transform.

        Args:
            transform: Optional callable applied to each PIL image before it
                is returned (e.g. a ``torchvision.transforms`` pipeline).
        """
        super().__init__()
        self.transform: Callable[[Image.Image], Any] | None = transform
        filter_folder = Path(__file__).parent / "dataset" / "filter"
        keep_folder = Path(__file__).parent / "dataset" / "keep"

        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        self.samples: list[tuple[Path, int]] = (
            [(p, 1) for p in keep_folder.rglob("*") if p.suffix.lower() in exts] +
            [(p, 0) for p in filter_folder.rglob("*") if p.suffix.lower() in exts]
        )

    def __len__(self) -> int:
        """Return the total number of samples in the dataset."""
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[Image.Image, int]:
        """Load and return the sample at *index*.

        Args:
            index: Index of the sample to load.

        Returns:
            A ``(image, label)`` tuple, where ``image`` has had
            :attr:`transform` applied if one was provided.
        """
        path, label = self.samples[index]
        img: Image.Image = Image.open(path).convert('RGB')
        if self.transform:
            img = self.transform(img)
        return img, label
