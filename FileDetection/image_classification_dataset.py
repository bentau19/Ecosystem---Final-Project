from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset


class ImageClassificationDataset(Dataset):
    CLASSES = {0: "filter", 1: "keep"}

    def __init__(self, transform=None):
        super().__init__()
        self.transform = transform
        filter_folder = Path(__file__).parent / "dataset" / "filter"
        keep_folder = Path(__file__).parent / "dataset" / "keep"

        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        self.samples: list[tuple[Path, int]] = (
            [(p, 1) for p in keep_folder.rglob("*") if p.suffix.lower() in exts] +
            [(p, 0) for p in filter_folder.rglob("*") if p.suffix.lower() in exts]
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[Image.Image, int]:
        path, label = self.samples[index]
        img: Image.Image = Image.open(path).convert('RGB')
        if self.transform:
            img = self.transform(img)
        return img, label
