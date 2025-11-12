🥭 Fruit Classification – Inference Service

This service performs batch inference for fruit classification using a trained PyTorch model.
It connects to MinIO for input images and logs results into PostgreSQL.

⚙️ 1. Environment Configuration

Create a .env file in the project root with the following variables:

# --- MinIO Connection ---
S3_ENDPOINT=http://host.docker.internal:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_SECURE=false
S3_BUCKET=classification
S3_PREFIX=samples

# --- Model & Config Paths ---
WEIGHTS_PATH=models/best.pt
LABELS_PATH=models/labels.json
CFG_PATH=configs/fruit_cls.yaml

# --- Database Connection ---
DATABASE_URL=postgresql://missions_user:pg123@host.docker.internal:5432/missions_db?sslmode=disable


🧠 Tip:
If your PostgreSQL or MinIO services run on external servers, update host.docker.internal to the relevant hostname or IP.

🔒 2. Certificates (Optional)

If your environment requires SSL interception (e.g., behind filtered networks like NetFree),
add the certificate file (e.g. netfree-ca.crt) to the project root —
it will be installed into the Docker image automatically.

🐳 3. Build the Docker Image
docker compose build

▶️ 4. Run the Service
docker compose up


This will:

Load the model and configuration.

Fetch images from MinIO (s3://classification/samples/...).

Perform inference.

Write classification results to the PostgreSQL inference_logs table.

✅ 5. Prerequisites Checklist

Before running the service, make sure you have:

Component	Requirement
PostgreSQL	A database named missions_db containing a table inference_logs.
MinIO	Bucket: classification, prefix: samples/.
Data Folder Structure	samples/<year>/<month>/<day>/ containing image files.

Example MinIO path:

classification/
 └── samples/
     └── 2025/
         └── 10/
             └── 15/
                 ├── apple1.png
                 ├── freshGrape (7).jpg
                 └── ...

🧩 Example Output
[INFO] s3://classification/samples/2025/10/15/ | secure=False
{"object": "samples/2025/10/15/apple1.png", "fruit_type": "Apple", "score": 0.9258}
{"object": "samples/2025/10/15/freshOrange.png", "fruit_type": "Orange", "score": 0.9123}
[DONE] processed=25 | date=2025-10-15

🛠️ Notes

The service automatically retries MinIO connections.

Database inserts are skipped if the connection fails (with a warning).

To rebuild dependencies or configuration, use docker compose up --build.