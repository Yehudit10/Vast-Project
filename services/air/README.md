# 📦 Model Installation Guide

This project requires **three machine-learning models** that are not stored in the repository due to size limits.  
Please download them from the following Google Drive folder:

👉 **Models Download Folder:**  
https://drive.google.com/drive/folders/1F0iMHbm3ahGOuoOWGWKY3frFxPw0mzRm?usp=sharing

The folder contains the following model files:

| Model Type           | File Name                    | Used By Service          |
|----------------------|------------------------------|---------------------------|
| Object Detection     | object_detection_api.pt      | infer-api                |
| Anomaly Detection    | anomaly_detection_api.pt     | anomaly-api              |
| Segmentation         | segmentation_api.pth         | segmentation-api         |

---

## 📥 1. Download the Models

Download all three files from the Google Drive folder:

- object_detection_api.pt  
- anomaly_detection_api.pt  
- segmentation_api.pth  

---

## 📁 2. Copy Each Model to Its Required Directory

### 🔹 Object Detection Model  
Copy to:
`services/air/object_detection_api/model/`

Expected final path:
`services/air/object_detection_api/model/object_detection_api.pt`

---

### 🔹 Anomaly Detection Model  
Copy to:
`services/air/anomaly_detection_api/models/`

Expected final path:
`services/air/anomaly_detection_api/models/anomaly_detection_api.pt`

---

### 🔹 Segmentation Model  
Copy to:
`services/air/segmentation_api/model/`

Expected final path:
`services/air/segmentation_api/model/segmentation_api.pth`

---

## ✅ 3. Verify the Installation

Ensure all three files exist in these exact locations:

- `services/air/object_detection_api/model/object_detection_api.pt`  
- `services/air/anomaly_detection_api/models/anomaly_detection_api.pt`  
- `services/air/segmentation_api/model/segmentation_api.pth`
