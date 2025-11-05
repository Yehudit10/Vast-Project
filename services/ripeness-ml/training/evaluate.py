import torch, yaml, numpy as np, matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, roc_auc_score
from training.data import make_loaders
from models.mobilenet_v3_large_head import build_model

if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/config.yaml"))
    _, _, classes = make_loaders(cfg["train_dir"], cfg["val_dir"],
                                 cfg["img_size"], cfg["batch_size"], cfg["num_workers"])
    # test loader
    from torchvision import datasets
    from training.transforms import build_transforms
    _, t_val = build_transforms(cfg["img_size"])
    dtest = datasets.ImageFolder(cfg["test_dir"], transform=t_val)
    from torch.utils.data import DataLoader
    testloader = DataLoader(dtest, batch_size=cfg["batch_size"], shuffle=False, num_workers=cfg["num_workers"])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model(num_classes=len(classes))
    model.load_state_dict(torch.load(cfg["checkpoint_dir"]+"/best.pt", map_location=device))
    model.to(device).eval()

    y_true, y_prob = [], []
    with torch.no_grad():
        for x,y in testloader:
            x=x.to(device); logits = model(x)
            prob = logits.softmax(1).cpu().numpy()
            y_prob.append(prob); y_true.append(y.numpy())
    y_prob = np.vstack(y_prob); y_true = np.concatenate(y_true)
    y_pred = y_prob.argmax(1)

    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(classes))))
    ConfusionMatrixDisplay(cm, display_labels=classes).plot(xticks_rotation=45)
    plt.title("Confusion Matrix"); plt.tight_layout(); plt.savefig("confusion_matrix.png")
    try:
        roc = roc_auc_score(y_true, y_prob, multi_class="ovr")
        print(f"Test ROC-AUC(ovr): {roc:.3f}")
    except Exception as e:
        print("ROC-AUC skipped:", e)
