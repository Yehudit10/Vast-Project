from .types import DeviceState
from typing import Dict, Set

class StateStore:
    def __init__(self):
        self._devices: Dict[str, DeviceState] = {}
        self._known_device_ids: Set[str] = set()

    @property
    def devices(self):
        """Expose internal devices dictionary (read-only)."""
        return self._devices

    def add_device(self, device_id: str, sensor_type: str = None) -> None:
        """Initialize state for a known device."""
        device_id = str(device_id)
        self._known_device_ids.add(device_id)
        if device_id not in self._devices:
            self._devices[device_id] = DeviceState(device_id=device_id, sensor_type=sensor_type)

    def get(self, device_id: str) -> DeviceState:
        """Return state for known device, or None if unknown."""
        device_id = str(device_id)
        return self._devices.get(device_id)

    def is_known_device(self, device_id: str) -> bool:
        """Check if device was loaded from API."""
        return str(device_id) in self._known_device_ids

    def all_states(self):
        """Iterator over all registered device states."""
        return self._devices.items()
