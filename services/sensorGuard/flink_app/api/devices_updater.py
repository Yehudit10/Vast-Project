import requests
from datetime import datetime, timezone
from api.auth import get_access_token

def update_device_last_seen(device_id: str):
    """
    Updates the 'last_seen' field for a specific device in the devices_sensor table.
    Uses PATCH /api/tables/devices_sensor
    """
    api_base = "http://host.docker.internal:8001"
    token = get_access_token(api_base)
    headers = {
        "X-Service-Token": token,
        "Content-Type": "application/json"
    }
    url = f"{api_base}/api/tables/devices_sensor"

    payload = {
        "keys": {"id": device_id},
        "data": {"last_seen": datetime.now(timezone.utc).isoformat()}
    }

    try:
        r = requests.patch(url, json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"[DB-UPDATER] Updated last_seen for device {device_id}")
        else:
            print(f"[DB-UPDATER] Failed ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"[DB-UPDATER] Exception: {e}")
