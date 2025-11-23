# Cross-Sensor System-Level Anomalies

# Model Artifacts

This folder stores the model artifacts required for anomaly detection.

The binary model files (**.pkl** / **.joblib**) are **not stored in the Git repository**, as they are large binary files that should not be tracked by Git.

Instead, you can download all required model files from Google Drive:

🔗 **Google Drive folder (all model artifacts):**  
https://drive.google.com/drive/folders/1QKRW5jTv3K-NmQLjMjfKqwgVu6JwrZsf?usp=drive_link

## How to use

1. Download all four model files from the Drive link.
2. Place them inside this `models/` directory.
3. The application will load them from here during runtime.

## Notes

- Do **not** upload model files back into Git.
- To prevent accidental uploads, ensure `.gitignore` includes:


## Overview

Unsupervised anomaly detection for agricultural sensor data using three complementary methods:

1. Isolation Forest (tree-based outlier model)
2. PCA Reconstruction Error (distance-from-low-rank structure)
3. Residual-per-Feature (OOF) with a robust HuberRegressor

We combine them into a hybrid decision:

* UNION (sensitive, higher recall)
* INTERSECTION (strict, higher precision)
* Majority (2-of-3) — good balance for high-confidence alerts.

Now fully integrated with Apache Flink streaming, consuming sensor JSON data from Kafka topics and producing anomaly alerts in real-time.

## Project Layout

docker-compose.yml                     # Build & run Flink + Kafka + job
flink_job.py                           # Flink job wrapping IF + PCA + Residual pipeline
detect_iforest_pca.py                  # Stage 1: IF + PCA + basic plots, intermediate CSV (used in batch mode)
detect_residuals_and_hybrid.py         # Stage 2: Residual OOF + Hybrid + 2-of-3 + hybrid plot (used in batch mode)
tests/                                 # Pytest-based tests (synthetic data fixtures included)
data/Crop_recommendationV2.csv        # Dataset (kept in repo)
out/                                    # Outputs (ignored by git)
Dockerfile                              # Build & run both stages
requirements.txt                        # Python dependencies
README.txt                               # This file

## Why these models?

* Isolation Forest: robust to high-dimensional mixed features; detects "few and different."
* PCA Recon Error: catches samples that don't fit global low-rank structure; complementary to IF.
* Residual-per-Feature (OOF): per-target predictive errors using KFold with no data leakage; highlights physically inconsistent sensor relationships (e.g., high soil moisture with very low rainfall).

## No-Leakage Residuals (critical)

Residuals are computed Out-Of-Fold:

* For each fold, we fit imputer + scaler + HuberRegressor on train only, then score the validation split.
* This prevents information leakage and over-optimistic errors.

## Streaming with Kafka & Flink

1. Start Kafka with Docker Compose:

   ```bash 
   docker compose -f docker-compose.yml up -d
   ```

2. Build and start Flink + job environment:

   ```bash
   docker compose up -d
   ```

3. Open Flink Web UI at [http://localhost:8084/](http://localhost:8084/) to monitor jobs.

4. Submit the Flink job:

   ```bash
   docker compose exec jobmanager flink run -py /opt/app/flink_job.py
   ```

5. Open two terminals for Kafka:

   * Producer (send JSON sensor data):

     ```bash
     docker exec -i kafka kafka-console-producer.sh --bootstrap-server localhost:9092 --topic sensors
     ```
   * Consumer (receive anomaly results):

     ```bash
     docker exec -it kafka kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic sensors_anomalies_modal --from-beginning
     ```

6. Example JSON input to producer:

```json
{"sid": "normal-01", "timestamp": 1690010100, "temperature": 24, "humidity": 55, "rainfall": 12, "soil_moisture": 45}
{"sid": "anomaly-01", "timestamp": 1690010150, "temperature": 100, "humidity": 0, "rainfall": 9999, "soil_moisture": 1000}
```

Consumer will output whether the sample is flagged as an anomaly or not.

## Outputs

out/dataset_with_iforest_pca.csv              # IF + PCA features/flags
out/pca_iforest_anomalies.png                 # PCA scatter with IF anomalies
out/dataset_hybrid_iforest_pca_residual.csv   # Final hybrid CSV with residual scores & flags
out/pca_hybrid_union.png                      # PCA scatter colored by hybrid union
out/top10_residual_rows.csv                   # Top-10 by residual_general_score (always created)

## Interpreting Results

* 'anomaly_union' is sensitive and best for broad monitoring.
* 'anomaly_2of3' is stricter and good as "high-confidence" alerting.
* Tune sensitivity via:

  * IsolationForest 'contamination'
  * PCA reconstruction error quantile
  * Residuals quantile (RES_Q)
* Choose thresholds to match your alert budget (~1–3% for 2-of-3 recommended).

## Notes

* Plots are saved headless (matplotlib Agg backend).
* The residual targets default to: soil_moisture, rainfall, temperature, humidity.
* top10_residual_rows.csv is always written (even if fewer than 10 rows exist).
* Streaming mode fully supports real-time detection via Flink and Kafka.
* Ensure Kafka is running before starting Flink jobs to avoid connectivity errors.
