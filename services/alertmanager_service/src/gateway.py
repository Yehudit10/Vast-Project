from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
import json, asyncio, logging


log = logging.getLogger(__name__)
app = FastAPI(title="AgGuard Alerts Gateway", version="1.0")

CLIENTS = set()

@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    CLIENTS.add(ws)
    log.info("Client connected.")
    # active = await fetch_active_alerts()
    try:
        # Send initial snapshot

        while True:
            # Wait for pings or keepalive from client
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                log.debug(f"Received message: {msg}")
            except asyncio.TimeoutError:
                # No message from client — send ping
                await ws.send_json({"type": "ping"})
                continue
    except WebSocketDisconnect:
        log.info("Client disconnected.")
    except Exception as e:
        log.exception(f"Error in WebSocket: {e}")
    finally:
        CLIENTS.discard(ws)


@app.post("/internal/alert")
async def internal_alert(request: Request):
    """Called by alert_service when a new alert is received."""
    alert = await request.json()
    msg = json.dumps({"type": "alert", "data": alert})
    dead = []
    for ws in CLIENTS:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)
    return {"status": "broadcasted"}



@app.get("/health")
async def health():
    return {"status": "ok"}

