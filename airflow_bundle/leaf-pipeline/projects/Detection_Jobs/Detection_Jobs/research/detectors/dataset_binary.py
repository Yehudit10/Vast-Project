# agri-baseline/src/detectors/dataset_binary.py
import os
from torch.utils.data import Dataset
from PIL import Image

class BinaryDiseaseDataset(Dataset):
    """
    Dataset wrapper that maps:
      - healthy folders -> label 0
      - all disease folders -> label 1
    Keeps also the original folder name for optional subtype info.
    """
    def __init__(self, root: str, transform=None):
        self.samples = []
        
        self.targets = [] 
        self.transform = transform
        for cls in os.listdir(root):
            path = os.path.join(root, cls)
            if not os.path.isdir(path):
                continue
            label = 0 if "healthy" in cls.lower() else 1
            for f in os.listdir(path):
                if f.lower().endswith((".jpg", ".png", ".jpeg")):
                    self.samples.append((os.path.join(path, f), label, cls))
                    self.targets.append(label)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label, cls_name = self.samples[idx]
        img = Image.open(path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, label, cls_name
