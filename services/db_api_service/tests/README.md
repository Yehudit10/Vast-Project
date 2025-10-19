

## Docker (one command)

```bash
docker build -f tests/Dockerfile -t db-api-tests .
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 db-api-tests
```

## Locally (optional)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pip install pytest httpx
export ENV=dev
export DB_DRY_RUN=1
export DB_DSN="sqlite+pysqlite:///:memory:"
pytest -q tests
```

Notes:
- Files tests use `client_overridden_auth` to bypass auth (router dependency) and validate DRY-RUN spooling.
- Auth tests use real auth (no override) with `bootstrap_tokens` fixture.
