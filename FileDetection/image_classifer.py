from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import torch
import torch.nn as nn
import torchvision.models as models
from PIL import Image
from torch.nn.functional import softmax
from torch.utils.data import DataLoader, random_split
from torchvision import transforms

from image_classification_dataset import ImageClassificationDataset

# Module-level device selection so every model instance and tensor in this
# file shares one target device; printed once at import time for diagnostics.
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ── Model singleton ───────────────────────────────────────────────────────────
# The ImageClassifier (MobileNetV3-Large backbone + custom head) is expensive
# to construct and deserialize — doing it once per classify_image call was the
# primary cause of high CPU usage during backup. The singleton is loaded on
# first use and reused for every subsequent call. Double-checked locking keeps
# concurrent first-calls (up to MAX_CONCURRENT_RECEIVES threads) safe.
_cached_model: ImageClassifier | None = None
_model_lock: threading.Lock = threading.Lock()

# Confidence threshold above which a "remove" verdict is acted on automatically.
_REMOVE_THRESHOLD: float = 0.95
# Probability above which the model's argmax favours "remove" at all.
_REVIEW_THRESHOLD: float = 0.5


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


class ImageClassifier(nn.Module):
    """MobileNetV3-Large feature extractor with five trainable CNN layers on top.

    Frozen backbone: MobileNetV3-Large pretrained on ImageNet (features only).
    Trainable head: five ``Conv2d`` layers (with ``Dropout2d`` regularisation)
    → ``AdaptiveAvgPool2d`` → ``Linear`` classifier.

    The pretrained ``features`` backbone is fully frozen. All gradient
    updates during training flow only through ``custom_cnn`` and
    ``classifier``.

    Args:
        num_classes: Number of output classes (default: 2 — safe / unsafe).
    """

    def __init__(self, num_classes: int = 2) -> None:
        super().__init__()

        # ── Frozen pretrained backbone ────────────────────────────────────
        weights = models.MobileNet_V3_Large_Weights.DEFAULT
        backbone = models.mobilenet_v3_large(weights=weights)

        # Keep only the convolutional feature layers; discard the original
        # pooling and classifier heads so we can insert our own CNN layers.
        # Output shape after features: [B, 960, H, W]
        self.features = backbone.features
        for param in self.features.parameters():
            param.requires_grad = False

        # ── Five trainable CNN layers ─────────────────────────────────────
        # Pair A (layers 1-2): compress 960 → 512, then refine at 512.
        # Pair B (layers 3-4): compress 512 → 256, then refine at 256.
        # Layer 5: compress 256 → 128 before the global pool.
        # Dropout2d(0.3) after each pair regularises against overfitting on
        # the typically small training set.
        self.custom_cnn = nn.Sequential(
            # Layer 1: 960 → 512 channels
            nn.Conv2d(960, 512, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            # Layer 2: 512 → 512 channels (refinement)
            nn.Conv2d(512, 512, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.3),
            # Layer 3: 512 → 256 channels
            nn.Conv2d(512, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            # Layer 4: 256 → 256 channels (refinement)
            nn.Conv2d(256, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.3),
            # Layer 5: 256 → 128 channels
            nn.Conv2d(256, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
        )

        # ── Pooling + linear head ─────────────────────────────────────────
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.classifier = nn.Linear(128, num_classes)

        # ── Device placement ──────────────────────────────────────────────
        self.to(DEVICE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Run a forward pass through the classifier.

        Args:
            x: Input tensor of shape [B, 3, H, W].

        Returns:
            Raw class logits of shape [B, num_classes].
        """
        x = self.features(x)  # [B, 960, H, W]  — frozen
        x = self.custom_cnn(x)  # [B, 128, H, W]  — trainable
        x = self.pool(x)  # [B, 128, 1,  1]
        x = torch.flatten(x, 1)  # [B, 128]
        x = self.classifier(x)  # [B, num_classes]
        return x


def train_model(
        model: ImageClassifier,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: int = 10,
) -> None:
    """Train the classifier's unfrozen layers (custom_cnn + classifier head).

    The pretrained MobileNetV3 backbone is never updated — only parameters
    with ``requires_grad=True`` are passed to the optimizer.

    Args:
        model: The ImageClassifier instance to train.
        train_loader: DataLoader yielding ``(images, labels)`` batches.
            Images must be pre-processed with MobileNet_V3_Large_Weights
            transforms (224×224, normalized).
        val_loader: DataLoader yielding ``(images, labels)`` batches.
            Images must be pre-processed with MobileNet_V3_Large_Weights
            transforms (224×224, normalized).
        epochs: Number of full passes over the dataset (default: 10).
    """
    criterion = nn.CrossEntropyLoss()
    trainable_params = filter(lambda p: p.requires_grad, model.parameters())
    optimizer = torch.optim.Adam(trainable_params)

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0

        for x, y in train_loader:
            optimizer.zero_grad()
            prediction = model(x)
            loss = criterion(prediction, y)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()

        avg_loss = running_loss / len(train_loader)

        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for x, y in val_loader:
                prediction = model(x)
                val_loss += criterion(prediction, y).item()
                correct += (prediction.argmax(dim=1) == y).sum().item()
                total += len(y)

        avg_val_loss = val_loss / len(val_loader)
        val_acc = correct / total * 100
        print(
            f"Epoch [{epoch + 1}/{epochs}]  loss: {avg_loss:.4f}  val_loss: {avg_val_loss:.4f}  val_acc: {val_acc:.1f}%")


def test(image_model: ImageClassifier) -> None:
    """Evaluate a trained model against the held-out ``dataset/test`` split.

    Loads every image from ``dataset/test/keep`` (label 1) and
    ``dataset/test/filter`` (label 0), shuffles them, and runs inference one
    image at a time. Prints overall accuracy and the false-negative count
    (filter-worthy images predicted as "keep").

    Args:
        image_model: The trained :class:`ImageClassifier` to evaluate.
    """
    print("-------------------------Test Start---------------------")

    correct = 0
    total = 0
    fn = 0

    filter_folder = Path(__file__).parent / "dataset" / "test" / "filter"
    keep_folder = Path(__file__).parent / "dataset" / "test" / "keep"

    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    samples: list[tuple[Path, int]] = (
            [(p, 1) for p in keep_folder.rglob("*") if p.suffix.lower() in exts] +
            [(p, 0) for p in filter_folder.rglob("*") if p.suffix.lower() in exts]
    )
    random.shuffle(samples)

    image_model.eval()
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    with torch.no_grad():
        for x, y in samples:
            img = Image.open(x).convert('RGB')
            img_tensor = transform(img)
            output = softmax(image_model(img_tensor.unsqueeze(0)), dim=1)  # add batch dim
            predicted = 0 if output[0][0] > _REMOVE_THRESHOLD else 1
            if predicted == 0 and y == 1:
                fn += 1
            if predicted == y:
                correct += 1
            total += 1

    print(f"Test Accuracy: {correct / total * 100}%")
    print(f"Test False Negatives: {fn} / {total}")
    print("-------------------------Test Finished---------------------")


def _get_model(model_path: Path) -> ImageClassifier:
    """Return the module-level cached model, loading it from disk on first call.

    Thread-safe via double-checked locking — at most one thread performs the
    expensive instantiation + ``torch.load`` even when many slots call
    ``classify_image`` concurrently for the first time.

    Args:
        model_path: Path to the ``.pth`` weights file.

    Returns:
        The shared :class:`ImageClassifier` in eval mode.
    """
    global _cached_model
    if _cached_model is None:
        with _model_lock:
            if _cached_model is None:
                m = ImageClassifier()
                m.load_state_dict(
                    torch.load(str(model_path), map_location=DEVICE, weights_only=True)
                )
                m.eval()
                _cached_model = m
    return _cached_model


def classify_image(
        img: Path,
        model_path: Path = Path(__file__).parent / "model.pth",
) -> ClassificationResult:
    """Classify *img* and return a three-way :class:`ClassificationResult`.

    The underlying :class:`ImageClassifier` is loaded once and cached at
    module level — repeated calls (e.g. during a multi-file backup) reuse
    the same model instance and never touch disk again.

    Args:
        img: Path to the image file to classify.
        model_path: Path to the trained model weights (``.pth``).

    Returns:
        A :class:`ClassificationResult` describing the verdict
        (:attr:`ClassificationVerdict.ACCEPTED`,
        :attr:`ClassificationVerdict.REJECTED`, or
        :attr:`ClassificationVerdict.NEEDS_REVIEW`) and the raw
        ``pr(remove)`` confidence.
    """
    image_model = _get_model(model_path)

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    image = Image.open(img).convert('RGB')
    img_tensor = transform(image)

    with torch.no_grad():
        output = softmax(image_model(img_tensor.unsqueeze(0)), dim=1)
        confidence = float(output[0][0])

    if confidence > _REMOVE_THRESHOLD:
        verdict = ClassificationResult(ClassificationVerdict.REJECTED, confidence)
    elif confidence > _REVIEW_THRESHOLD:
        verdict = ClassificationResult(ClassificationVerdict.NEEDS_REVIEW, confidence)
    else:
        verdict = ClassificationResult(ClassificationVerdict.ACCEPTED, confidence)
    return verdict


def main() -> None:
    """Train, evaluate, and save the image classifier model.

    Builds an :class:`ImageClassifier`, trains it on
    :class:`~image_classification_dataset.ImageClassificationDataset` with
    augmentation transforms, evaluates it via :func:`test`, and saves the
    resulting weights to ``model.pth``.
    """
    image_model = ImageClassifier()

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.3, contrast=0.3),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])

    dataset = ImageClassificationDataset(transform=transform)

    train_size = int(len(dataset) * 0.8)
    val_size = len(dataset) - train_size

    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=True)

    train_model(image_model, train_loader, val_loader)

    test(image_model)

    save_path: Path = Path(__file__).parent / "model.pth"

    torch.save(image_model.state_dict(), str(save_path))
    image_model = ImageClassifier()
    image_model.load_state_dict(
        torch.load(str(save_path), map_location=DEVICE, weights_only=True)
    )


if __name__ == "__main__":
    main()
