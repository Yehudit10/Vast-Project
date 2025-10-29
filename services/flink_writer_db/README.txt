
# flink_writer_db

Flink job that listens to Kafka topics and forwards each message to your DB API at:
    POST /api/<topic>
with the original message body (JSON).

## Quick start

1) Put your `netfree-ca.crt` next to `Dockerfile.flink` (required for HTTPS trust).
2) Ensure you have an external Docker network named `ag_cloud` and that your Kafka (`kafka:9092`) and DB API service (`db_api_service:8001`) are reachable on it.
3) Build & run:
   ```bash
   docker compose up -d --build
   ```

## Environment

- `KAFKA_BROKERS` (default `kafka:9092`)
- `TOPICS` (comma-separated; default `files`)
- `DB_API_BASE` (default `http://db_api_service:8001`)
- `DB_API_AUTH_MODE` (default `service` → uses `X-Service-Token` header)
- `DB_API_SERVICE_NAME` (default `flink-writer-db` for token bootstrap)
- `DB_API_TOKEN_FILE` (path to persist service token; default `/app/secrets/db_api_token`)
- `DUMMY_DB` (set `1` to log-only without calling the API)

## Logs & Debug

Follow logs:
```bash
docker logs -f flink_writer_db
```

Enter container shell:
```bash
docker exec -it flink_writer_db bash
```

Expected log lines when things work:
```
[FLINK] Listening on topic: files
[DB] wrote to files ✅
```

If a message is not valid JSON, you will see:
```
[WARN] skip invalid JSON on topic=files: '...'
```

If API is not reachable or times out, you'll see warnings or errors like:
```
[DB][WARN] API not reachable (http://db_api_service:8001): ...
[DB][WARN] API timeout (http://db_api_service:8001): ...
[DB][ERROR] ...
```

## Notes

- Token bootstrap uses `POST {DB_API_BASE}/auth/_dev_bootstrap` with `{"service_name": DB_API_SERVICE_NAME, "rotate_if_exists": true}`
  and stores the token at `DB_API_TOKEN_FILE`. Header is `X-Service-Token` when `DB_API_AUTH_MODE=service`.
- To listen to multiple topics, set e.g. `TOPICS=files,alerts,devices`.
