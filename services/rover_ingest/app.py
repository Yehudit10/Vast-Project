from pathlib import Path
SAMPLE_PATH = Path(__file__).resolve().parent / "sample.ndjson"

import json, time
from prometheus_client import Counter, Histogram, start_http_server
from .schema import ImageMeta
from .validators import validate_semantics
# from .db import upsert
from . import db

INGEST_OK   = Counter("ingest_success_total", "successful ingestions")
INGEST_FAIL = Counter("ingest_fail_total", "failed ingestions")
INGEST_LAT  = Histogram("ingest_latency_ms", "ingest latency (ms)")

def handle_message(payload: dict):
    with INGEST_LAT.time():
        try:
            meta = ImageMeta.model_validate(payload)
            validate_semantics(meta)  # schema + business checks
            # upsert(meta)     
            db.upsert(meta)         # idempotent write
            INGEST_OK.inc()
        except Exception as e:
            INGEST_FAIL.inc()
            # TODO: send to DLQ / structured log
            # raise
            print(f"[ingest] ERROR: {e}")


def main():
    # Expose Prometheus metrics (adjust port as needed)
    start_http_server(9109, addr="0.0.0.0")
    print("[ingest] metrics server on :9109")

    # Demo: read messages from a local NDJSON file
    # Each line is a JSON object that conforms to contract.md
    try:
        with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                handle_message(payload)
                time.sleep(0.05)  # tiny pacing; optional
        print("[ingest] demo NDJSON finished")
    except FileNotFoundError:
        print(f"[ingest] NDJSON not found at {SAMPLE_PATH} - staying alive")

    # Keep the process alive so /metrics remains reachable
    while True:
        time.sleep(3600)

if __name__ == "__main__":
    main()
