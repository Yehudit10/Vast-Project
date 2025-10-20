# Dataset Spec — Fruit Defect Classification

## Source
- **Name**: Fruit and Vegetable Disease - Healthy vs Rotten (Kaggle-based)
- **Structure**: Two conditions (`Healthy`, `Rotten`) across multiple fruits and vegetables.
- **Usage in this project**: collapsed into **binary labels**:  
  - `ok` (healthy/fresh)  
  - `defect` (rotten/decayed/moldy)

## Local Path (outside git)
```
C:/Users/משתמש/Desktop/vectordb_efrat/Datasets/Fruit and Vegetable Disease - Healthy vs Rotten
```

Inside this folder:
```
train/
val/
test/
```

> **Note**: Dataset folders remain **outside git**. The model accesses them via config paths.

## Split
- Method: stratified random split by class (script `split_dataset.py`).
- Ratios: `train=0.8`, `val=0.1`, `test=0.1`.
- Seed fixed for reproducibility.

## Preprocessing
- Resize images to `192×192` (chosen to improve CPU latency while preserving accuracy).
- Normalize using ImageNet mean/std.
- Light augmentations (random flip, small color jitter) during training.

## Labels
- `ok`  ← all `Healthy` folders.  
- `defect` ← all `Rotten` folders.

## Metrics & Targets
- **Classification**:  
  - Accuracy: **98.91%**  
  - Precision: **99.22%**  
  - Recall: **98.71%**  
  - F1: **98.96%**  
- **Latency (CPU)**:  
  - TorchScript + 192 px → **p95 = 86.80 ms**  
  
- **Segmentation**: *not implemented*  
  - The dataset provides only **binary health labels**, without **lesion masks**.  
  - Alternative datasets checked (Strawberry, PlantSeg) either provided masks of whole leaves or leaf diseases, not fruit defects.  
  - As segmentation was optional in the acceptance criteria, we focused on classification.