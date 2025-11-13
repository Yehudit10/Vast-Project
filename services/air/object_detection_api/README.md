# Aerial Object Counter API

A lightweight FastAPI service that runs an object-detection model on aerial images and returns **counts per category** plus a **human‑readable summary**.  
Optionally, the service can **save annotated images** (with bounding boxes) to disk.

> **Outputs are English-only.** Every response includes:
>
> - `counts` — a JSON dictionary of `{class_name: count}`  
> - `summary_text` — a compact sentence (e.g., `177 buildings, 19 vehicles`)

---

## Overview

- **Model**: Ultralytics YOLO (weights file: `best.pt`).  
- **Wrapper**: `model_wrapper.py` normalizes class names to singular, clean keys.  
- **API**: `app.py` exposes two endpoints:
  - `POST /infer` — single image
  - `POST /infer_dir` — process an entire folder of images

Class set (12): `agri equipment, agri infra, building, rail, vessel, aviation, construction site, crane, tower, vehicle, container, yard`.

---

## Project Structure

```
object_counter_api/
├─ app.py               # FastAPI server + endpoints
├─ model_wrapper.py     # YOLOv8 loader + inference + draw/save utils
└─ requirements.txt     # dependencies
```

---

## Installation

> Recommended on Windows inside a virtual environment.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Place your trained weights file `best.pt` next to `app.py` (or change `WEIGHTS_PATH` at the top of `app.py`).

---

## Run the Server

```bat
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Health check (should return `{"status":"ok", ...}`):
```
http://127.0.0.1:8000/health
```

---

## Endpoints

### 1) `POST /infer` — Single Image

- **Always returns**: `counts` and `summary_text`
- **Optional**: save an annotated image to disk (`outputs/` by default)

**Query parameters**

| Name        | Type    | Default | Description                               |
|-------------|---------|---------|-------------------------------------------|
| `conf`      | float   | 0.25    | Confidence threshold                      |
| `iou`       | float   | 0.45    | NMS IoU threshold                         |
| `min_area`  | int?    | null    | Filter out tiny detections by pixel area  |
| `save_image`| bool    | false   | Save annotated image to disk              |
| `save_name` | string? | null    | Optional filename for saved image (PNG)   |

**Request (Windows CMD / Git Bash)**
```bash
curl -s -X POST "http://127.0.0.1:8000/infer?save_image=true&save_name=annotated_test.png" \
  -F "file=@C:/Users/USER/Desktop/only_yolo/dataset/xView_12cls_en/images/test/img_99_640_0.jpg"
```

**Response**
```json
{
  "counts": { "building": 177, "vehicle": 19 },
  "summary_text": "177 buildings, 19 vehicles"
}
```

If `save_image=true`, the annotated PNG is saved on the server (default folder `outputs/`), filename as provided via `save_name` or `annotated_<original>.png`.

---

### 2) `POST /infer_dir` — Entire Folder

Runs inference over all supported images in a directory.  
**Always returns**: aggregated `counts` and `summary_text`.  
**Optional**: save annotated images for each file.

**Body (JSON)**
```json
{
  "dir_path": "C:/path/to/images",
  "recursive": true,
  "save_images": true,
  "save_dir": "C:/path/to/outputs/batch1",
  "conf": 0.25,
  "iou": 0.45,
  "min_area": 400
}
```

**Example (Windows PowerShell / CMD)**
```bash
curl -s -X POST "http://127.0.0.1:8000/infer_dir" ^
  -H "Content-Type: application/json" ^
  -d "{\"dir_path\":\"C:/Users/USER/Desktop/only_yolo/dataset/images\",\"recursive\":true,\"save_images\":true,\"save_dir\":\"C:/Users/USER/Desktop/only_yolo/dataset/outputs/batch1\"}"
```

**Response**
```json
{
  "counts": { "building": 5200, "vehicle": 430 },
  "summary_text": "5200 buildings, 430 vehicles"
}
```

**Notes**

- Allowed extensions: `.jpg .jpeg .png .tif .tiff`
- If `save_images=true` and no detections found for a file, no image is saved for that file.

---

## Labels

```
GET /labels
```

Returns the model’s id→name mapping (normalized to clean, singular names).

---

## Configuration

At the top of `app.py`:

```python
WEIGHTS_PATH = "best.pt"     # path to your trained weights
OUTPUT_DIR   = Path("outputs")  # where annotated images are stored
```

You can change these to absolute paths if preferred.

---

## Troubleshooting

- **`ModuleNotFoundError: ultralytics`**  
  Ensure you run the server with the same Python where packages were installed. On Windows, check:
  ```bat
  where python
  python --version
  ```
  Then reinstall if needed:
  ```bat
  python -m pip install ultralytics
  ```

- **Different Python versions** (e.g., installed under Python 3.10 but server runs under 3.11)  
  Create a virtual env (see Installation) and run everything inside it.

- **Weights not found**  
  Verify that `best.pt` path matches `WEIGHTS_PATH` or place the file next to `app.py`.

---

## Security / Safety

- The API accepts local file paths (for `/infer_dir`). Do **not** expose this server publicly without proper authentication and sandboxing.
- For public deployments, add authentication, request size limits, and path validation.

---

## License

This repository contains example code and is provided “as is”, without warranty.  
Your trained model weights remain your property under your chosen license.

---

## Quick Checklist

- [ ] Put `best.pt` next to `app.py` (or change `WEIGHTS_PATH`).
- [ ] `pip install -r requirements.txt` in a virtual environment.
- [ ] `uvicorn app:app --host 0.0.0.0 --port 8000 --reload`
- [ ] Test single image with `/infer`.
- [ ] Test folder mode with `/infer_dir`.
