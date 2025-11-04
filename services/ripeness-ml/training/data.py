from torch.utils.data import DataLoader
from torchvision import datasets
from .transforms import build_transforms

def make_loaders(train_dir, val_dir, img_size, batch_size, num_workers):
    t_train, t_val = build_transforms(img_size)
    dtrain = datasets.ImageFolder(train_dir, transform=t_train)
    dval   = datasets.ImageFolder(val_dir, transform=t_val)
    ltrain = DataLoader(dtrain, batch_size=batch_size, shuffle=True,  num_workers=num_workers, pin_memory=True)
    lval   = DataLoader(dval,   batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=True)
    return ltrain, lval, dtrain.classes
