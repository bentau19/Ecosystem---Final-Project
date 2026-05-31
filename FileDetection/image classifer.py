import torch.nn as nn
import torchvision.models as models
import torch
from torch.utils.data import dataloader


class ImageClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.weights = models.MobileNet_V3_Large_Weights.DEFAULT
        self.model = models.mobilenet_v3_large(weights=self.weights)
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"using device: {self._device.type}")

    def forward(self, x: torch.Tensor):
        pass


def train_model(model: ImageClassifier):
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters())
    epochs = 10
    for epoch in range(epochs):
        for x, y in dataloader:
            optimizer.zero_grad()
            prediction = model(x)
            loss = criterion(prediction, y)
            loss.backward()
            optimizer.step()


if __name__ == '__main__':
    image_model = ImageClassifier()
