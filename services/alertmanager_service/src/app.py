from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from alert_service import AlertManagerService
import os, logging

app = FastAPI(title="AgGuard AlertManager Service", version="1.3")
log = logging.getLogger(__name__)

# CFG_PATH = os.getenv("CFG_PATH", "templates.yml")
CFG_PATH = os.getenv("CFG_PATH", "/app/templates/templates.yml")

ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")

service = AlertManagerService(CFG_PATH, ALERTMANAGER_URL)


@app.post("/alerts")
async def post_alert(request: Request):
    """
    Receive an alert JSON payload and forward it to Alertmanager.
    """
    try:
        data = await request.json()
        result = service.process_alert(data)
        return JSONResponse({"status": "sent", "alert": result})
    except Exception as e:
        log.exception("Failed to process alert")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health():
    """Simple health check endpoint."""
    return {"status": "ok"}
