
import json
from typing import Optional, Dict, Any
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

class DB:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def conn(self):
        conn = psycopg2.connect(self.dsn)
        try:
            yield conn
        finally:
            conn.close()

    def init_ok(self) -> bool:
        try:
            with self.conn() as c:
                with c.cursor() as cur:
                    cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def log_event(self, device_id: str, ts_iso: str, dry_ratio: float,
                  decision: str, confidence: float, patch_count: int,
                  idem_key: str, extra: Optional[Dict[str, Any]]=None) -> bool:
        q = '''
        INSERT INTO soil_moisture_events
        (device_id, ts, dry_ratio, decision, confidence, patch_count, idempotency_key, extra)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (idempotency_key) DO NOTHING
        '''
        with self.conn() as c:
            with c.cursor() as cur:
                cur.execute(q, (
                    device_id,
                    ts_iso,
                    dry_ratio,
                    decision,
                    confidence,
                    patch_count,
                    idem_key,
                    json.dumps(extra or {})
                ))
                c.commit()
                return cur.rowcount > 0

    def load_device_policy(self, device_id: str) -> dict:
        try:
            with self.conn() as c:
                with c.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute("""
                        SELECT prev_state, dry_ratio_high, dry_ratio_low,
                            min_patches, duration_min
                        FROM irrigation_policies
                        WHERE device_id = %s
                    """, (device_id,))
                    row = cur.fetchone()
                    if not row:
                        print(f"No row found for device_id={device_id}")
                        raise ValueError("not found")
                    print(f"Loaded from DB: {dict(row)}")
                    return dict(row)
        except Exception as e:
            print(f"Falling back to defaults because: {e}")
            # fallback defaults
            return {
                "prev_state": "stop",
                "dry_ratio_high": 0.35,
                "dry_ratio_low": 0.25,
                "min_patches": 2,
                "duration_min": 10
            }


    def upsert_schedule(self, device_id: str, next_run_at: str, duration_min: int,
                        updated_by: str, update_reason: str) -> None:
        with self.conn() as c:
            with c.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT next_run_at, duration_min FROM irrigation_schedule WHERE device_id=%s", (device_id,))
                prev = cur.fetchone()
                cur.execute('''
                INSERT INTO irrigation_schedule(device_id, next_run_at, duration_min, updated_by, update_reason)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (device_id) DO UPDATE SET
                    next_run_at=EXCLUDED.next_run_at,
                    duration_min=EXCLUDED.duration_min,
                    updated_by=EXCLUDED.updated_by,
                    update_reason=EXCLUDED.update_reason,
                    updated_at=NOW()
                ''', (device_id, next_run_at, duration_min, updated_by, update_reason))
                cur.execute('''
                INSERT INTO irrigation_schedule_audit(device_id, prev_next_run_at, prev_duration_min,
                                                    next_run_at, duration_min, updated_by, update_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (device_id,
                    prev["next_run_at"] if prev else None,
                    prev["duration_min"] if prev else None,
                    next_run_at, duration_min, updated_by, update_reason))
                c.commit()

    def update_prev_state(self, device_id: str, new_state: str) -> None:
        # default values for other new fields
        default_policy = {
            "dry_ratio_high": 0.35,
            "dry_ratio_low": 0.25,
            "min_patches": 2,
            "duration_min": 10
        }

        with self.conn() as c:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO irrigation_policies 
                        (device_id, prev_state, dry_ratio_high, dry_ratio_low, min_patches, duration_min)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE
                        SET prev_state = EXCLUDED.prev_state,
                            updated_at = NOW()
                """, (
                    device_id,
                    new_state,
                    default_policy["dry_ratio_high"],
                    default_policy["dry_ratio_low"],
                    default_policy["min_patches"],
                    default_policy["duration_min"]
                ))
                c.commit()

