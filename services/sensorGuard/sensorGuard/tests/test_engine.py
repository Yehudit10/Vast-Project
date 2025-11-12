import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
import sys
import os

# Add the flink_app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flink_app'))

from core.engine import Engine
from core.types import Event, Alert
from core.state import StateStore


@pytest.fixture(autouse=True)
def mock_engine_dependencies():
    """Mock external dependencies for Engine class"""
    with patch('core.engine.get_access_token', return_value='test_token'), \
         patch('core.engine.update_device_last_seen'):
        yield


class TestEngine:
    """Test Engine class public methods"""
    
    def setup_method(self):
        """Arrange - Set up test fixtures"""
        self.mock_writer = Mock()
        self.mock_cfg = {
            'features': {'out_of_range': True, 'stuck_sensor': True},
            'ranges': {'temperature': {'min': 0, 'max': 50}},
            'stuck': {'min_duration_seconds': 1800}
        }
        self.state_store = StateStore()
        self.engine = Engine(self.mock_cfg, self.mock_writer, self.state_store)
    
    def test_engine_initialization(self):
        """Test engine initializes correctly"""
        # Assert
        assert self.engine.cfg == self.mock_cfg
        assert len(self.engine.writers) == 1
        assert self.engine.state is self.state_store
    
    def test_process_event_unknown_device(self):
        """Test processing event for unknown device"""
        # Arrange
        event = Event(
            ts=datetime.now(timezone.utc),
            device_id="unknown_device",
            sensor_type="temperature",
            site_id=None,
            msg_type="reading",
            value=25.0,
            seq=None,
            quality="ok"
        )
        
        # Act
        self.engine.process_event(event)
        
        # Assert - no alerts should be emitted for unknown devices
        self.mock_writer.write.assert_not_called()
    
    def test_process_event_known_device_normal_value(self):
        """Test processing normal value for known device"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        event = Event(
            ts=datetime.now(timezone.utc),
            device_id="device_1", 
            sensor_type="temperature",
            site_id=None,
            msg_type="reading",
            value=25.0,
            seq=None,
            quality="ok"
        )
        
        # Act
        self.engine.process_event(event)
        
        # Assert - device state should be updated
        device_state = self.state_store.get("device_1")
        assert device_state.last_seen_ts == event.ts
        assert device_state.last_value == 25.0
    
    def test_emit_alert_calls_all_writers(self):
        """Test _emit calls write on all writers"""
        # Arrange
        writer1 = Mock()
        writer2 = Mock()
        engine = Engine(self.mock_cfg, [writer1, writer2], self.state_store)
        alert = Alert(
            device_id="device_1",
            issue_type="test_alert",
            severity="error",
            start_ts=datetime.now(timezone.utc),
            end_ts=None
        )
        
        # Act
        engine._emit(alert)
        
        # Assert
        writer1.write.assert_called_once_with(alert)
        writer2.write.assert_called_once_with(alert)
    
    def test_open_once_new_alert(self):
        """Test opening new alert when none exists"""
        # Arrange  
        self.state_store.add_device("device_1", "temperature")
        device_state = self.state_store.get("device_1")
        alert = Alert(
            device_id="device_1",
            issue_type="out_of_range", 
            severity="error",
            start_ts=datetime.now(timezone.utc),
            end_ts=None
        )
        
        # Act
        self.engine._open_once(device_state, alert)
        
        # Assert
        assert "out_of_range" in device_state.open_alerts
        self.mock_writer.write.assert_called_once_with(alert)
    
    def test_open_once_existing_alert(self):
        """Test not opening duplicate alert"""
        # Arrange
        self.state_store.add_device("device_1", "temperature") 
        device_state = self.state_store.get("device_1")
        
        # Pre-existing alert
        existing_alert = Alert(
            device_id="device_1",
            issue_type="out_of_range",
            severity="error", 
            start_ts=datetime.now(timezone.utc),
            end_ts=None
        )
        device_state.open_alerts["out_of_range"] = existing_alert
        
        new_alert = Alert(
            device_id="device_1",
            issue_type="out_of_range",
            severity="error",
            start_ts=datetime.now(timezone.utc),
            end_ts=None
        )
        
        # Act
        self.engine._open_once(device_state, new_alert)
        
        # Assert - should not emit new alert
        self.mock_writer.write.assert_not_called()
        assert device_state.open_alerts["out_of_range"] is existing_alert
    
    def test_close_if_open_existing_alert(self):
        """Test closing existing alert"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        device_state = self.state_store.get("device_1") 
        
        alert = Alert(
            device_id="device_1",
            issue_type="out_of_range",
            severity="error",
            start_ts=datetime.now(timezone.utc),
            end_ts=None
        )
        device_state.open_alerts["out_of_range"] = alert
        close_ts = datetime.now(timezone.utc)
        
        # Act
        self.engine._close_if_open(device_state, "out_of_range", close_ts)
        
        # Assert
        assert "out_of_range" not in device_state.open_alerts
        assert alert.end_ts == close_ts
        self.mock_writer.write.assert_called_once_with(alert)
    
    def test_close_if_open_nonexistent_alert(self):
        """Test closing non-existent alert does nothing"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        device_state = self.state_store.get("device_1")
        close_ts = datetime.now(timezone.utc)
        
        # Act  
        self.engine._close_if_open(device_state, "out_of_range", close_ts)
        
        # Assert - nothing should happen
        self.mock_writer.write.assert_not_called()
        assert len(device_state.open_alerts) == 0