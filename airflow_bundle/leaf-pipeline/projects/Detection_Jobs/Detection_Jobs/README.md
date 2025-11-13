🌿 Agri Baseline – Disease Detection Pipeline

This project runs an end-to-end disease detection pipeline for agricultural images.
It supports both local and MinIO-based storage backends, and processes entire folders of plant images using trained CNN models.

🚀 Quick Start
1️⃣ Setup Environment
cp agri_baseline/.env.example agri_baseline/.env
pip install -r agri_baseline/requirements.txt

2️⃣ Run the Pipeline

Now the pipeline fetches images directly from MinIO, not from a local folder.

docker compose up -d
docker compose logs -f app


The service automatically connects to your configured MinIO bucket, downloads the images to a cache directory, and processes them.

3️⃣ Run Tests

To verify the system:

docker compose run --rm app pytest -q

📂 Project Structure
Detection_Jobs/
│
├── agri_baseline/
│   ├── scripts/
│   │   └── run_batch.py       # Run the pipeline on MinIO or local images
│   │
│   ├── src/
│   │   ├── detectors/          # CNN models and detectors
│   │   │   ├── base.py         # Base Detector/Detection classes
│   │   │   ├── cnn_multi_classifier.py
│   │   │   ├── disease_model.py  # Wraps CNN model as a Detector
│   │   │   ├── train/
│   │   │   │   └── dictionary.py
│   │   │
│   │   ├── pipeline/
│   │   │   ├── config.py
│   │   │   ├── db.py           # DB connection via SQLAlchemy
│   │   │   ├── logging_setup.py
│   │   │   └── utils.py        # Helper functions (image loading, bbox, etc.)
│   │   │
│   │   ├── storage/
│   │   │   ├── minio_client.py
│   │   │   └── minio_sync.py   # MinIO download helpers
│   │   │
│   │   └── validator/
│   │       ├── rules.py        # Validation rules
│   │       └── validator.py    # QA manager, writes to event logs
│   │
│   ├── batch_runner.py         # Orchestrates the full pipeline
│   ├── .env                    # Local config (not committed)
│   ├── .env.example            # Example configuration file
│   ├── requirements.txt        # Python dependencies
│   └── README.md
│
├── models/                     # Trained model weights (not in git)
│   ├── resnet18-f37072fd.pth
│   ├── cnn_multi_stage3.pth
│   └── multi_classes.pth
│
├── docker-compose.yml           # Runs pipeline + MinIO connection
├── dockerfile
├── tests/                       # Unit and integration tests
│   ├── test_batch_runner.py
│   ├── test_disease_model.py
│   ├── test_run_detectors.py
│   ├── test_utils.py
│   └── test_validator.py
│
└── ressearch/                   # Experimental models and training
    ├── detectors/
    │   ├── models/
    │   │   ├── cnn_binary.pth
    │   │   ├── cnn_multi_finetuned.pth
    │   │   └── cnn_multi.pth
    │   ├── train/
    │   │   ├── disease.py
    │   │   ├── eval_multi_levels.py
    │   │   ├── finetune_multi_stage3.py
    │   │   ├── finetune_multi.py
    │   │   └── train_binary_multi.py
    │   ├── cnn_binary_classifier.py
    │   └── dataset_binary.py

🧩 Models

All trained models are stored under models/ and are not committed to Git:

cnn_multi.pth – Base multi-class CNN

cnn_multi_finetuned.pth – Fine-tuned on additional data

cnn_multi_stage3.pth – Advanced fine-tuning with crop-specific data

multi_classes.pth – Unified class mapping

🧪 Testing

Run all integration and unit tests using Docker:

docker compose run --rm app pytest -q

📌 Notes

The pipeline now supports MinIO integration via environment variables in .env.

Make sure your .env file includes all required MINIO_* variables (endpoint, bucket, credentials).

Avoid committing .env or model files to the repository.