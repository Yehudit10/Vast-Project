# Sensor Anomaly Detection
Real-time anomaly detection in environmental sensor data using Flink + Kafka + Python.

This project continuously monitors IoT sensor streams (e.g., Soil Moisture, Ambient Temperature, Humidity) and detects anomalies using statistical baselines and streaming analytics.

## Tech Stack
Python · Apache Flink · Apache Kafka · Docker · Pandas · Statsmodels

## Features
- Cleans and validates incoming sensor data.
- Builds statistical baselines:
  - Daily (hour of day)
  - Weekly (day of week + hour)
  - Seasonal (day of year + hour)
- Detects anomalies:
  - Band — value outside baseline ± 2×std  
  - Spike — sudden jump between consecutive values  
  - Break — sustained deviation from baseline
- Exports results to:
  - reports/anomalies_report.csv
  - reports/plots/
  - reports/models/ (saved baseline profiles)

## Project Structure
sensor-anomaly-pro/
├─ analyze_sensors.py       # Batch analysis on CSV data
├─ profiles_runtime.py      # Baseline export & real-time scoring
├─ app.py                   # Flink streaming job (Kafka → detection → Kafka)
├─ requirements.txt
├─ Dockerfile
├─ data/
│  └─ plant_health_data.csv
└─ tests/

## Environment Variables
| Variable | Description | Default |
|-----------|-------------|----------|
| KAFKA_BROKERS | Kafka broker address | kafka:9092 |
| IN_TOPIC | Input topic for raw telemetry | sensor-telemetry |
| OUT_TOPIC | Output topic for anomalies | sensor_anomalies |
| PYTHONPATH | Application base path | /opt/app/sensorAnomalyPro |

## Local (Batch Mode)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt

Run analysis:
set DATA_PATH=./data/plant_health_data.csv  # Windows
export DATA_PATH=./data/plant_health_data.csv  # Linux/macOS
python analyze_sensors.py

Run tests:
python -m pytest -q --maxfail=1 --disable-warnings --cov=. --cov-report=term-missing

## Docker
docker build -t sensor-anomaly-pro .
docker run --rm   -e DATA_PATH="/app/data/plant_health_data.csv"   -v "${PWD}/data:/app/data"   -v "${PWD}/reports:/app/reports"   sensor-anomaly-pro python analyze_sensors.py

## Real-Time Flow (Kafka + Flink)
The real-time pipeline connects Kafka and Flink for continuous anomaly detection.

| Component | Description |
|------------|-------------|
| Kafka Broker (kafka) | Handles telemetry input and anomaly output topics. |
| Flink JobManager / TaskManager | Executes app.py (the streaming anomaly detection job). |
| sensorAnomalyPro/app.py | Python Flink job that consumes, processes, and produces results. |

### Step-by-Step

#### 1️ Build and Start Services
```bash
docker-compose up -d --build
```

#### 2️ Submit the Flink Job
```bash
docker exec -it flink-jobmanager flink run -py /opt/app/sensorAnomalyPro/app.py

```

#### 3️ Send Sample Sensor Data
```bash
docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
```
Paste this:
```json

{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
PS C:\Users\user1\Desktop\AgCloud> docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
PS C:\Users\user1\Desktop\AgCloud> docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
PS C:\Users\user1\Desktop\AgCloud> docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
PS C:\Users\user1\Desktop\AgCloud> docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
PS C:\Users\user1\Desktop\AgCloud> docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
PS C:\Users\user1\Desktop\AgCloud> docker exec -i kafka kafka-console-producer.sh   --bootstrap-server localhost:9092   --topic dev-robot-telemetry-raw
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-10-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2025-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":55555555555588888888,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":555555555555555,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":555555555555555,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":37.2,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":555555555555555,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Ambient_Temperature","value":555555555555555,"lat":32.045,"lon":34.835}
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":555555555555555,"lat":32.055,"lon":34.845} 
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Ambient_Temperature","value":55,"lat":32.045,"lon":34.835}             
{"ts":"2024-11-02T12:00:00Z","plant_id":1,"sensor":"Soil_Moisture","value":32.1,"lat":32.048,"lon":34.836}
{"ts":"2024-11-02T12:00:05Z","plant_id":1,"sensor":"Ambient_Temperature","value":28.5,"lat":32.048,"lon":34.836}
{"ts":"2024-11-02T12:00:08Z","plant_id":2,"sensor":"Humidity","value":71.4,"lat":32.020,"lon":34.800}
{"ts":"2024-11-02T12:00:10Z","plant_id":2,"sensor":"Soil_Moisture","value":18.2,"lat":32.020,"lon":34.800}
{"ts":"2024-11-02T12:00:15Z","plant_id":3,"sensor":"Ambient_Temperature","value":44.9,"lat":32.090,"lon":34.910}
```

#### 4️ View Detected Anomalies
```bash
docker exec -it kafka kafka-console-consumer.sh --bootstrap-server kafka:9092 --topic sensor_zone_stats --from-beginning
docker exec -it kafka kafka-console-consumer.sh   --bootstrap-server localhost:9092   --topic sensor_anomalies   --from-beginning
```
Example output:
```json
{
  "plant_id": 1,
  "sensor": "Soil_Moisture",
  "ts": "2025-09-21T12:34:56Z",
  "value": 37.2,
  "result": {
    "ok": true,
    "is_anomaly": true,
    "bl_type": "seasonal",
    "baseline": 23.36,
    "adaptive_baseline": 23.39,
    "bias": 0.05,
    "lower": 7.60,
    "upper": 39.18,
    "band_std": 7.89,
    "flags": {"band": false, "spike": false, "break": true},
    "ema_abs_res": 13.83,
    "ts": "2025-09-21 12:34:56+00:00"
  }
}

```

---

##  Data Flow Diagram
```
  ┌──────────────┐      ┌────────────┐      ┌────────────────────────┐
  │ Sensors / IoT│ ---> │ Kafka Topic│ ---> │ Flink (app.py) detects │
  │ telemetry     │      │sensor-telemetry│  │ anomalies              │
  └──────────────┘      └────────────┘      └─────────────┬──────────┘
                                                          │
                                                          ▼
                                                Kafka Topic: sensor_anomalies
```

---

##  Notes
- **IN_TOPIC** = `sensor-telemetry`  
- **OUT_TOPIC** = `sensor_anomalies`  
- Kafka + Flink must share the same network (e.g., `agcloud_mesh`).  
- Rebuild after modifying `app.py`:
  ```bash
  docker-compose build jobmanager taskmanager
  ```

---

##  Troubleshooting
- Create topics manually if missing:
  ```bash
  docker exec -it kafka-single kafka-topics.sh     --create --topic sensor-telemetry     --bootstrap-server localhost:9092     --partitions 1 --replication-factor 1
  ```
- View logs:
  ```bash
  docker logs flink-jobmanager
  ```

---

##  License
MIT
branch shiffi-flink-sensor-connection