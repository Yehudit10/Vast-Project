# Plant Stress Daily Job
This service runs **once per day**.
It loads a pre-trained ML model, reads audio files from MinIO, predicts plant stress, writes results to PostgreSQL, **and if stress is detected, it sends an alert message to Kafka**.


---


## Download Model Files
Download the required model files from:
https://drive.google.com/drive/folders/17iXRnP-a5_6wt_tS4ieLKkUlUlU5IhDT?usp=sharing
Place all files in a folder named **`AgCloud/services/plant_stress/models/`** in the project root.