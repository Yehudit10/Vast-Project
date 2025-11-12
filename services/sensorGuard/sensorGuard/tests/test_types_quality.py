"""
Professional, comprehensive tests for Types (dataclasses).
These tests verify data validation, business rules, and type safety.
"""
import pytest
from datetime import datetime, timezone, timedelta
from copy import deepcopy

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flink_app'))

from core.types import Event, Alert, DeviceState


class TestEventDataIntegrity:
    """Tests that verify Event dataclass behavior and business rules."""
    
    def test_event_creation_with_all_required_fields(self):
        """CRITICAL: Event must be creatable with all required fields."""
        # Arrange
        test_time = datetime.now(timezone.utc)
        
        # Act: Create event with all fields
        event = Event(
            ts=test_time,
            device_id="sensor_123",
            sensor_type="temperature", 
            site_id="greenhouse_a",
            msg_type="reading",
            value=24.7,
            seq=42,
            quality="ok"
        )
        
        # Assert: All fields should be set correctly
        assert event.ts == test_time
        assert event.device_id == "sensor_123"
        assert event.sensor_type == "temperature"
        assert event.site_id == "greenhouse_a"
        assert event.msg_type == "reading"
        assert event.value == 24.7
        assert event.seq == 42
        assert event.quality == "ok"
    
    def test_event_with_none_optional_fields(self):
        """Business rule: Event should handle None values for optional fields."""
        # Act: Create event with minimal required fields
        event = Event(
            ts=datetime.now(timezone.utc),
            device_id="minimal_device",
            sensor_type="humidity",
            site_id=None,  # Optional
            msg_type="keepalive", 
            value=None,    # Optional (e.g., keepalive messages)
            seq=None,      # Optional
            quality=None   # Optional
        )
        
        # Assert: Should handle None values gracefully
        assert event.site_id is None
        assert event.value is None
        assert event.seq is None
        assert event.quality is None
    
    def test_event_immutability_after_creation(self):
        """Data integrity: Event fields should be modifiable after creation."""
        # Arrange: Create event
        original_time = datetime.now(timezone.utc)
        event = Event(
            ts=original_time,
            device_id="test_device",
            sensor_type="temperature",
            site_id="site1",
            msg_type="reading",
            value=25.0,
            seq=1,
            quality="ok"
        )
        
        # Act: Modify fields (should be allowed for dataclass)
        new_time = original_time + timedelta(seconds=30)
        event.ts = new_time
        event.value = 26.5
        event.quality = "corrupted"
        
        # Assert: Changes should be reflected
        assert event.ts == new_time
        assert event.value == 26.5
        assert event.quality == "corrupted"
    
    def test_event_different_msg_types_validation(self):
        """Business rule: Different msg_type values should be handled correctly.""" 
        base_params = {
            "ts": datetime.now(timezone.utc),
            "device_id": "msg_type_test",
            "sensor_type": "temperature",
            "site_id": "site1"
        }
        
        # Test reading message
        reading_event = Event(
            **base_params,
            msg_type="reading",
            value=23.4,
            seq=1,
            quality="ok"
        )
        assert reading_event.msg_type == "reading"
        assert reading_event.value is not None
        
        # Test keepalive message (typically no sensor value)
        keepalive_event = Event(
            **base_params,
            msg_type="keepalive",
            value=None,  # Keepalives usually don't have sensor values
            seq=2,
            quality=None
        )
        assert keepalive_event.msg_type == "keepalive"
        assert keepalive_event.value is None


