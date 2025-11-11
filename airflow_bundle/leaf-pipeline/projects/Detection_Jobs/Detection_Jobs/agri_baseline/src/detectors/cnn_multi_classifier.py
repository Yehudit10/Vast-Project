# agri-baseline/src/detectors/cnn_multi_classifier.py
import torch.nn as nn
from torchvision import models

def build_multi_model(num_classes: int, pretrained: bool = True) -> nn.Module:
    """
    Builds a ResNet18 model for multi-class disease classification.
    """
    model = models.resnet18(weights="IMAGENET1K_V1" if pretrained else None)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, num_classes)
    return model
