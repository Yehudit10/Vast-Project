import argparse, psycopg2, psycopg2.extras, json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://missions_user:pg123@127.0.0.1:5432/missions_db")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    conn = psycopg2.connect(args.dsn)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, device_id, ts, dry_ratio, decision, confidence, patch_count, idempotency_key
            FROM soil_moisture_events
            ORDER BY id DESC
            LIMIT %s
        """, (args.limit,))
        rows = cur.fetchall()
        print(json.dumps(rows, indent=2, default=str))
    finally:
        conn.close()

if __name__ == "__main__":
    main()
