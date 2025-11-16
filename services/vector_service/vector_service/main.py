
from fastapi import FastAPI
import asyncpg
import numpy as np
import os

app = FastAPI()

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "missions_user")
DB_PASS = os.getenv("DB_PASS", "pg123")
DB_NAME = os.getenv("DB_NAME", "missions_db")

@app.on_event("startup")
async def startup():
    import asyncio
    max_retries = 10
    for attempt in range(max_retries):
        try:
            app.state.conn = await asyncpg.connect(
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                host=DB_HOST,
                port=DB_PORT
            )
            print("✅ Connected to Postgres")
            return
        except Exception as e:
            print(f"⏳ Waiting for Postgres... attempt {attempt + 1}/{max_retries} ({e})")
            await asyncio.sleep(3)
    raise RuntimeError("❌ Could not connect to Postgres after several attempts")

@app.on_event("shutdown")
async def shutdown():
    await app.state.conn.close()

@app.post("/add_embedding")
async def add_embedding(vector: list[float]):
    vec_str = "[" + ",".join(str(x) for x in vector) + "]"
    await app.state.conn.execute("INSERT INTO embeddings (vec) VALUES ($1::vector)", vec_str)
    return {"status": "ok"}

@app.post("/search")
async def search(vector: list[float], limit: int = 5):
    vec_str = "[" + ",".join(str(x) for x in vector) + "]"
    rows = await app.state.conn.fetch(
        "SELECT id, vec <-> $1::vector AS distance FROM embeddings ORDER BY vec <-> $1::vector LIMIT $2;",
        vec_str, limit
    )
    return {"results": [{"id": r["id"], "distance": r["distance"]} for r in rows]}

@app.post("/generate_embeddings_from_sensors")
async def generate_embeddings_from_sensors():
    """
    שולף נתונים מטבלת sensors, יוצר מהם embeddings, ושומר אותם ב-DB יחד עם sensor_id.
    """
    rows = await app.state.conn.fetch("SELECT id, sensor_name, sensor_type, lat, lon, status FROM sensors;")
    if not rows:
        return {"message": "No sensors found."}

    inserted = 0
    for r in rows:
        sensor_id = r["id"]
        lat = r["lat"] or 0.0
        lon = r["lon"] or 0.0
        name_len = len(r["sensor_name"] or "")
        type_len = len(r["sensor_type"] or "")
        status_score = 1.0 if (r["status"] or "").lower() == "active" else 0.0

        # יצירת embedding פשוט
        vector = np.array([lat, lon, name_len, type_len, status_score], dtype=float)
        vec_str = "[" + ",".join(str(x) for x in vector) + "]"

        # שמירה ל-DB כולל sensor_id
        await app.state.conn.execute(
            "INSERT INTO embeddings (sensor_id, vec) VALUES ($1, $2::vector)",
            sensor_id, vec_str
        )
        inserted += 1

    print(f"✅ {inserted} embeddings inserted (with sensor_id).")
    return {"message": f"{inserted} embeddings generated from sensors (with sensor_id)."}
@app.get("/similar_sensors/{sensor_id}")
async def similar_sensors(sensor_id: int, limit: int = 5):
    # שליפת ה-embedding של הסנסור שביקשנו
    row = await app.state.conn.fetchrow(
        "SELECT vec FROM embeddings WHERE sensor_id=$1;", sensor_id
    )
    if not row:
        return {"message": f"No embedding found for sensor_id {sensor_id}"}

    vec = row["vec"]

    # שליפת הסנסורים הכי דומים לפי המרחק הווקטורי
    results = await app.state.conn.fetch(
        """
        SELECT e.sensor_id, e.vec <-> $1 AS distance,
               s.sensor_name, s.sensor_type, s.lat, s.lon, s.status
        FROM embeddings e
        JOIN sensors s ON e.sensor_id = s.id
        WHERE e.sensor_id <> $2
        ORDER BY distance
        LIMIT $3;
        """,
        vec, sensor_id, limit
    )

    # בניית התשובה
    return {
        "similar_sensors": [
            {
                "sensor_id": r["sensor_id"],
                "distance": r["distance"],
                "sensor_name": r["sensor_name"],
                "sensor_type": r["sensor_type"],
                "lat": r["lat"],
                "lon": r["lon"],
                "status": r["status"]
            }
            for r in results
        ]
    }
