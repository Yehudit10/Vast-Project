import psycopg2
import random
import time

# --- הגדרות חיבור ---
conn = psycopg2.connect(
    host="localhost",  # אם אתה בתוך docker-compose, תצטרך לשים את שם ה‑service
    port=5432,
    dbname="missions_db",
    user="missions_user",
    password="pg123"
)
cur = conn.cursor()

# --- צור טבלה אם לא קיימת ---
cur.execute("""
CREATE TABLE IF NOT EXISTS test (
    id serial PRIMARY KEY,
    value text
);
""")
conn.commit()

print("Starting simulated DB activity...")

try:
    while True:
        # --- הוספה של ערכים אקראיים ---
        new_value = str(random.randint(1, 1000000))
        cur.execute("INSERT INTO test (value) VALUES (%s)", (new_value,))
        conn.commit()
        print(f"Inserted: {new_value}")

        # --- עדכון ערכים קיימים כל 10 שורות ---
        update_value = str(random.randint(1, 1000000))
        print("Updating with:", update_value)
        cur.execute("UPDATE test SET value = '999999' WHERE (id % 10) = 0")

        conn.commit()

        print(f"Updated every 10th row to: {update_value}")

        # --- המתנה קצרה לפני הסיבוב הבא ---
        time.sleep(1)

except KeyboardInterrupt:
    print("Stopping simulation...")
finally:
    cur.close()
    conn.close()