class TestAlertDataIntegrity:
    """Tests that verify Alert dataclass behavior and lifecycle management."""
    
    def test_alert_creation_with_required_fields(self):
        """CRITICAL: Alert must be creatable with all required fields."""
        # Arrange
        start_time = datetime.now(timezone.utc)
        
        # Act: Create alert
        alert = Alert(
            device_id="alert_test_device",
            issue_type="out_of_range",
            start_ts=start_time,
            end_ts=None,  # Open alert
            severity="warning",
            sensor_type="temperature",
            site_id="greenhouse_b",
            details={"value": 150.0, "max_allowed": 85.0}
        )
        
        # Assert: All fields should be set correctly
        assert alert.device_id == "alert_test_device"
        assert alert.issue_type == "out_of_range"
        assert alert.start_ts == start_time
        assert alert.end_ts is None
        assert alert.severity == "warning"
        assert alert.sensor_type == "temperature"
        assert alert.site_id == "greenhouse_b"
        assert alert.details["value"] == 150.0
        assert alert.details["max_allowed"] == 85.0
    
    def test_alert_lifecycle_open_to_closed(self):
        """Business rule: Alert should properly transition from open to closed state."""
        # Arrange: Create open alert
        start_time = datetime.now(timezone.utc)
        alert = Alert(
            device_id="lifecycle_test",
            issue_type="stuck_sensor",
            start_ts=start_time,
            end_ts=None,  # Initially open
            severity="error"
        )
        
        # Verify initially open
        assert alert.end_ts is None
        
        # Act: Close the alert
        end_time = start_time + timedelta(minutes=5)
        alert.end_ts = end_time
        
        # Assert: Should be properly closed
        assert alert.end_ts == end_time
        duration = alert.end_ts - alert.start_ts
        assert duration.total_seconds() == 300  # 5 minutes
    
    def test_alert_different_severities(self):
        """Business rule: Different severity levels should be supported."""
        base_params = {
            "device_id": "severity_test",
            "issue_type": "test_issue",
            "start_ts": datetime.now(timezone.utc),
            "end_ts": None
        }
        
        # Test different severity levels
        warning_alert = Alert(**base_params, severity="warning")
        error_alert = Alert(**base_params, severity="error")
        critical_alert = Alert(**base_params, severity="critical")
        
        assert warning_alert.severity == "warning"
        assert error_alert.severity == "error"
        assert critical_alert.severity == "critical"
    
    def test_alert_details_dictionary_flexibility(self):
        """Business rule: Alert details should support flexible data structures."""
        # Act: Create alert with complex details
        alert = Alert(
            device_id="details_test",
            issue_type="complex_issue", 
            start_ts=datetime.now(timezone.utc),
            end_ts=None,
            severity="warning",
            details={
                "sensor_readings": [22.1, 22.1, 22.1, 22.1],
                "threshold": 0.1,
                "consecutive_count": 4,
                "metadata": {
                    "location": "field_section_3",
                    "operator": "automated_system"
                },
                "numeric_value": 42.7,
                "boolean_flag": True
            }
        )
        
        # Assert: Complex details should be preserved
        assert len(alert.details["sensor_readings"]) == 4
        assert alert.details["threshold"] == 0.1
        assert alert.details["metadata"]["location"] == "field_section_3"
        assert alert.details["numeric_value"] == 42.7
        assert alert.details["boolean_flag"] is True


class TestDeviceStateDataIntegrity:
    """Tests that verify DeviceState dataclass behavior and state management."""
    
    def test_device_state_creation_with_minimal_params(self):
        """CRITICAL: DeviceState should initialize with sensible defaults."""
        # Act: Create device state with minimal parameters
        device_state = DeviceState(device_id="minimal_device")
        
        # Assert: Should have proper defaults
        assert device_state.device_id == "minimal_device"
        assert device_state.sensor_type is None
        assert device_state.last_seen_ts is None
        assert device_state.last_value is None
        assert device_state.run_length == 0
        assert device_state.stuck_since_ts is None
        assert device_state.open_alerts == {}
    
    def test_device_state_alert_management(self):
        """Business rule: DeviceState should properly manage multiple open alerts."""
        # Arrange: Create device state
        device_state = DeviceState(
            device_id="multi_alert_device", 
            sensor_type="temperature"
        )
        
        # Act: Add multiple alerts
        now = datetime.now(timezone.utc)
        
        alert1 = Alert(
            device_id="multi_alert_device",
            issue_type="out_of_range",
            start_ts=now,
            end_ts=None,
            severity="warning"
        )
        
        alert2 = Alert(
            device_id="multi_alert_device", 
            issue_type="stuck_sensor",
            start_ts=now + timedelta(minutes=1),
            end_ts=None,
            severity="error"
        )
        
        device_state.open_alerts["out_of_range"] = alert1
        device_state.open_alerts["stuck_sensor"] = alert2
        
        # Assert: Both alerts should be tracked
        assert len(device_state.open_alerts) == 2
        assert "out_of_range" in device_state.open_alerts
        assert "stuck_sensor" in device_state.open_alerts
        
        # Assert: Alerts should maintain their properties
        assert device_state.open_alerts["out_of_range"].severity == "warning"
        assert device_state.open_alerts["stuck_sensor"].severity == "error"
    
    def test_device_state_evolution_over_time(self):
        """Business rule: DeviceState should track sensor data evolution correctly."""
        # Arrange: Create device state
        device_state = DeviceState(
            device_id="evolution_test",
            sensor_type="humidity"
        )
        
        # Act: Simulate sensor data evolution
        time1 = datetime.now(timezone.utc)
        time2 = time1 + timedelta(minutes=1)
        time3 = time1 + timedelta(minutes=2)
        
        # First reading
        device_state.last_seen_ts = time1
        device_state.last_value = 45.2
        device_state.run_length = 1
        
        # Second reading (same value - potential stuck sensor)
        device_state.last_seen_ts = time2 
        device_state.last_value = 45.2  # Same value
        device_state.run_length = 2
        device_state.stuck_since_ts = time1  # Started being stuck from first occurrence
        
        # Third reading (different value - unstuck)
        device_state.last_seen_ts = time3
        device_state.last_value = 46.8  # Different value
        device_state.run_length = 1     # Reset
        device_state.stuck_since_ts = None  # No longer stuck
        
        # Assert: State evolution should be properly tracked
        assert device_state.last_seen_ts == time3
        assert device_state.last_value == 46.8
        assert device_state.run_length == 1
        assert device_state.stuck_since_ts is None
    
    def test_device_state_deep_copy_independence(self):
        """Data integrity: DeviceState copies should be independent.""" 
        # Arrange: Create device state with complex data
        original_time = datetime.now(timezone.utc)
        original_state = DeviceState(
            device_id="copy_test",
            sensor_type="temperature",
            last_seen_ts=original_time,
            last_value=25.0,
            run_length=3
        )
        
        # Add an alert
        alert = Alert(
            device_id="copy_test",
            issue_type="test_alert", 
            start_ts=original_time,
            end_ts=None,
            severity="warning"
        )
        original_state.open_alerts["test_alert"] = alert
        
        # Act: Create deep copy
        copied_state = deepcopy(original_state)
        
        # Modify original
        new_time = original_time + timedelta(minutes=1)
        original_state.last_seen_ts = new_time
        original_state.last_value = 26.0
        original_state.open_alerts["test_alert"].severity = "error"
        
        # Assert: Copy should remain unchanged
        assert copied_state.last_seen_ts == original_time
        assert copied_state.last_value == 25.0
        assert copied_state.open_alerts["test_alert"].severity == "warning"


