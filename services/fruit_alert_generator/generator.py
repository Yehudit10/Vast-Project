
import psycopg2
from datetime import datetime, timedelta, timezone
import uuid, random, json, time, os

DB_HOST = os.getenv("PGHOST", "postgres")
DB_PORT = os.getenv("PGPORT", "5432")
DB_USER = os.getenv("PGUSER", "missions_user")
DB_PASS = os.getenv("PGPASSWORD", "pg123")
DB_NAME = os.getenv("PGDATABASE", "missions_db")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME
    )

# updated device list
devices = ["fruit-camera-01", "fruit-camera-02", "fruit-camera-03"]
severities = [1,2,3,4]

def insert_alert():
    conn = get_conn()
    cur = conn.cursor()

    alert_id = str(uuid.uuid4())
    alert_type = "fruit_defect_detected"
    device_id = random.choice(devices)
    started_at = datetime.now(timezone.utc)

    ended_at = (started_at + timedelta(minutes=random.randint(1,5))) if random.random() < 0.3 else None
    severity = random.choice(severities)
    confidence = round(random.uniform(0.4, 0.99), 2)

    lat = 31.751 + random.uniform(-0.005, 0.005)
    lon = 35.022 + random.uniform(-0.005, 0.005)
    image_url = f"https://minio-hot:9000/fake/{alert_id}.jpg"

    meta = {"generator": "fruit_alert_generator"}

    cur.execute(
        '''
        INSERT INTO alerts (
            alert_id, alert_type, device_id, started_at, ended_at,
            confidence, severity, image_url, lat, lon, area, meta,
            created_at, updated_at
        )
        VALUES (
            %(alert_id)s, %(alert_type)s, %(device_id)s, %(started_at)s, %(ended_at)s,
            %(confidence)s, %(severity)s, %(image_url)s, %(lat)s, %(lon)s,
            %(area)s, %(meta)s, now(), now()
        )
        ''',
        {
            "alert_id": alert_id,
            "alert_type": alert_type,
            "device_id": device_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "confidence": confidence,
            "severity": severity,
            "image_url": image_url,
            "lat": lat,
            "lon": lon,
            "area": None,
            "meta": json.dumps(meta)
        }
    )

    conn.commit()
    cur.close()
    conn.close()
    print(f"[GENERATOR] Inserted alert {alert_id} device={device_id} severity={severity}")

def main():
    print("Fruit Alert Generator started.")
    while True:
        insert_alert()
        time.sleep(30)

if __name__ == "__main__":
    main()
