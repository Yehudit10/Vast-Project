import json
import time
import pathlib
from typing import Dict, List
import requests
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import psycopg2
import psycopg2.extras
import os


# ---------- CONFIG ----------
DB_API_BASE = "http://db_api_service:8001"
DB_API_AUTH_MODE = "service"
DB_API_TOKEN_FILE = "/app/secrets/db_api_token"
DB_API_TOKEN = "auto"
DB_API_SERVICE_NAME = "GUI_H"


# ---------- TOKEN BOOTSTRAP ----------
def _safe_join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _read_token_from_file(path: str) -> str | None:
    p = pathlib.Path(path)
    if p.exists():
        token = p.read_text(encoding="utf-8").strip()
        return token or None
    return None

def _fetch_token_via_dev_bootstrap(base: str, retries: int = 3, backoff: float = 0.8) -> str | None:
    url = _safe_join_url(base, "/auth/_dev_bootstrap")
    payload = {"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": True}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code in (200, 201):
                data = r.json()
                raw = (data.get("service_account", {}) or {}).get("raw_token") \
                    or (data.get("service_account", {}) or {}).get("token")
                if raw and isinstance(raw, str) and "***" not in raw:
                    return raw.strip()
        except Exception:
            time.sleep(backoff * attempt)
    return None


