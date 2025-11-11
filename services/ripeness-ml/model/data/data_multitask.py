from torch.utils.data import Dataset, DataLoader
from PIL import Image
from torchvision import transforms
import pandas as pd

IMAGENET_MEAN=(0.485,0.456,0.406); IMAGENET_STD=(0.229,0.224,0.225)

def build_transforms(img_size=224):
    from torchvision import transforms as T
    t_train = T.Compose([
        T.RandomResizedCrop(img_size, scale=(0.7,1.0)),
        T.RandomHorizontalFlip(),
        T.ColorJitter(0.2,0.2,0.2,0.05),
        T.ToTensor(), T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    t_val = T.Compose([
        T.Resize(int(img_size*1.15)), T.CenterCrop(img_size),
        T.ToTensor(), T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    return t_train, t_val

class CSVConditional(Dataset):
    def __init__(self, csv_path, fruit_to_idx, ripeness_to_idx, transform=None):
        self.df = pd.read_csv(csv_path)
        self.fruit_to_idx = fruit_to_idx
        self.ripeness_to_idx = ripeness_to_idx
        self.transform = transform

    def __len__(self): return len(self.df)

    def __getitem__(self, i):
        row = self.df.iloc[i]
        img = Image.open(row["path"]).convert("RGB")
        if self.transform: img = self.transform(img)
        fruit_idx    = self.fruit_to_idx[row["fruit"]]
        ripeness_idx = self.ripeness_to_idx[row["ripeness"]]
        return img, fruit_idx, ripeness_idx

def make_loaders(csv_train, csv_val, img_size, batch_size, num_workers, fruits, ripeness):
    t_train, t_val = build_transforms(img_size)
    f2i = {f:i for i,f in enumerate(fruits)}
    r2i = {r:i for i,r in enumerate(ripeness)}
    dtr = CSVConditional(csv_train, f2i, r2i, t_train)
    dva = CSVConditional(csv_val,   f2i, r2i, t_val)
    from torch.utils.data import DataLoader
    ltr = DataLoader(dtr, batch_size=batch_size, shuffle=True,  num_workers=num_workers, pin_memory=True)
    lva = DataLoader(dva, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=True)
    return ltr, lva, f2i, r2i
