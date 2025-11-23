"""
api/devices_client.py
-----------------------------------
Fetches all active sensors (devices) from the API
and returns their IDs and models.
"""
import requests
from typing import Iterable, Tuple
from api.auth import get_access_token


def list_active_sensors(api_base: str, token: str, timeout: float = 10.0) -> Iterable[str]:
    """
    Fetch all sensors from the devices_sensor table.

    Args:
        api_base: Base URL of the API (e.g., "http://localhost:8001")
        token: Access token (returned from get_access_token)
        timeout: HTTP request timeout in seconds

    Yields:
        Device IDs as strings.
    """
    url = f"{api_base.rstrip('/')}/api/tables/devices_sensor"
    headers = {"X-Service-Token": token}

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            print(f"[DEVICES] Failed ({response.status_code}): {response.text[:120]}")
            return

        items = (response.json() or {}).get("rows", [])
        print(f"[DEVICES] Fetched {len(items)} sensors from API")
        for dev in items:
            # All sensors in table are active, just return the IDs
            device_id = dev.get("id", "")
            if device_id:
                print(f"[DEVICES] Adding sensor: id={device_id}")
                yield str(device_id)

    except requests.RequestException as e:
        print(f"[DEVICES] Request error: {e}")
        return


def get_sensors_last_seen(api_base: str = None, timeout: float = 10.0):
    """
    Fetch all sensors from devices_sensor with their last_seen timestamp.
    Used for silence sweep.
    
    Args:
        api_base: Base URL of the API. If None, uses host.docker.internal (same as PATCH).
        timeout: Request timeout.
        
    Returns:
        List of dicts like: [{"id": "dev-a", "sensor_type": "temp", "last_seen": "2025-11-11T13:00:00Z"}, ...]
    """
    # Use same URL pattern as update_device_last_seen (PATCH)
    if api_base is None:
        api_base = "http://host.docker.internal:8001"
    
    # Get fresh token each time (same pattern as update_device_last_seen)
    token = get_access_token(api_base)
    
    url = f"{api_base.rstrip('/')}/api/tables/devices_sensor"
    headers = {"X-Service-Token": token}

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            print(f"[DEVICES] Failed ({response.status_code}): {response.text[:120]}")
            return []

        items = (response.json() or {}).get("rows", [])
        print(f"[DEVICES] Fetched {len(items)} sensors (with last_seen) from API")
        return items

    except requests.RequestException as e:
        print(f"[DEVICES][ERROR] {e}")
        return []