def get_or_bootstrap_token() -> str | None:
    print(f"[DEBUG] Checking for existing token file at: {DB_API_TOKEN_FILE}", flush=True)

    if DB_API_TOKEN and DB_API_TOKEN.lower() != "auto":
        print(f"[DEBUG] Using static token from config", flush=True)
        return DB_API_TOKEN

    token = _read_token_from_file(DB_API_TOKEN_FILE)
    if token:
        print(f"[DEBUG] Loaded token from {DB_API_TOKEN_FILE}", flush=True)
        return token

    print(f"[DEBUG] No existing token found, bootstrapping via {DB_API_BASE}/auth/_dev_bootstrap", flush=True)
    token = _fetch_token_via_dev_bootstrap(DB_API_BASE)
    if token:
        pathlib.Path(DB_API_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(DB_API_TOKEN_FILE).write_text(token, encoding="utf-8")
        print(f"[BOOTSTRAP] wrote token to {DB_API_TOKEN_FILE}", flush=True)
        return token

    print("[BOOTSTRAP][ERROR] Failed to obtain token.", flush=True)
    return None


# ---------- API CLIENT ----------
class DashboardApi:
    def __init__(self):
        """Initialize DashboardApi with HTTP session and database connection parameters"""
        # HTTP API setup
        self.base = DB_API_BASE.rstrip("/")
        self.http = requests.Session()
        token = get_or_bootstrap_token()
        if token:
            if DB_API_AUTH_MODE == "service":
                self.http.headers.update({"X-Service-Token": token})
            else:
                self.http.headers.update({"Authorization": f"Bearer {token}"})
        self.http.headers.update({"Content-Type": "application/json"})
        self.http.mount("http://",  HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))
        self.http.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])))

        # Database connection parameters
        self.conn_params = {
            'host': os.getenv('PGHOST', 'postgres'),
            'port': int(os.getenv('PGPORT', 5432)),
            'database': os.getenv('PGDATABASE', 'missions_db'),
            'user': os.getenv('PGUSER', 'missions_user'),
            'password': os.getenv('PGPASSWORD', 'pg123')
        }
        print(f"[DashboardApi] Initialized with DB host={self.conn_params['host']}, db={self.conn_params['database']}", flush=True)

    def _get_connection(self):
        """Create and return a new database connection"""
        return psycopg2.connect(**self.conn_params)

    # ---------- EXISTING METHODS ----------

    def list_devices(self, model: str | None = None) -> list[dict]:
        """Get list of devices from API"""
        url = f"{self.base}/api/devices"
        if model:
            url += f"?model={model}"
        try:
            r = self.http.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
            print(f"[API ERROR] {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"[API FAIL] {e}")
        return []

    def bulk_set_task_thresholds_labeled(
        self,
        mapping: dict[tuple[str, str], float] | list[dict],
        updated_by: str = "gui",
    ) -> dict:
        """Bulk update task thresholds via API"""
        if isinstance(mapping, dict):
            items = [
                {"task": t, "label": l or "", "threshold": thr, "updated_by": updated_by}
                for (t, l), thr in mapping.items()
            ]
        else:
            items = mapping

        url = f"{self.base}/api/task_thresholds/batch"
        try:
            r = self.http.post(url, json=items, timeout=20)
            if r.status_code in (200, 201):
                data = r.json()
                return {
                    "ok": list(data.get("ok", [])),
                    "fail": list(data.get("fail", [])),
                }
            return {
                "ok": [],
                "fail": [[ [i.get("task"), i.get("label","")], f"http-{r.status_code} {r.text[:200]}"] for i in items],
            }
        except Exception as e:
            return {"ok": [], "fail": [[ [i.get("task"), i.get("label","")], str(e)] for i in items]}

    # =====================================================
    # ===== GENERIC QUERY METHOD =====
    # =====================================================
   
    def run_query(self, query: str, params: tuple | None = None) -> List[Dict]:
        """Execute a raw SQL query and return results as list of dicts"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
           
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
           
            results = cursor.fetchall()
            return [dict(row) for row in results]
           
        except Exception as e:
            print(f"[DashboardApi] Query error: {e}", flush=True)
            print(f"[DashboardApi] Query was: {query[:200]}...", flush=True)
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
   
    # =====================================================
    # ===== AUDIO ANALYTICS METHODS WITH SOUND FILTER =====
    # =====================================================
   
    def get_audio_stats(self, time_range: str = 'all', sound_types: List[str] = None) -> Dict:
        """Get aggregated audio classification statistics"""
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }.get(time_range, '')
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
       
        query = f"""
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN head_is_another = true THEN 1 ELSE 0 END) as unknown_count,
                AVG(head_pred_prob) as avg_confidence,
                AVG(processing_ms) as avg_processing_ms
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE 1=1 {time_filter} {sound_filter}
        """
       
        results = self.run_query(query)
        return results[0] if results else {}
   
    def get_audio_distribution(self, time_range: str = 'all', limit: int = 10, sound_types: List[str] = None) -> List[Dict]:
        """Get distribution of audio classifications"""
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }.get(time_range, '')
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
       
        query = f"""
            SELECT
                head_pred_label,
                COUNT(*) as count
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE head_pred_label IS NOT NULL {time_filter} {sound_filter}
            GROUP BY head_pred_label
            ORDER BY count DESC
            LIMIT {limit}
        """
       
        return self.run_query(query)
   
    def get_audio_confidence_by_class(self, time_range: str = 'all', limit: int = 10, sound_types: List[str] = None) -> List[Dict]:
        """Get average confidence levels by classification"""
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }.get(time_range, '')
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
       
        query = f"""
            SELECT
                head_pred_label,
                AVG(head_pred_prob) as avg_confidence
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE head_pred_label IS NOT NULL
              AND head_pred_prob IS NOT NULL
              {time_filter}
              {sound_filter}
            GROUP BY head_pred_label
            ORDER BY avg_confidence DESC
            LIMIT {limit}
        """
       
        return self.run_query(query)
   
    def get_audio_detailed_table(self, time_range: str = 'all', limit: int = 20, sound_types: List[str] = None) -> List[Dict]:
        """Get detailed table data with class probabilities"""
        time_filter = {
            'all': '',
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }.get(time_range, '')
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
       
        query = f"""
            SELECT
                head_pred_label,
                COUNT(*) as count,
                AVG(head_pred_prob) as avg_prob,
                AVG((head_probs_json->>'predatory_animals')::float) as p_predatory,
                AVG((head_probs_json->>'birds')::float) as p_birds,
                AVG((head_probs_json->>'fire')::float) as p_fire,
                AVG((head_probs_json->>'screaming')::float) as p_screaming,
                AVG((head_probs_json->>'shotgun')::float) as p_shotgun
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE head_pred_label IS NOT NULL {time_filter} {sound_filter}
            GROUP BY head_pred_label
            ORDER BY count DESC
            LIMIT {limit}
        """
       
        return self.run_query(query)
   
    def get_audio_critical_events(self, time_range: str = 'day', limit: int = 100, sound_types: List[str] = None) -> List[Dict]:
        """Get critical sound events"""
        time_filter = {
            'hour': "AND r.started_at > NOW() - INTERVAL '1 hour'",
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }.get(time_range, "AND r.started_at > NOW() - INTERVAL '24 hours'")
       
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
        else:
            sound_filter = "AND fa.head_pred_label IN ('fire', 'screaming', 'shotgun', 'predatory_animals')"
       
        query = f"""
            SELECT
                r.run_id,
                r.started_at,
                f.path as file_path,
                fa.head_pred_label as event_type,
                fa.head_pred_prob as confidence,
                fa.head_probs_json
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            JOIN agcloud_audio.files f ON fa.file_id = f.file_id
            WHERE 1=1
              {time_filter}
              {sound_filter}
            ORDER BY r.started_at DESC, fa.head_pred_prob DESC
            LIMIT {limit}
        """
       
        return self.run_query(query)
   
    def get_audio_timeline(self, time_range: str = 'day', sound_types: List[str] = None) -> List[Dict]:
        """Get audio alert timeline data grouped by time buckets"""
        bucket_interval = {
            'day': 1,
            'week': 6,
            'month': 24
        }.get(time_range, 1)
       
        time_filter_map = {
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }
        time_filter = time_filter_map.get(time_range, "AND r.started_at > NOW() - INTERVAL '24 hours'")
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
       
        query = f"""
            SELECT
                date_trunc('hour', r.started_at) +
                INTERVAL '{bucket_interval} hours' *
                (EXTRACT(hour FROM r.started_at)::int / {bucket_interval}) as time_bucket,
                fa.head_pred_label,
                COUNT(*) as count
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE fa.head_pred_label IS NOT NULL
              {time_filter}
              {sound_filter}
            GROUP BY time_bucket, fa.head_pred_label
            ORDER BY time_bucket ASC, count DESC
        """
       
        return self.run_query(query)
   
    def get_audio_heatmap(self, time_range: str = 'week', sound_types: List[str] = None) -> List[Dict]:
        """Get audio detection heatmap data - hour of day vs day of week"""
        time_filter_map = {
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }
        time_filter = time_filter_map.get(time_range, "AND r.started_at > NOW() - INTERVAL '7 days'")
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"
       
        query = f"""
            SELECT
                EXTRACT(HOUR FROM r.started_at) as hour_of_day,
                EXTRACT(DOW FROM r.started_at) as day_of_week,
                fa.head_pred_label as sound_type,
                COUNT(*) as count
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE fa.head_pred_label IS NOT NULL
            {time_filter}
            {sound_filter}
            GROUP BY hour_of_day, day_of_week, fa.head_pred_label
            ORDER BY day_of_week, hour_of_day
        """
       
        return self.run_query(query)
   
    def get_audio_correlations(self, time_range: str = 'day', sound_types: List[str] = None) -> List[Dict]:
        """Get sound detection data for correlation analysis using linked_time from sound_new_sounds_connections"""
        bucket_interval = {
            'day': 1,
            'week': 6,
            'month': 24
        }.get(time_range, 1)

        time_filter_map = {
            'day': "AND c.linked_time > NOW() - INTERVAL '24 hours'",
            'week': "AND c.linked_time > NOW() - INTERVAL '7 days'",
            'month': "AND c.linked_time > NOW() - INTERVAL '30 days'"
        }
        time_filter = time_filter_map.get(time_range, "AND c.linked_time > NOW() - INTERVAL '24 hours'")

        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_list})"

        query = f"""
            SELECT
                (date_trunc('hour', c.linked_time)
                    - (INTERVAL '1 hour' * (EXTRACT(hour FROM c.linked_time)::int % {bucket_interval}))
                ) AS time_bucket,
                fa.head_pred_label AS sound_type,
                COUNT(*) AS detection_count
            FROM agcloud_audio.file_aggregates fa
            JOIN public.sound_new_sounds_connections c
            ON c.id = fa.file_id
            WHERE fa.head_pred_label IS NOT NULL
            {time_filter}
            {sound_filter}
            GROUP BY time_bucket, fa.head_pred_label
            ORDER BY time_bucket ASC
        """

        return self.run_query(query)

    def get_model_health_metrics(self, time_range: str = 'day', sound_types: List[str] = None) -> List[Dict]:
        """Get model health metrics over time"""
        bucket_interval = {
            'day': 1,
            'week': 6,
            'month': 24
        }.get(time_range, 1)
       
        time_filter_map = {
            'day': "AND r.started_at > NOW() - INTERVAL '24 hours'",
            'week': "AND r.started_at > NOW() - INTERVAL '7 days'",
            'month': "AND r.started_at > NOW() - INTERVAL '30 days'"
        }
        time_filter = time_filter_map.get(time_range, "AND r.started_at > NOW() - INTERVAL '24 hours'")
       
        sound_filter = ""
        if sound_types and len(sound_types) > 0:
            sound_list = "'" + "','".join(sound_types) + "'"
            sound_filter = f"AND fa.head_pred_label IN ({sound_filter})"
       
        query = f"""
            SELECT
                date_trunc('hour', r.started_at) +
                INTERVAL '{bucket_interval} hours' *
                (EXTRACT(hour FROM r.started_at)::int / {bucket_interval}) as time_bucket,
                AVG(fa.head_pred_prob) as avg_confidence,
                AVG(fa.processing_ms) as avg_processing_ms,
                COUNT(*) as total_predictions,
                SUM(CASE WHEN fa.head_is_another = true THEN 1 ELSE 0 END) as unknown_count,
                (SUM(CASE WHEN fa.head_is_another = true THEN 1 ELSE 0 END)::float /
                 NULLIF(COUNT(*), 0)) * 100 as error_rate_pct
            FROM agcloud_audio.file_aggregates fa
            JOIN agcloud_audio.runs r ON fa.run_id = r.run_id
            WHERE fa.head_pred_label IS NOT NULL
              {time_filter}
              {sound_filter}
            GROUP BY time_bucket
            ORDER BY time_bucket ASC
        """
       
        return self.run_query(query)
   
    # =====================================================
    # ===== HELPER METHODS =====
    # =====================================================
   
    def get_sensors(self) -> List[Dict]:
        """Get all sensors"""
        query = "SELECT * FROM sensors ORDER BY sensor_name"
        return self.run_query(query)
   
    def get_sensor_status(self, sensor_name: str) -> Dict:
        """Get status of specific sensor"""
        query = "SELECT * FROM sensors WHERE sensor_name = %s"
        results = self.run_query(query, (sensor_name,))
        return results[0] if results else {}
   
    def get_alerts(self, limit: int = 50) -> List[Dict]:
        """Get recent alerts"""
        query = "SELECT * FROM alerts ORDER BY started_at DESC LIMIT %s"
        return self.run_query(query, (limit,))
   
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark alert as acknowledged"""
        conn = None
        cursor = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = "UPDATE alerts SET ack = true WHERE alert_id = %s"
            cursor.execute(query, (alert_id,))
            conn.commit()
            print(f"[DashboardApi] Alert {alert_id} acknowledged", flush=True)
            return True
        except Exception as e:
            print(f"[DashboardApi] Error acknowledging alert: {e}", flush=True)
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
   
    def get_ripeness_stats(self) -> Dict:
        """Get ripeness prediction statistics"""
        query = """
            SELECT
                COUNT(*) as total_predictions,
                SUM(CASE WHEN ripeness_label = 'ripe' THEN 1 ELSE 0 END) as ripe_count,
                SUM(CASE WHEN ripeness_label = 'unripe' THEN 1 ELSE 0 END) as unripe_count,
                SUM(CASE WHEN ripeness_label = 'overripe' THEN 1 ELSE 0 END) as overripe_count
            FROM ripeness_predictions
        """
        results = self.run_query(query)
        return results[0] if results else {}