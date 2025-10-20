# Usage — Fruit Defect Classifier

## Project Path
```
C:/Users/משתמש/Desktop/vectordb_efrat/AgCloud/fruit-defect
```

## Install
Install required Python packages manually if no `requirements.txt` is provided.  
Typical dependencies include:
```bash
pip install torch torchvision torchaudio
pip install pillow numpy pyyaml tqdm scikit-learn tensorboard minio
```

## Config
Edit `configs/fruit_defect.yaml` with your dataset paths:

```yaml
data:
  train_dir: "C:/Users/משתמש/Desktop/vectordb_efrat/Datasets/Fruit and Vegetable Disease - Healthy vs Rotten/train"
  val_dir:   "C:/Users/משתמש/Desktop/vectordb_efrat/Datasets/Fruit and Vegetable Disease - Healthy vs Rotten/val"
  test_dir:  "C:/Users/משתמש/Desktop/vectordb_efrat/Datasets/Fruit and Vegetable Disease - Healthy vs Rotten/test"

model:
  backbone: "mobilenet_v3_small"
  img_size: 192

train:
  epochs: 8
  batch_size: 32
  lr: 3e-4
  weight_decay: 1e-4

paths:
  best_weights: "outputs/fruit_cls_best.pt"

inference:
  img_size: 192
```

## Train
```bash
python training/train_fruit_defect_cls.py
```
- Best weights saved to `outputs/fruit_cls_best.pt`.
- TensorBoard logs in `outputs/runs`:
```bash
python -m tensorboard.main --logdir outputs/runs
```

## Evaluate
```bash
python scripts/eval_cls.py
```
Example:
```json
{"accuracy": 0.9891, "precision": 0.9922, "recall": 0.9871, "f1": 0.9896}
```

## Inference (Local Folder)
```bash
python inference/infer_fruit_defect.py
```
- Reads from `data.test_dir` and writes `outputs/infer_results.json`.
- Console prints latency stats (p50/p90/p95).

## TorchScript (Optional)
```bash
python scripts/export_torchscript.py
```
Produces `outputs/fruit_cls_best.ts`. Inference auto-uses it if present.

## (Optional) MinIO Integration
- `scripts/infer_from_minio.py`: download images from MinIO prefix → run inference → upload JSON back.
- `scripts/upload_weights.py`: upload trained weights (`outputs/fruit_cls_best.pt`) to MinIO.

## .gitignore (recommended)
```
/outputs/
/**/train/
/**/val/
/**/test/
/**/*_masks/
```