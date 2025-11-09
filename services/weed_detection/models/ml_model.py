"""
Optional ML model for weed detection (patch classification / region scoring).
If no weights are available, fallback to heuristic detections is used.
"""

import torch
import torch.nn as nn
import torchvision.transforms as T
from torchvision.models import mobilenet_v3_small
import numpy as np
import cv2
from typing import Dict, List, Tuple

class WeedNet(nn.Module):
    def __init__(self, num_classes=2):
        super().__init__()
        self.backbone = mobilenet_v3_small(weights="DEFAULT")
        in_feats = self.backbone.classifier[3].in_features
        self.backbone.classifier[3] = nn.Linear(in_feats, num_classes)

    def forward(self, x):
        return self.backbone(x)

class MLWeedDetector:
    def __init__(self, weights_path: str | None = None, device: str = "cpu"):
        self.device = device
        self.model = WeedNet().to(self.device)
        self.model.eval()
        self.transform = T.Compose([
            T.ToTensor(),
            T.Resize((224,224)),
            T.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
        ])
        self.active = False
        if weights_path:
            try:
                state = torch.load(weights_path, map_location=self.device)
                self.model.load_state_dict(state, strict=False)
                self.active = True
            except Exception:
                self.active = False  # fallback

    @torch.inference_mode()
    def score_mask(self, bgr: np.ndarray, coarse_mask: np.ndarray) -> np.ndarray:
        """
        Optionally refine heuristic mask by classifying sampled patches.
        Returns refined binary mask (uint8).
        """
        bgr   = np.ascontiguousarray(bgr)
        coarse_mask= np.ascontiguousarray(coarse_mask)
        if not self.active:
            return coarse_mask
        mask = coarse_mask.copy()
        ys, xs = np.where(coarse_mask > 0)
        if len(ys) == 0:
            return coarse_mask

        # sample up to N points for refinement
        N = min(200, len(ys))
        idx = np.random.choice(len(ys), N, replace=False)
        H, W = bgr.shape[:2]
        for i in idx:
            y, x = ys[i], xs[i]
            y0, x0 = max(0, y-16), max(0, x-16)
            y1, x1 = min(H, y+16), min(W, x+16)
            patch = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
            patch = np.ascontiguousarray(patch)
            if patch.size == 0:
                continue
            inp = self.transform(patch).unsqueeze(0).to(self.device)
            logits = self.model(inp)
            prob = torch.softmax(logits, dim=1)[0,1].item()  # class 1 = weed
            if prob < 0.5:
                mask[y, x] = 0
        return mask