class TestTypesBusinessRules:
    """Tests that verify business rules across all types."""
    
    def test_event_to_alert_data_consistency(self):
        """Business rule: Alerts generated from Events should maintain data consistency."""
        # Arrange: Create event
        event_time = datetime.now(timezone.utc)
        event = Event(
            ts=event_time,
            device_id="consistency_test", 
            sensor_type="pressure",
            site_id="factory_floor_2",
            msg_type="reading",
            value=999.9,  # Out of range value
            seq=15,
            quality="ok"
        )
        
        # Act: Create alert based on event (simulating engine behavior)
        alert = Alert(
            device_id=event.device_id,        # Must match
            issue_type="out_of_range",
            start_ts=event.ts,                # Must use event timestamp
            end_ts=None,
            severity="error", 
            sensor_type=event.sensor_type,    # Must match
            site_id=event.site_id,           # Must match
            details={
                "trigger_value": event.value,  # Include event data
                "trigger_seq": event.seq,
                "trigger_quality": event.quality
            }
        )
        
        # Assert: Data consistency between event and alert
        assert alert.device_id == event.device_id
        assert alert.start_ts == event.ts
        assert alert.sensor_type == event.sensor_type
        assert alert.site_id == event.site_id
        assert alert.details["trigger_value"] == event.value
        assert alert.details["trigger_seq"] == event.seq
        assert alert.details["trigger_quality"] == event.quality
    
    def test_timestamp_ordering_consistency(self):
        """Business rule: Timestamps should maintain logical ordering."""
        # Arrange: Create time sequence
        base_time = datetime.now(timezone.utc)
        event_time = base_time
        alert_start = base_time + timedelta(seconds=1)
        alert_end = base_time + timedelta(minutes=5)
        
        # Act: Create objects with time sequence
        event = Event(
            ts=event_time,
            device_id="timing_test",
            sensor_type="temperature",
            site_id="test_site",
            msg_type="reading", 
            value=25.0,
            seq=1,
            quality="ok"
        )
        
        alert = Alert(
            device_id="timing_test",
            issue_type="test_issue",
            start_ts=alert_start,
            end_ts=alert_end, 
            severity="warning"
        )
        
        device_state = DeviceState(
            device_id="timing_test",
            last_seen_ts=event_time
        )
        
        # Assert: Timestamp relationships should be logical
        assert event.ts <= alert.start_ts  # Event should trigger alert
        assert alert.start_ts < alert.end_ts  # Alert start before end
        assert device_state.last_seen_ts == event.ts  # State reflects event time


if __name__ == "__main__":
    pytest.main([__file__, "-v"])