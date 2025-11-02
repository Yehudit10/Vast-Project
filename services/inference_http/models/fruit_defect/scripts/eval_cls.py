import yaml
from pathlib import Path
import torch
from torchvision import transforms, models
from torch.utils.data import Dataset, DataLoader
from PIL import Image
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

IMG_EXTS = {".jpg",".jpeg",".png",".bmp",".webp",".tif",".tiff"}

def label_from_path(p: Path) -> int:
    name = " ".join([s.lower() for s in p.parts])
    if "healthy" in name or "fresh" in name: return 0
    return 1

class DS(Dataset):
    def __init__(self, root, img_size):
        self.items = [p for p in Path(root).rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
        self.tf = transforms.Compose([
            transforms.Resize((img_size,img_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
        ])
    def __len__(self): return len(self.items)
    def __getitem__(self,i):
        p = self.items[i]; y = label_from_path(p)
        x = self.tf(Image.open(p).convert("RGB"))
        return x,y

def load_model(weights_path, backbone):
    if backbone=="mobilenet_v3_small":
        m = models.mobilenet_v3_small()
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, 2)
    else:
        m = models.resnet18()
        m.fc = torch.nn.Linear(m.fc.in_features, 2)
    m.load_state_dict(torch.load(weights_path, map_location="cpu"))
    m.eval()
    return m

if __name__=="__main__":
    cfg = yaml.safe_load(open("configs/fruit_defect.yaml","r",encoding="utf-8"))
    ds = DS(cfg["data"]["test_dir"], cfg["model"]["img_size"])
    dl = DataLoader(ds, batch_size=32, shuffle=False)
    m = load_model(cfg["paths"]["best_weights"], cfg["model"]["backbone"])
    ys, ps = [], []
    with torch.no_grad():
        for x,y in dl:
            pred = m(x).argmax(1)
            ys += y.tolist(); ps += pred.tolist()
    acc = accuracy_score(ys,ps)
    p,r,f1,_ = precision_recall_fscore_support(ys,ps,average="binary",zero_division=0)
    print({"accuracy":round(acc,4), "precision":round(p,4),"recall":round(r,4),"f1":round(f1,4)})
