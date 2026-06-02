"""
Image classifier for ML-based content detection (detector.py stage 3).

Architecture
------------
Frozen backbone  : MobileNetV3-Large pretrained on ImageNet (features only).
Trainable head   : two Conv2d layers → AdaptiveAvgPool2d → Linear classifier.

Only the two custom CNN layers and the linear head are updated during
training; the backbone weights stay static throughout.
"""
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torchvision.models as models
from torch.nn.functional import softmax
from torch.utils.data import DataLoader, random_split
from torchvision import transforms
from PIL import Image

from image_classification_dataset import ImageClassificationDataset

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"using device: {device.type}")


class ImageClassifier(nn.Module):
    """
    MobileNetV3-Large feature extractor with two trainable CNN layers on top.

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

        # ── Two trainable CNN layers ──────────────────────────────────────
        # Layer 1: 960 → 512 channels
        # Layer 2: 512 → 256 channels
        self.custom_cnn = nn.Sequential(
            nn.Conv2d(960, 512, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(512),
            nn.ReLU(inplace=True),
            nn.Conv2d(512, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
        )

        # ── Pooling + linear head ─────────────────────────────────────────
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.classifier = nn.Linear(256, num_classes)

        # ── Device placement ──────────────────────────────────────────────
        self.to(device)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Run a forward pass through the classifier.

        Args:
            x: Input tensor of shape [B, 3, H, W].

        Returns:
            Raw class logits of shape [B, num_classes].
        """
        x = self.features(x)  # [B, 960, H, W]  — frozen
        x = self.custom_cnn(x)  # [B, 256, H, W]  — trainable
        x = self.pool(x)  # [B, 256, 1,  1]
        x = torch.flatten(x, 1)  # [B, 256]
        x = self.classifier(x)  # [B, num_classes]
        return x


def train_model(
        model: ImageClassifier,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: int = 10,
) -> None:
    """
    Train the classifier's unfrozen layers (custom_cnn + classifier head).

    The pretrained MobileNetV3 backbone is never updated — only parameters
    with ``requires_grad=True`` are passed to the optimizer.

    Args:
        model:      The ImageClassifier instance to train.
        train_loader: DataLoader yielding ``(images, labels)`` batches.
                    Images must be pre-processed with MobileNet_V3_Large_Weights
                    transforms (224×224, normalized).
        val_loader:  DataLoader yielding ``(images, labels)`` batches.
                    Images must be pre-processed with MobileNet_V3_Large_Weights
                    transforms (224×224, normalized).
        epochs:     Number of full passes over the dataset (default: 10).
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


def main(argc: int, argv: list[str]):
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

    image_model.eval()

    img = Image.open(Path(__file__).parent / "26720.jpg")
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    img_tensor = transform(img)

    with torch.no_grad():
        output = softmax(image_model(img_tensor.unsqueeze(0)), dim=1)  # add batch dim
        predicted = output.argmax(dim=1)
        print(output)
        print(predicted)


if __name__ == "__main__":
    main(len(sys.argv), sys.argv)
