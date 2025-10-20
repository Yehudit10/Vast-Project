from pathlib import Path
import torch, yaml
from torchvision import models

cfg = yaml.safe_load(open("configs/fruit_defect.yaml","r",encoding="utf-8"))
img_size = int(cfg["model"]["img_size"])
weights = Path(cfg["paths"]["best_weights"])
assert weights.exists(), f"Missing weights: {weights}"

m = models.mobilenet_v3_small()
m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, 2)
state = torch.load(weights, map_location="cpu")
m.load_state_dict(state)
m.eval()

example = torch.randn(1, 3, img_size, img_size)
with torch.inference_mode():
    # trace "עדין": בלי freeze/optimize_for_inference כדי להימנע מהבאג בטעינה
    ts = torch.jit.trace(m, example, strict=False)

out = Path("outputs/fruit_cls_best.ts")
ts.save(str(out))
print("Saved TorchScript (safe trace):", out)
