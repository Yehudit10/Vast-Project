from pathlib import Path
SAMPLE_PATH = Path(__file__).resolve().parent / "sample.ndjson"

import json
from prometheus_client import Counter, Histogram, start_http_server
from .schema import ImageMeta
from .validators import validate_semantics
from .db import upsert

INGEST_OK   = Counter("ingest_success_total", "successful ingestions")
INGEST_FAIL = Counter("ingest_fail_total", "failed ingestions")
INGEST_LAT  = Histogram("ingest_latency_ms", "ingest latency (ms)")

def handle_message(payload: dict):
    with INGEST_LAT.time():
        try:
            meta = ImageMeta.model_validate(payload)
            validate_semantics(meta)  # schema + business checks
            upsert(meta)              # idempotent write
            INGEST_OK.inc()
        except Exception as e:
            INGEST_FAIL.inc()
            # TODO: send to DLQ / structured log
            raise

def main():
    # Expose Prometheus metrics (adjust port as needed)
    start_http_server(9109)

    # Demo: read messages from a local NDJSON file
    # Each line is a JSON object that conforms to contract.md
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            handle_message(payload)

if __name__ == "__main__":
    main()
