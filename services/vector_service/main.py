from fastapi import FastAPI, HTTPException
import asyncpg
import numpy as np
import os
from datetime import datetime, timedelta

app = FastAPI()

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "missions_user")
DB_PASS = os.getenv("DB_PASS", "pg123")
DB_NAME = os.getenv("DB_NAME", "missions_db")


# =========================================================
#  STARTUP – CREATE CONNECTION POOL (SAFE)
# =========================================================
@app.on_event("startup")
async def startup():
    print("⏳ Creating Postgres pool...")
    try:
        app.state.pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            min_size=1,
            max_size=10,
        )
        # ensure pgvector exists
        async with app.state.pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        print("✅ Postgres connection pool ready.")
    except Exception as e:
        print(f"❌ Failed to connect to Postgres: {e}")
        raise


@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()
    print("🛑 Connection pool closed")


# =========================================================
#  Helper: Validate Embedding Vector
# =========================================================
def validate_vector(vec):
    if not isinstance(vec, list):
        raise HTTPException(400, "Vector must be a list of floats.")
    if len(vec) != 5:
        raise HTTPException(400, "Embedding vector must be length 5.")
    try:
        return [float(x) for x in vec]
    except:
        raise HTTPException(400, "Vector contains non-numeric values.")



# =========================================================
#  INSERT VECTOR  (sensor_embeddings)
# =========================================================
@app.post("/add_embedding")
async def add_embedding(sensor_id: int, vector: list[float]):
    vec = validate_vector(vector)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"

    async with app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sensor_embeddings (sensor_id, vec)
            VALUES ($1, $2::vector)
            """,
            sensor_id, vec_str
        )

    return {"status": "ok"}



# =========================================================
#  VECTOR SEARCH
# =========================================================
@app.post("/search")
async def search(vector: list[float], limit: int = 5):
    vec = validate_vector(vector)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"

    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, vec <-> $1::vector AS distance
            FROM sensor_embeddings
            ORDER BY distance
            LIMIT $2;
            """,
            vec_str, limit
        )

    return {"results": [{"id": r["id"], "distance": r["distance"]} for r in rows]}



# =========================================================
#  GENERATE EMBEDDINGS FROM SENSORS
# =========================================================
@app.post("/generate_embeddings_from_sensors")
async def generate_embeddings_from_sensors():

    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT sensor_id, sensor_name, sensor_type, lat, lon, status
            FROM sensors;
            """
        )

        if not rows:
            return {"message": "No sensors found."}

        inserted = 0

        for r in rows:
            sensor_id = r["sensor_id"]
            name_len = len(r["sensor_name"] or "")
            type_len = len(r["sensor_type"] or "")
            lat = r["lat"] or 0.0
            lon = r["lon"] or 0.0
            status_score = 1.0 if (r["status"] or "").lower() == "active" else 0.0

            # vector(5) is still your default
            vector = np.array([lat, lon, name_len, type_len, status_score], dtype=float)
            vec_str = "[" + ",".join(str(x) for x in vector) + "]"

            await conn.execute(
                """
                INSERT INTO sensor_embeddings (sensor_id, vec)
                VALUES ($1, $2::vector)
                """,
                sensor_id, vec_str
            )
            inserted += 1

        print(f"✅ {inserted} embeddings created.")
        return {"message": f"{inserted} embeddings generated."}



# =========================================================
#  FIND SIMILAR SENSORS BY SENSOR ID
# =========================================================
@app.get("/similar_sensors/{sensor_id}")
async def similar_sensors(sensor_id: int, limit: int = 5):

    async with app.state.pool.acquire() as conn:

        row = await conn.fetchrow(
            "SELECT vec FROM sensor_embeddings WHERE sensor_id=$1;",
            sensor_id
        )
        if not row:
            return {"message": f"No embedding found for sensor_id {sensor_id}"}

        vec = row["vec"]

        results = await conn.fetch(
            """
            SELECT e.sensor_id, e.vec <-> $1 AS distance,
                   s.sensor_name, s.sensor_type, s.lat, s.lon, s.status
            FROM sensor_embeddings e
            JOIN sensors s ON e.sensor_id = s.sensor_id
            WHERE e.sensor_id <> $2
            ORDER BY distance
            LIMIT $3;
            """,
            vec, sensor_id, limit
        )

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



# =========================================================
#  ADVANCED SIMILARITY SEARCH
# =========================================================
@app.get("/similar_sensors_advanced")
async def similar_sensors_advanced(
    sensor_id: int,
    same_day: bool = False,
    same_type: bool = False,
    same_status: bool = False,
    date_filter: str = None,
    limit: int = 5
):

    async with app.state.pool.acquire() as conn:

        sensor = await conn.fetchrow("SELECT * FROM sensors WHERE sensor_id=$1;", sensor_id)
        if not sensor:
            return {"message": f"Sensor {sensor_id} not found."}

        base_date = sensor["install_date"].date()
        sensor_type = sensor["sensor_type"]
        status = sensor["status"]

        row = await conn.fetchrow(
            "SELECT vec FROM sensor_embeddings WHERE sensor_id=$1;",
            sensor_id
        )
        if not row:
            return {"message": f"No embedding found for sensor {sensor_id}."}

        vec = row["vec"]

        # --- date logic ---
        today = datetime.utcnow().date()
        weekdays = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
        }

        start_date = end_date = None

        if date_filter:
            df = date_filter.lower()

            if df == "today":
                start_date = end_date = today

            elif df == "yesterday":
                start_date = end_date = today - timedelta(days=1)

            elif df.startswith("last_"):
                day = df.replace("last_", "")
                if day in weekdays:
                    today_wd = today.weekday()
                    days_back = (today_wd - weekdays[day] + 7) % 7 + 7
                    target = today - timedelta(days=days_back)
                    start_date = end_date = target

            elif df in weekdays:
                today_wd = today.weekday()
                days_back = (today_wd - weekdays[df] + 7) % 7
                target = today - timedelta(days=days_back)
                start_date = end_date = target

        # Base query
        query = """
            SELECT e.sensor_id, e.vec <-> $1 AS distance,
                   s.sensor_name, s.sensor_type, s.install_date, s.status
            FROM sensor_embeddings e
            JOIN sensors s ON e.sensor_id = s.sensor_id
            WHERE e.sensor_id <> $2
        """
        params = [vec, sensor_id]
        idx = 3

        if same_day:
            query += f" AND DATE(s.install_date) = ${idx}"
            params.append(base_date)
            idx += 1

        if same_type:
            query += f" AND s.sensor_type = ${idx}"
            params.append(sensor_type)
            idx += 1

        if same_status:
            query += f" AND s.status = ${idx}"
            params.append(status)
            idx += 1

        if start_date and end_date:
            query += f" AND DATE(s.install_date) BETWEEN ${idx} AND ${idx+1}"
            params.extend([start_date, end_date])
            idx += 2

        query += f" ORDER BY distance LIMIT ${idx}"
        params.append(limit)

        results = await conn.fetch(query, *params)

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
