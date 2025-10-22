import io
import json
from pathlib import Path
from typing import Dict, Tuple

import torch
from PIL import Image
from torchvision import models, transforms

def build_infer_transforms(image_size: int):
    return transforms.Compose([
        transforms.Resize(int(image_size * 1.14)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

def load_model(weights_path: Path, labels_json: Path, backbone: str, device: str = "cpu"):
    with open(labels_json, "r", encoding="utf-8") as f:
        class_to_idx = json.load(f)
    idx_to_class = {v: k for k, v in class_to_idx.items()}

    if backbone == "mobilenet_v3_small":
        m = models.mobilenet_v3_small()
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, len(idx_to_class))
    elif backbone == "efficientnet_b0":
        m = models.efficientnet_b0()
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, len(idx_to_class))
    else:
        raise ValueError(f"Unsupported backbone: {backbone}")

    state = torch.load(weights_path, map_location=device)
    m.load_state_dict(state["model"])
    m.eval().to(device)
    return m, idx_to_class

def infer_image_bytes(model, idx_to_class: Dict[int, str], img_bytes: bytes,
                      tfms, device: str = "cpu") -> Tuple[str, float]:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    x = tfms(img).unsqueeze(0).to(device)
    with torch.no_grad():
        logits = model(x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
    idx = int(probs.argmax())
    return idx_to_class[idx], float(probs[idx])
