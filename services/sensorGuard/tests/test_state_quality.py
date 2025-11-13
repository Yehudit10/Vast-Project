"""
Professional, comprehensive tests for StateStore class.
These tests verify data integrity and state management correctness.
"""
import pytest
from datetime import datetime, timezone, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flink_app'))

from core.state import StateStore
from core.types import DeviceState, Alert


class TestStateStoreDataIntegrity:
    """Tests that verify data integrity and correct state management."""
    
    def setup_method(self):
        """Set up fresh StateStore for each test."""
        self.state_store = StateStore()
    
    def test_add_device_creates_proper_state_structure(self):
        """CRITICAL: Adding device must create correct internal state structure."""
        # Arrange
        device_id = "sensor_001" 
        sensor_type = "temperature"
        
        # Act: Add device
        self.state_store.add_device(device_id, sensor_type)
        
        # Assert: Device should be in known devices
        assert self.state_store.is_known_device(device_id)
        
        # Assert: Device state should be properly initialized
        device_state = self.state_store.get(device_id)
        assert device_state is not None
        assert device_state.device_id == device_id
        assert device_state.sensor_type == sensor_type
        assert device_state.last_seen_ts is None  # Should start as None
        assert device_state.last_value is None    # Should start as None
        assert device_state.open_alerts == {}     # Should start empty
    
    def test_get_unknown_device_returns_none_safely(self):
        """CRITICAL: Getting unknown device must return None, not crash."""
        # Act: Try to get device that was never added
        result = self.state_store.get("nonexistent_device")
        
        # Assert: Should return None safely
        assert result is None
        
        # Assert: Should not be considered known
        assert not self.state_store.is_known_device("nonexistent_device")
    
    def test_device_state_persistence_across_operations(self):
        """CRITICAL: Device state changes must persist correctly."""
        # Arrange: Add device and get its state
        device_id = "persistent_device"
        self.state_store.add_device(device_id, "humidity")
        device_state = self.state_store.get(device_id)
        
        # Act: Modify device state
        test_time = datetime.now(timezone.utc)
        test_value = 42.7
        test_alert = Alert(
            issue_type="test_alert",
            device_id=device_id,
            sensor_type="humidity", 
            site_id="test_site",
            severity="warning",
            start_ts=test_time,
            end_ts=None,
            details={"test": "data"}
        )
        
        device_state.last_seen_ts = test_time
        device_state.last_value = test_value  
        device_state.open_alerts["test_alert"] = test_alert
        
        # Assert: Changes should persist when retrieving again
        retrieved_state = self.state_store.get(device_id)
        assert retrieved_state.last_seen_ts == test_time
        assert retrieved_state.last_value == test_value
        assert "test_alert" in retrieved_state.open_alerts
        assert retrieved_state.open_alerts["test_alert"].issue_type == "test_alert"
    
    def test_multiple_devices_maintain_separate_states(self):
        """CRITICAL: Multiple devices must have completely separate states."""
        # Arrange: Add multiple devices
        device1 = "temp_sensor_01"
        device2 = "humid_sensor_02" 
        device3 = "pressure_sensor_03"
        
        self.state_store.add_device(device1, "temperature")
        self.state_store.add_device(device2, "humidity")
        self.state_store.add_device(device3, "pressure")
        
        # Act: Set different values for each device
        time1 = datetime.now(timezone.utc)
        time2 = time1 + timedelta(minutes=1)
        time3 = time1 + timedelta(minutes=2)
        
        state1 = self.state_store.get(device1)
        state2 = self.state_store.get(device2)
        state3 = self.state_store.get(device3)
        
        state1.last_seen_ts = time1
        state1.last_value = 25.5
        
        state2.last_seen_ts = time2
        state2.last_value = 65.8
        
        state3.last_seen_ts = time3
        state3.last_value = 1013.2
        
        # Assert: Each device maintains its own independent state
        retrieved1 = self.state_store.get(device1)
        retrieved2 = self.state_store.get(device2)
        retrieved3 = self.state_store.get(device3)
        
        assert retrieved1.last_seen_ts == time1
        assert retrieved1.last_value == 25.5
        assert retrieved1.sensor_type == "temperature"
        
        assert retrieved2.last_seen_ts == time2
        assert retrieved2.last_value == 65.8
        assert retrieved2.sensor_type == "humidity"
        
        assert retrieved3.last_seen_ts == time3
        assert retrieved3.last_value == 1013.2
        assert retrieved3.sensor_type == "pressure"
    
    def test_all_states_returns_correct_iterator(self):
        """CRITICAL: all_states() must return all devices and their current states."""
        # Arrange: Add several devices with different states
        devices_data = [
            ("device_a", "temperature", 22.1),
            ("device_b", "humidity", 58.3),
            ("device_c", "pressure", 1015.7)
        ]
        
        for device_id, sensor_type, value in devices_data:
            self.state_store.add_device(device_id, sensor_type)
            state = self.state_store.get(device_id)
            state.last_value = value
        
        # Act: Get all states
        all_states = dict(self.state_store.all_states())
        
        # Assert: Should contain exactly the devices we added
        assert len(all_states) == 3
        assert "device_a" in all_states
        assert "device_b" in all_states
        assert "device_c" in all_states
        
        # Assert: States should contain correct data
        assert all_states["device_a"].sensor_type == "temperature"
        assert all_states["device_a"].last_value == 22.1
        
        assert all_states["device_b"].sensor_type == "humidity"
        assert all_states["device_b"].last_value == 58.3
        
        assert all_states["device_c"].sensor_type == "pressure"
        assert all_states["device_c"].last_value == 1015.7
    
    def test_device_id_type_conversion_consistency(self):
        """CRITICAL: Device IDs must be consistently converted to strings."""
        # Act: Add devices with different ID types
        self.state_store.add_device(123, "temperature")      # Integer
        self.state_store.add_device("456", "humidity")       # String  
        self.state_store.add_device(789.0, "pressure")      # Float
        
        # Assert: All should be accessible as strings
        assert self.state_store.is_known_device("123")
        assert self.state_store.is_known_device("456") 
        assert self.state_store.is_known_device("789.0")
        
        # Assert: States should be retrievable with string IDs
        assert self.state_store.get("123") is not None
        assert self.state_store.get("456") is not None
        assert self.state_store.get("789.0") is not None
        
        # Assert: Original types should also work (converted internally)
        assert self.state_store.is_known_device(123)
        assert self.state_store.is_known_device(456)
        assert self.state_store.is_known_device(789.0)

    def test_duplicate_device_addition_is_safe(self):
        """CRITICAL: Adding same device multiple times must be safe."""
        # Arrange: Add device and modify its state
        device_id = "duplicate_test_device"
        self.state_store.add_device(device_id, "temperature")
        
        original_state = self.state_store.get(device_id)
        test_time = datetime.now(timezone.utc)
        original_state.last_seen_ts = test_time
        original_state.last_value = 99.9
        
        # Act: Add same device again (should not overwrite existing state)
        self.state_store.add_device(device_id, "humidity")  # Different sensor type
        
        # Assert: Original state should be preserved
        current_state = self.state_store.get(device_id)
        assert current_state.last_seen_ts == test_time
        assert current_state.last_value == 99.9
        assert current_state.sensor_type == "temperature"  # Should keep original


class TestStateStoreEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def setup_method(self):
        self.state_store = StateStore()
    
    def test_empty_state_store_operations(self):
        """Edge case: Operations on empty state store should be safe."""
        # Assert: Empty state store behaves correctly
        assert not self.state_store.is_known_device("any_device")
        assert self.state_store.get("any_device") is None
        
        # all_states should return empty iterator
        all_states = list(self.state_store.all_states())
        assert len(all_states) == 0
    
    def test_none_and_empty_device_ids(self):
        """Edge case: None/empty device IDs should be handled gracefully."""
        # Act/Assert: These should not crash
        try:
            result1 = self.state_store.is_known_device("")
            result2 = self.state_store.get("")
            # Empty string is valid, should return False/None
            assert result1 is False
            assert result2 is None
        except Exception as e:
            pytest.fail(f"Empty string device ID caused crash: {e}")
    
    def test_very_large_number_of_devices(self):
        """Performance test: Should handle many devices efficiently."""
        # Arrange: Add many devices
        num_devices = 1000
        for i in range(num_devices):
            device_id = f"device_{i:04d}"
            self.state_store.add_device(device_id, f"sensor_type_{i % 10}")
        
        # Act/Assert: Should be able to access all devices
        for i in range(num_devices):
            device_id = f"device_{i:04d}"
            assert self.state_store.is_known_device(device_id)
            state = self.state_store.get(device_id)
            assert state is not None
            assert state.device_id == device_id
        
        # Should return correct count
        all_states = list(self.state_store.all_states())
        assert len(all_states) == num_devices


class TestStateStoreBusinessRules:
    """Tests that verify business logic around state management."""
    
    def setup_method(self):
        self.state_store = StateStore()
    
    def test_alert_lifecycle_management(self):
        """Business rule: Alert lifecycle should be managed correctly in device state."""
        # Arrange: Add device
        device_id = "alert_lifecycle_device"
        self.state_store.add_device(device_id, "temperature")
        device_state = self.state_store.get(device_id)
        
        # Act: Simulate alert lifecycle
        now = datetime.now(timezone.utc)
        
        # 1. Open alert
        alert1 = Alert(
            issue_type="out_of_range",
            device_id=device_id,
            sensor_type="temperature",
            site_id="site1",
            severity="warning", 
            start_ts=now,
            end_ts=None,
            details={"value": 150.0, "max": 85.0}
        )
        device_state.open_alerts["out_of_range"] = alert1
        
        # 2. Open second alert
        alert2 = Alert(
            issue_type="stuck_sensor", 
            device_id=device_id,
            sensor_type="temperature",
            site_id="site1",
            severity="error",
            start_ts=now + timedelta(minutes=1),
            end_ts=None,
            details={"repeated_value": 150.0}
        )
        device_state.open_alerts["stuck_sensor"] = alert2
        
        # Assert: Both alerts should be tracked
        assert len(device_state.open_alerts) == 2
        assert "out_of_range" in device_state.open_alerts
        assert "stuck_sensor" in device_state.open_alerts
        
        # 3. Close first alert
        closed_alert = device_state.open_alerts.pop("out_of_range")
        closed_alert.end_ts = now + timedelta(minutes=2)
        
        # Assert: Only one alert should remain open
        assert len(device_state.open_alerts) == 1
        assert "out_of_range" not in device_state.open_alerts
        assert "stuck_sensor" in device_state.open_alerts
        
        # Assert: Closed alert should have end_ts
        assert closed_alert.end_ts is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])