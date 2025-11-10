# agri-baseline/src/detectors/cnn_binary_classifier.py
import torch.nn as nn
from torchvision import models

def build_binary_model(pretrained: bool = True) -> nn.Module:
    """
    Builds a ResNet18 model for binary classification (healthy vs diseased).
    """
    model = models.resnet18(weights="IMAGENET1K_V1" if pretrained else None)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, 2)  # healthy / diseased
    return model
