## Quickstart (Windows PowerShell)

# 1) Create venv
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# 2) Prepare data (local folders)
# data/train|val|test with subfolders per class (unripe/ripe/overripe)

# 3) Train
python -m training.train

# 4) Evaluate (creates confusion_matrix.png + prints ROC-AUC)
python -m training.evaluate

# 5) Export to ONNX
python -m training.export_onnx

# 6) Local inference
python -m inference.infer_local path\to\image.jpg

# 7) Docker service for inference
docker build -t ripeness-ml:local .
docker run --rm -p 8080:8080 ripeness-ml:local
# POST /predict with image file
