# Disease Monitor (Offline)

Offline batch job that reads disease detections from **Postgres**, aggregates data,
builds baselines, detects anomalies/worsening, deduplicates & rate-limits alerts,
delivers notifications (Slack/Webhook/Email), and writes alerts back to **Postgres**.

> **Note:** The pipeline uses **Postgres only** (both sources and sink). No CSV/SQLite.

---

## Data Sources & Sink (Postgres)

**Sources**
- `anomalies`   — per-image detections (0..N rows per image)
- `tile_stats`  — exactly 1 row per image (summary)
- `event_logs`  — QA & validator logs (rules/metrics/errors)

**Sink**
- `alerts` — unified alerts table (rules: `COUNT_SPIKE`, `WORSENING_TREND`)

---

## Config (`configs/config.example.yaml`)

Main sections:
- **io**: Postgres URL (e.g. `postgresql+psycopg2://user:pass@host:5432/db`)
- **windows**: frequency (`"D"`/`"W"`), timezone (e.g. `"UTC"`)
- **baseline**: method (`mean`/`median`), lookback, min_history, optional seasonality
- **rules**: thresholds & toggles for `count_anomaly` (zscore/iqr) and `worsening` (slope/ewma)
- **alerting**: dedup cooldown (windows), resolve-after-no-anomaly, per-run rate limit, group_by_window
- **delivery**: slack/webhook/email targets (can be disabled)
- **run**: `dry_run` and optional filters

Example:
```yaml
io:
  postgres_url: "postgresql+psycopg2://missions_user:pg123@localhost:5432/missions_db"

windows:
  frequency: "D"
  timezone: "UTC"

baseline:
  method: "median"
  lookback_periods: 28
  min_history: 7
  seasonality: null

rules:
  count_anomaly:
    enabled: true
    method: "zscore"
    z_threshold: 3.0
    iqr_k: 1.5
    min_count: 3
  worsening:
    enabled: true
    method: "slope"
    slope_lookback: 7
    slope_min: 0.02
    min_periods: 5
    ewma_span: 7
    ewma_threshold: 0.6

alerting:
  dedup_cooldown_windows: 3
  resolve_after_no_anomaly: 3
  rate_limit_per_run: 100
  group_by_window: true

delivery:
  slack:
    enabled: false
    webhook_url: ""
  webhook:
    enabled: false
    url: ""
    headers: {}
  email:
    enabled: false
    smtp_host: ""
    smtp_port: 587
    username: ""
    password_env: "SMTP_PASSWORD"
    from_addr: ""
    to_addrs: []

run:
  dry_run: false
```

---

## Install & Run

```bash
# Create & activate venv (Linux/Mac)
python -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
# python -m venv .venv
# .venv\Scripts\Activate.ps1

# Install
pip install -r requirements.txt

# Run
python -m disease_monitor.cli   --config configs/config.example.yaml   --log-level INFO
```

---

## Tests

```bash
pytest
```

---


## Notes

- Thresholds, lookbacks, and active rules are fully configurable from YAML.
- Logs and runtime counters are emitted to stdout.
- Extend notifiers in `src/disease_monitor/notifiers`.
