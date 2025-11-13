import pytest
from datetime import datetime, timezone
import sys
import os

# Add the flink_app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flink_app'))

from core.types import Event, Alert, DeviceState


class TestEvent:
    """Test Event class"""
    
    def test_event_creation(self):
        """Test creating Event with valid data"""
        # Arrange
        ts = datetime.now(timezone.utc)
        
        # Act
        event = Event(
            ts=ts,
            device_id="sensor_1",
            sensor_type="temperature", 
            site_id=None,
            msg_type="telemetry",
            value=25.5,
            seq=1,
            quality="ok"
        )
        
        # Assert
        assert event.ts == ts
        assert event.device_id == "sensor_1"
        assert event.sensor_type == "temperature"
        assert event.value == 25.5
        assert event.msg_type == "telemetry"
        assert event.seq == 1
        assert event.quality == "ok"
    
    def test_event_with_minimal_data(self):
        """Test creating Event with minimal required data"""
        # Arrange & Act
        ts = datetime.now(timezone.utc)
        event = Event(
            ts=ts,
            device_id="sensor_1",
            sensor_type="temperature",
            site_id=None,
            msg_type="reading",
            value=None,
            seq=None,
            quality=None
        )
        
        # Assert
        assert event.device_id == "sensor_1"
        assert event.sensor_type == "temperature"
        assert event.value is None


class TestAlert:
    """Test Alert class"""
    
    def test_alert_creation(self):
        """Test creating Alert with valid data"""
        # Arrange
        start_ts = datetime.now(timezone.utc)
        
        # Act
        alert = Alert(
            device_id="sensor_1",
            issue_type="out_of_range",
            severity="error", 
            start_ts=start_ts,
            end_ts=None,
            sensor_type="temperature"
        )
        
        # Assert
        assert alert.issue_type == "out_of_range"
        assert alert.device_id == "sensor_1"  
        assert alert.severity == "error"
        assert alert.start_ts == start_ts
        assert alert.end_ts is None
        assert alert.sensor_type == "temperature"
    
    def test_alert_with_end_time(self):
        """Test alert with both start and end times"""
        # Arrange
        start_ts = datetime.now(timezone.utc)
        end_ts = datetime.now(timezone.utc)
        
        # Act
        alert = Alert(
            device_id="sensor_2",
            issue_type="missing_keepalive",
            severity="critical",
            start_ts=start_ts,
            end_ts=end_ts
        )
        
        # Assert
        assert alert.start_ts == start_ts
        assert alert.end_ts == end_ts


class TestDeviceState:
    """Test DeviceState class"""
    
    def test_device_state_creation(self):
        """Test creating DeviceState"""
        # Arrange & Act
        device_state = DeviceState(
            device_id="sensor_1",
            sensor_type="temperature"
        )
        
        # Assert
        assert device_state.device_id == "sensor_1"
        assert device_state.sensor_type == "temperature"
        assert device_state.last_seen_ts is None
        assert device_state.last_value is None
        assert len(device_state.open_alerts) == 0
    
    def test_device_state_update(self):
        """Test updating device state"""
        # Arrange
        device_state = DeviceState(
            device_id="sensor_1",
            sensor_type="temperature"
        )
        ts = datetime.now(timezone.utc)
        
        # Act
        device_state.last_seen_ts = ts
        device_state.last_value = 25.0
        
        # Assert
        assert device_state.last_seen_ts == ts
        assert device_state.last_value == 25.0
    
    def test_device_state_alerts_management(self):
        """Test managing alerts in device state"""
        # Arrange
        device_state = DeviceState(
            device_id="sensor_1", 
            sensor_type="temperature"
        )
        alert = Alert(
            device_id="sensor_1",
            issue_type="out_of_range",
            severity="error",
            start_ts=datetime.now(timezone.utc),
            end_ts=None
        )
        
        # Act - Add alert
        device_state.open_alerts["out_of_range"] = alert
        
        # Assert
        assert "out_of_range" in device_state.open_alerts
        assert device_state.open_alerts["out_of_range"] == alert
        
        # Act - Remove alert
        removed_alert = device_state.open_alerts.pop("out_of_range")
        
        # Assert
        assert removed_alert == alert
        assert len(device_state.open_alerts) == 0