from datetime import datetime, timedelta

@app.get("/similar_sensors_advanced")
async def similar_sensors_advanced(
    sensor_id: int,
    same_day: bool = False,
    same_type: bool = False,
    same_status: bool = False,
    date_filter: str = None,
    limit: int = 5
):
    """
    Generic endpoint for flexible similarity queries.
    Supports filters:
    - same_day (bool)
    - same_type (bool)
    - same_status (bool)
    - date_filter ('today', 'yesterday', 'monday', 'last_wednesday', etc.)
    """

    # Fetch base sensor
    sensor = await app.state.conn.fetchrow("SELECT * FROM sensors WHERE id=$1;", sensor_id)
    if not sensor:
        return {"message": f"Sensor {sensor_id} not found."}

    base_date = sensor["install_date"].date()
    sensor_type = sensor["sensor_type"]
    status = sensor["status"]

    # Fetch embedding
    row = await app.state.conn.fetchrow("SELECT vec FROM embeddings WHERE sensor_id=$1;", sensor_id)
    if not row:
        return {"message": f"No embedding found for sensor {sensor_id}."}
    vec = row["vec"]

    # --- date_filter support ---
    start_date, end_date = None, None
    today = datetime.utcnow().date()
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }

    if date_filter:
        df = date_filter.lower()
        if df == "today":
            start_date, end_date = today, today
        elif df == "yesterday":
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif df.startswith("last_"):
            day = df.replace("last_", "")
            if day in weekdays:
                today_weekday = today.weekday()
                days_back = (today_weekday - weekdays[day] + 7) % 7 + 7
                target_day = today - timedelta(days=days_back)
                start_date, end_date = target_day, target_day
        elif df in weekdays:
            today_weekday = today.weekday()
            days_back = (today_weekday - weekdays[df] + 7) % 7
            target_day = today - timedelta(days=days_back)
            start_date, end_date = target_day, target_day

    # --- dynamic query ---
    query = """
        SELECT e.sensor_id, e.vec <-> $1 AS distance,
               s.sensor_name, s.sensor_type, s.install_date, s.status
        FROM embeddings e
        JOIN sensors s ON e.sensor_id = s.id
        WHERE e.sensor_id <> $2
    """
    params = [vec, sensor_id]
    param_idx = 3

    if same_day:
        query += f" AND DATE(s.install_date) = ${param_idx}"
        params.append(base_date)
        param_idx += 1

    if same_type:
        query += f" AND s.sensor_type = ${param_idx}"
        params.append(sensor_type)
        param_idx += 1

    if same_status:
        query += f" AND s.status = ${param_idx}"
        params.append(status)
        param_idx += 1

    if start_date and end_date:
        query += f" AND DATE(s.install_date) BETWEEN ${param_idx} AND ${param_idx + 1}"
        params.extend([start_date, end_date])
        param_idx += 2

    query += f" ORDER BY distance LIMIT ${param_idx};"
    params.append(limit)

    results = await app.state.conn.fetch(query, *params)

    return {
        "base_sensor": {
            "sensor_id": sensor_id,
            "sensor_name": sensor["sensor_name"],
            "sensor_type": sensor_type,
            "install_date": str(sensor["install_date"]),
            "status": status
        },
        "filters": {
            "same_day": same_day,
            "same_type": same_type,
            "same_status": same_status,
            "date_filter": date_filter
        },
        "similar_sensors": [
            {
                "sensor_id": r["sensor_id"],
                "distance": r["distance"],
                "sensor_name": r["sensor_name"],
                "sensor_type": r["sensor_type"],
                "install_date": str(r["install_date"]),
                "status": r["status"]
            }
            for r in results
        ]
    }
