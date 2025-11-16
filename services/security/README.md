# AgGuard Model Weights

This directory contains the model weight files required for the AgGuard Security service.

The weights **are not stored in Git** because they are large.  
You must download them manually from Google Drive and place them directly in this folder.

---

## 📥 1. Download Model Weights

Download the following files from our shared Google Drive folder:

🔗 **Google Drive (AgGuard Models)**  
https://drive.google.com/drive/u/0/folders/1Qu7F4eG2XcINoUWFZt-1qpBQmRiPECPG

Files you should download:

```
mask_yolov8.onnx
yolov8n-cls.pt
```

---

## 📁 2. Copy Files Into This Folder

After downloading, copy BOTH files into:

```
services/security/weights/
```

The final structure must look exactly like this:

```
services/security/weights/
│
├── mask_yolov8.onnx
└── yolov8n-cls.pt
```

No subfolders.  
No renaming.

---

## ⚠️ Important

- Do **not** commit these files to Git.
- Do **not** rename the files.
- Anytime a new or updated weight is added to Google Drive, download it again and replace it here.

---

## ❓ Need help?

Ask Yehudit or the AgGuard developers if you are unsure about any of the required weight files.
