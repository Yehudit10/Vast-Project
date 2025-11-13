"""
Professional, comprehensive tests for the Engine class.
These tests verify REAL business logic, not just code coverage.
"""
import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flink_app'))

from core.engine import Engine
from core.types import Event, Alert, DeviceState
from core.state import StateStore


@pytest.fixture(autouse=True)
def mock_engine_dependencies():
    """Mock external dependencies for Engine class"""
    with patch('core.engine.get_access_token', return_value='test_token'), \
         patch('core.engine.update_device_last_seen'), \
         patch('core.engine.get_sensors_last_seen', return_value=[]):
        yield


class TestEngineBusinessLogic:
    """Tests that verify the actual sensor monitoring business rules."""
    
    def setup_method(self):
        """Set up test environment with realistic configuration."""
        self.mock_writer = Mock()
        self.cfg = {
            "features": {
                "corrupted": True,
                "out_of_range": True, 
                "stuck_sensor": True,
                "silence": True
            },
            "prolonged_silence_seconds": 300,  # 5 minutes
            "ranges": {
                "temperature": {"min": -40, "max": 85},
                "humidity": {"min": 0, "max": 100}
            },
            "stuck": {
                "temperature": {"tolerance": 0.1, "count": 5}
            }
        }
        self.state_store = StateStore()
        self.engine = Engine(self.cfg, self.mock_writer, self.state_store)
    
    def create_real_sensor_message(self, device_id, sensor_type, value, msg_type="telemetry", **extra):
        """Create a message in the EXACT format that comes from real sensors."""
        return {
            "sid": f"sensor-{device_id}",
            "id": int(device_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "msg_type": msg_type,
            "value": value,
            "sensor": sensor_type,
            "plant_id": 123,
            "temperature": value if sensor_type == "temperature" else 25.0,
            "humidity": value if sensor_type == "humidity" else 65.0,
            "ph": 7.0,
            "n": 50.0,
            "p": 30.0,
            "k": 40.0,
            **extra
        }
    
    def to_event(self, sensor_message):
        """Convert sensor message to Event using EXACT logic from main.py."""
        if not isinstance(sensor_message, dict):
            return None
        ts = datetime.now(timezone.utc)
        device_id = sensor_message.get("id")
        sensor_type = sensor_message.get("sensor_type") or sensor_message.get("sensor", "unknown_sensor")
        if not device_id:
            device_id = "unknown_device"
        else:
            device_id = str(device_id)
        
        return Event(
            ts=ts,
            device_id=device_id,
            sensor_type=sensor_type,
            site_id=sensor_message.get("site_id"),
            msg_type=sensor_message.get("msg_type", "reading"),
            value=sensor_message.get("value"),
            seq=sensor_message.get("seq"),
            quality=sensor_message.get("quality"),
        )
    
    def test_new_unknown_device_is_ignored_completely(self):
        """CRITICAL: Unknown devices should be completely ignored - no alerts, no state changes."""
        # Arrange: Create REAL sensor message from unknown device (not in state_store)
        unknown_message = self.create_real_sensor_message(
            device_id="999",  # Device not added to state store
            sensor_type="temperature",
            value=25.0
        )
        
        # Act: Convert and process like real system does
        event = self.to_event(unknown_message)
        assert event is not None, "Valid message should convert to event"
        self.engine.process_event(event)
        
        # Assert: No alerts should be generated for unknown devices
        assert self.mock_writer.write.call_count == 0
        
        # Assert: Device should not be considered known
        assert not self.state_store.is_known_device("999")
        
        # Assert: No state should exist for this device  
        result = self.state_store.get("999")
        assert result is None, "Unknown device should return None from state store"

    def test_sensor_comeback_closes_keepalive_alerts_immediately(self):
        """CRITICAL: When sensor sends data after being silent, missing_keepalive alert must close.
        NOTE: prolonged_silence alerts are NOT closed by process_event - only by sweep_silence."""
        # Arrange: Add device and simulate missing keepalive alert
        device_id = "5"
        self.state_store.add_device(device_id, "temperature")
        device_state = self.state_store.get(device_id)
        
        # Manually create open missing_keepalive alert (simulating sweep_silence)
        now = datetime.now(timezone.utc)
        missing_alert = Alert(
            device_id=device_id,
            issue_type="missing_keepalive",
            start_ts=now - timedelta(minutes=10),
            end_ts=None,
            severity="error",
            sensor_type="temperature",
            site_id=None,
            details={"reason": "no data received"}
        )
        
        device_state.open_alerts["missing_keepalive"] = missing_alert
        
        # Act: Sensor sends REAL comeback message
        comeback_message = self.create_real_sensor_message(
            device_id="5",
            sensor_type="temperature", 
            value=23.5
        )
        
        comeback_event = self.to_event(comeback_message)
        assert comeback_event is not None
        self.engine.process_event(comeback_event)
        
        # Assert: missing_keepalive alert should be closed (emitted with end_ts)
        assert self.mock_writer.write.call_count >= 1, "Expected at least 1 alert emission"
        
        # Verify the closed alert has end_ts set
        calls = self.mock_writer.write.call_args_list
        closed_alerts = [call[0][0] for call in calls]
        
        keepalive_closed = any(alert.issue_type == "missing_keepalive" and alert.end_ts is not None 
                             for alert in closed_alerts)
        
        assert keepalive_closed, "missing_keepalive alert should be closed with end_ts"
        
        # Assert: missing_keepalive alert should no longer be open
        assert "missing_keepalive" not in device_state.open_alerts

    def test_out_of_range_alert_opens_and_closes_correctly(self):
        """CRITICAL: Out-of-range alerts must open when value is invalid, close when valid."""
        # Arrange: Add device
        device_id = "5"
        self.state_store.add_device(device_id, "temperature")
        
        # Act 1: Send out-of-range value using REAL message format
        bad_message = self.create_real_sensor_message(
            device_id="5",
            sensor_type="temperature",
            value=150.0  # Way above max of 85
        )
        
        bad_event = self.to_event(bad_message)
        assert bad_event is not None, "Valid message should convert to event"
        
        self.engine.process_event(bad_event)
        
        # Assert: Out-of-range alert should be opened
        device_state = self.state_store.get(device_id)
        assert "out_of_range" in device_state.open_alerts
        
        # Find the out-of-range alert that was emitted
        calls = self.mock_writer.write.call_args_list
        out_of_range_alerts = [call[0][0] for call in calls if call[0][0].issue_type == "out_of_range"]
        assert len(out_of_range_alerts) == 1
        assert out_of_range_alerts[0].end_ts is None  # Should be open
        
        # Reset mock for next assertion
        self.mock_writer.reset_mock()
        
        # Act 2: Send valid value using REAL message format
        good_message = self.create_real_sensor_message(
            device_id="5",
            sensor_type="temperature",
            value=22.0  # Within valid range
        )
        
        good_event = self.to_event(good_message)
        assert good_event is not None, "Valid message should convert to event"
        
        self.engine.process_event(good_event)
        
        # Assert: Out-of-range alert should be closed
        assert "out_of_range" not in device_state.open_alerts
        
        # Verify alert was closed (emitted with end_ts)
        closing_calls = self.mock_writer.write.call_args_list
        if closing_calls:  # Alert closure generates emission
            closed_alert = closing_calls[0][0][0]
            assert closed_alert.issue_type == "out_of_range" 
            assert closed_alert.end_ts is not None

    def test_complete_alert_lifecycle_with_multiple_bad_then_good_messages(self):
        """COMPREHENSIVE: Test complete alert lifecycle - multiple bad messages, then recovery."""
        # Arrange: Add device
        device_id = "10"
        self.state_store.add_device(device_id, "temperature") 
        device_state = self.state_store.get(device_id)
        
        # Act 1: Send first bad message (should open alert)
        bad_message_1 = self.create_real_sensor_message(
            device_id="10",
            sensor_type="temperature",
            value=200.0  # Way out of range
        )
        
        self.engine.process_event(self.to_event(bad_message_1))
        
        # Assert: Alert should be open
        assert "out_of_range" in device_state.open_alerts
        assert self.mock_writer.write.call_count == 1  # One alert opened
        
        # Act 2: Send second bad message (should NOT open duplicate alert)
        self.mock_writer.reset_mock()
        bad_message_2 = self.create_real_sensor_message(
            device_id="10", 
            sensor_type="temperature",
            value=250.0  # Still out of range
        )
        
        self.engine.process_event(self.to_event(bad_message_2))
        
        # Assert: Still same alert, no new alert created
        assert "out_of_range" in device_state.open_alerts
        assert self.mock_writer.write.call_count == 0  # No new alerts
        
        # Act 3: Send good message (should close alert)
        self.mock_writer.reset_mock()
        good_message = self.create_real_sensor_message(
            device_id="10",
            sensor_type="temperature", 
            value=25.0  # Back to normal
        )
        
        self.engine.process_event(self.to_event(good_message))
        
        # Assert: Alert should be closed completely
        assert "out_of_range" not in device_state.open_alerts
        assert self.mock_writer.write.call_count == 1  # Alert closure emitted
        
        # Verify the closed alert has proper end_ts
        closed_alert = self.mock_writer.write.call_args[0][0]
        assert closed_alert.issue_type == "out_of_range"
        assert closed_alert.device_id == device_id
        assert closed_alert.end_ts is not None
        assert closed_alert.end_ts > closed_alert.start_ts  # End after start
        
        # Act 4: Send another good message (should NOT close anything)
        self.mock_writer.reset_mock()
        another_good = self.create_real_sensor_message(
            device_id="10",
            sensor_type="temperature",
            value=30.0
        )
        
        self.engine.process_event(self.to_event(another_good))
        
        # Assert: No alert activity (no open alerts to close)
        assert len(device_state.open_alerts) == 0
        assert self.mock_writer.write.call_count == 0

    def test_multiple_alert_types_independence(self):
        """CRITICAL: Different alert types should open/close independently."""
        # Arrange
        device_id = "11" 
        self.state_store.add_device(device_id, "temperature")
        device_state = self.state_store.get(device_id)
        
        # Act 1: Trigger out_of_range alert
        bad_temp_message = self.create_real_sensor_message(
            device_id="11",
            sensor_type="temperature",
            value=200.0
        )
        self.engine.process_event(self.to_event(bad_temp_message))
        
        # Act 2: Manually add a missing_keepalive alert (simulating silence)
        keepalive_alert = Alert(
            device_id=device_id,
            issue_type="missing_keepalive",
            start_ts=datetime.now(timezone.utc),
            end_ts=None,
            severity="error",
            sensor_type="temperature"
        )
        device_state.open_alerts["missing_keepalive"] = keepalive_alert
        
        # Assert: Both alerts should be open
        assert "out_of_range" in device_state.open_alerts
        assert "missing_keepalive" in device_state.open_alerts
        assert len(device_state.open_alerts) == 2
        
        # Act 3: Send good temperature (should close out_of_range but not missing_keepalive)
        self.mock_writer.reset_mock()
        good_temp_message = self.create_real_sensor_message(
            device_id="11",
            sensor_type="temperature", 
            value=25.0
        )
        self.engine.process_event(self.to_event(good_temp_message))
        
        # Assert: out_of_range closed, missing_keepalive should be closed by _close_all_keepalive_alerts
        assert "out_of_range" not in device_state.open_alerts
        assert "missing_keepalive" not in device_state.open_alerts  # This should be closed by comeback
        
        # Should have emitted 2 alerts: out_of_range closure + missing_keepalive closure
        assert self.mock_writer.write.call_count == 2

    def test_corrupted_message_overrides_out_of_range_alerts(self):
        """CRITICAL: Corrupted message should close out_of_range and stuck_sensor alerts."""
        # Arrange
        device_id = "12"
        self.state_store.add_device(device_id, "humidity")
        device_state = self.state_store.get(device_id)
        
        # Act 1: Create out_of_range alert first
        out_of_range_message = self.create_real_sensor_message(
            device_id="12",
            sensor_type="humidity", 
            value=150.0  # Above max of 100
        )
        self.engine.process_event(self.to_event(out_of_range_message))
        
        assert "out_of_range" in device_state.open_alerts
        first_alert_count = self.mock_writer.write.call_count
        
        # Act 2: Send corrupted message (None value)
        self.mock_writer.reset_mock()
        corrupted_message = self.create_real_sensor_message(
            device_id="12",
            sensor_type="humidity",
            value=None  # This triggers corrupted alert
        )
        self.engine.process_event(self.to_event(corrupted_message))
        
        # Assert: Corrupted should open, out_of_range should be closed
        assert "corrupted" in device_state.open_alerts
        assert "out_of_range" not in device_state.open_alerts
        
        # Should emit: 1 corrupted open + 1 out_of_range close
        assert self.mock_writer.write.call_count == 2

    def test_sensor_value_oscillation_alert_behavior(self):
        """COMPLEX: Test alert behavior when sensor oscillates between good/bad values."""
        # Arrange
        device_id = "13"
        self.state_store.add_device(device_id, "temperature")
        device_state = self.state_store.get(device_id)
        
        # Scenario: bad -> good -> bad -> good (should open/close/open/close)
        test_sequence = [
            (100.0, True),   # Bad (should open alert)
            (25.0, False),   # Good (should close alert)
            (200.0, True),   # Bad again (should open new alert)
            (30.0, False)    # Good again (should close alert)
        ]
        
        total_opens = 0
        total_closes = 0
        
        for i, (value, should_be_bad) in enumerate(test_sequence):
            self.mock_writer.reset_mock()
            
            message = self.create_real_sensor_message(
                device_id="13",
                sensor_type="temperature",
                value=value
            )
            self.engine.process_event(self.to_event(message))
            
            if should_be_bad:
                # Should have alert open
                assert "out_of_range" in device_state.open_alerts
                if self.mock_writer.write.call_count > 0:
                    total_opens += 1
            else:
                # Should NOT have alert open
                assert "out_of_range" not in device_state.open_alerts
                if self.mock_writer.write.call_count > 0:
                    total_closes += 1
        
        # Should have opened 2 times and closed 2 times
        assert total_opens == 2, f"Expected 2 opens, got {total_opens}"
        assert total_closes == 2, f"Expected 2 closes, got {total_closes}"

    def test_sweep_silence_detects_missing_devices_correctly(self):
        """CRITICAL: sweep_silence must detect devices that haven't been seen for too long.
        This tests the REAL business logic: sweep_silence fetches from API and compares timestamps."""
        # Arrange: Add device to state store
        device_id = "never_seen_device"
        self.state_store.add_device(device_id, "humidity")
        device_state = self.state_store.get(device_id)
        
        # Mock API to return this sensor with old last_seen timestamp
        old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        mock_sensors_from_api = [
            {
                "id": device_id,
                "sensor_type": "humidity",
                "last_seen": old_timestamp
            }
        ]
        
        # Act: Run silence sweep with mocked API response
        with patch('core.engine.get_sensors_last_seen', return_value=mock_sensors_from_api):
            now = datetime.now(timezone.utc)
            self.engine.sweep_silence(now)
        
        # Assert: missing_keepalive alert should be created (gap > threshold)
        assert "missing_keepalive" in device_state.open_alerts, \
            f"Expected missing_keepalive alert for device silent for 10 minutes (threshold is ~3 minutes)"
        
        # Verify alert was emitted
        assert self.mock_writer.write.call_count >= 1, "Expected alert emission"
        emitted_alert = self.mock_writer.write.call_args[0][0]
        assert emitted_alert.issue_type == "missing_keepalive"
        assert emitted_alert.device_id == device_id
        assert emitted_alert.end_ts is None, "Alert should be open"

    def test_sweep_silence_detects_prolonged_silence_correctly(self):
        """CRITICAL: sweep_silence must detect devices silent for too long and close alerts when they resume.
        This tests REAL business logic: comparing API timestamps against threshold.""" 
        # Arrange: Add device to state store
        device_id = "old_device"
        self.state_store.add_device(device_id, "temperature")
        device_state = self.state_store.get(device_id)
        
        # Mock API to return sensor with old last_seen (10 minutes ago - exceeds 3 min threshold)
        old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        mock_sensors_from_api = [
            {
                "id": device_id,
                "sensor_type": "temperature",
                "last_seen": old_timestamp
            }
        ]
        
        # Act: Run silence sweep with mocked API - should open missing_keepalive alert
        with patch('core.engine.get_sensors_last_seen', return_value=mock_sensors_from_api):
            now = datetime.now(timezone.utc)
            self.engine.sweep_silence(now)
        
        # Assert: missing_keepalive alert should be created (device silent > threshold)
        assert "missing_keepalive" in device_state.open_alerts, \
            "Expected missing_keepalive alert for device silent for 10 minutes"
        
        # Verify alert was emitted
        assert self.mock_writer.write.call_count >= 1
        first_alert = self.mock_writer.write.call_args[0][0]
        assert first_alert.issue_type == "missing_keepalive"
        assert first_alert.device_id == device_id
        assert first_alert.end_ts is None, "Initial alert should be open"
        
        # Reset mock for next phase
        self.mock_writer.reset_mock()
        
        # Act 2: Run sweep again with RECENT timestamp - should close the alert
        recent_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        mock_sensors_recent = [
            {
                "id": device_id,
                "sensor_type": "temperature",
                "last_seen": recent_timestamp
            }
        ]
        
        with patch('core.engine.get_sensors_last_seen', return_value=mock_sensors_recent):
            now = datetime.now(timezone.utc)
            self.engine.sweep_silence(now)
        
        # Assert: Alert should be closed (gap now < threshold)
        assert "missing_keepalive" not in device_state.open_alerts, \
            "Alert should be closed when device is no longer silent"
        
        # Verify closing alert was emitted
        assert self.mock_writer.write.call_count >= 1
        closing_alert = self.mock_writer.write.call_args[0][0]
        assert closing_alert.issue_type == "missing_keepalive"
        assert closing_alert.end_ts is not None, "Closing alert should have end_ts"

    def test_multiple_writers_receive_all_alerts(self):
        """CRITICAL: When multiple writers are configured, all must receive every alert."""
        # Arrange: Setup engine with multiple writers
        writer1 = Mock()
        writer2 = Mock()  
        writer3 = Mock()
        
        engine = Engine(self.cfg, [writer1, writer2, writer3], self.state_store)
        
        device_id = "7"
        self.state_store.add_device(device_id, "temperature")
        
        # Act: Generate an alert using REAL message format
        bad_message = self.create_real_sensor_message(
            device_id="7",
            sensor_type="temperature", 
            value=-100.0  # Out of range (below min of -40)
        )
        
        bad_event = self.to_event(bad_message)
        assert bad_event is not None
        engine.process_event(bad_event)
        
        # Assert: All writers should receive the alert
        assert writer1.write.call_count == 1
        assert writer2.write.call_count == 1  
        assert writer3.write.call_count == 1
        
        # Verify they all got the same alert
        alert1 = writer1.write.call_args[0][0]
        alert2 = writer2.write.call_args[0][0] 
        alert3 = writer3.write.call_args[0][0]
        
        assert alert1.issue_type == alert2.issue_type == alert3.issue_type == "out_of_range"
        assert alert1.device_id == alert2.device_id == alert3.device_id == device_id

    def test_device_state_updates_correctly_during_processing(self):
        """CRITICAL: Device state must be updated properly with each event."""
        # Arrange
        device_id = "8"
        self.state_store.add_device(device_id, "humidity") 
        
        initial_state = self.state_store.get(device_id)
        assert initial_state.last_seen_ts is None
        assert initial_state.last_value is None
        
        # Act: Process first event using REAL message format
        first_message = self.create_real_sensor_message(
            device_id="8",
            sensor_type="humidity",
            value=45.2
        )
        
        first_event = self.to_event(first_message)
        assert first_event is not None
        first_process_time = first_event.ts  # Capture the actual timestamp used
        
        self.engine.process_event(first_event)
        
        # Assert: State should be updated
        updated_state = self.state_store.get(device_id)
        assert updated_state.last_seen_ts == first_process_time
        assert updated_state.last_value == 45.2
        assert updated_state.sensor_type == "humidity"
        
        # Act: Process second event with different values
        time.sleep(0.1)  # Ensure different timestamp
        second_message = self.create_real_sensor_message(
            device_id="8",
            sensor_type="humidity",
            value=67.8
        )
        
        second_event = self.to_event(second_message)
        assert second_event is not None
        second_process_time = second_event.ts
        
        self.engine.process_event(second_event)
        
        # Assert: State should reflect latest values
        final_state = self.state_store.get(device_id)
        assert final_state.last_seen_ts == second_process_time
        assert final_state.last_value == 67.8
        assert final_state.sensor_type == "humidity"


class TestEngineEdgeCases:
    """Tests for edge cases and error scenarios."""
    
    def setup_method(self):
        self.mock_writer = Mock()
        self.cfg = {
            "features": {"corrupted": True, "out_of_range": True, "stuck_sensor": True, "silence": True},
            "prolonged_silence_seconds": 300
        }
        self.engine = Engine(self.cfg, self.mock_writer)
    
    def create_real_sensor_message(self, device_id, sensor_type, value, msg_type="telemetry", **extra):
        """Create a message in the EXACT format that comes from real sensors."""
        return {
            "sid": f"sensor-{device_id}",
            "id": int(device_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "msg_type": msg_type,
            "value": value,
            "sensor": sensor_type,
            "plant_id": 123,
            "temperature": value if sensor_type == "temperature" else 25.0,
            "humidity": value if sensor_type == "humidity" else 65.0,
            "ph": 7.0,
            "n": 50.0,
            "p": 30.0,
            "k": 40.0,
            **extra
        }
    
    def to_event(self, sensor_message):
        """Convert sensor message to Event using EXACT logic from main.py."""
        if not isinstance(sensor_message, dict):
            return None
        ts = datetime.now(timezone.utc)
        device_id = sensor_message.get("id")
        sensor_type = sensor_message.get("sensor_type") or sensor_message.get("sensor", "unknown_sensor")
        if not device_id:
            device_id = "unknown_device"
        else:
            device_id = str(device_id)
        
        return Event(
            ts=ts,
            device_id=device_id,
            sensor_type=sensor_type,
            site_id=sensor_message.get("site_id"),
            msg_type=sensor_message.get("msg_type", "reading"),
            value=sensor_message.get("value"),
            seq=sensor_message.get("seq"),
            quality=sensor_message.get("quality"),
        )
    
    def test_engine_handles_none_values_gracefully(self):
        """Edge case: Engine should handle None/null values without crashing."""
        # Arrange: Add device
        device_id = "9"
        self.engine.state.add_device(device_id, "temperature")
        
        # Act: Send REAL message with None value (like corrupted sensor reading)
        null_message = self.create_real_sensor_message(
            device_id="9",
            sensor_type="temperature",
            value=None  # Corrupted/missing sensor reading
        )
        
        null_event = self.to_event(null_message)
        assert null_event is not None
        
        # This should not raise an exception
        try:
            self.engine.process_event(null_event)
        except Exception as e:
            pytest.fail(f"Engine crashed with None value: {e}")
    
    def test_sweep_silence_on_empty_state_store(self):
        """Edge case: sweep_silence should handle empty state store."""
        # Act: Run sweep on empty state (should not crash)
        try:
            self.engine.sweep_silence(datetime.now(timezone.utc))
        except Exception as e:
            pytest.fail(f"sweep_silence crashed on empty state: {e}")
        
        # Assert: No alerts should be generated  
        assert self.mock_writer.write.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])