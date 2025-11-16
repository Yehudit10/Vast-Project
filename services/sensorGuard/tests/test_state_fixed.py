import pytest
from unittest.mock import Mock
import sys
import os

# Add the flink_app to path for imports  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'flink_app'))

from core.state import StateStore
from core.types import DeviceState


class TestStateStore:
    """Test StateStore class public methods"""
    
    def setup_method(self):
        """Arrange - Set up test fixtures"""
        self.state_store = StateStore()
    
    def test_add_device_new(self):
        """Test adding new device to state store"""
        # Act  
        self.state_store.add_device("device_1", "temperature")
        
        # Assert
        assert self.state_store.is_known_device("device_1")
        device_state = self.state_store.get("device_1")
        assert device_state.device_id == "device_1"
        assert device_state.sensor_type == "temperature"
    
    def test_add_device_existing(self):
        """Test adding existing device doesn't overwrite"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        original_state = self.state_store.get("device_1")
        
        # Act - Try to add same device with different sensor type
        self.state_store.add_device("device_1", "humidity")
        
        # Assert - Original state preserved
        current_state = self.state_store.get("device_1")
        assert current_state is original_state
        assert current_state.sensor_type == "temperature"  # Not changed
    
    def test_is_known_device_true(self):
        """Test is_known_device returns True for existing device"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        
        # Act & Assert
        assert self.state_store.is_known_device("device_1") is True
    
    def test_is_known_device_false(self):
        """Test is_known_device returns False for non-existing device"""
        # Act & Assert
        assert self.state_store.is_known_device("unknown_device") is False
    
    def test_get_device_existing(self):
        """Test getting existing device state"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        
        # Act
        device_state = self.state_store.get("device_1")
        
        # Assert
        assert device_state is not None
        assert device_state.device_id == "device_1"
        assert device_state.sensor_type == "temperature"
    
    def test_get_device_nonexistent(self):
        """Test getting non-existent device returns None"""
        # Act
        device_state = self.state_store.get("unknown_device")
        
        # Assert
        assert device_state is None
    
    def test_all_states_empty(self):
        """Test getting all devices when store is empty"""
        # Act
        all_devices = list(self.state_store.all_states())
        
        # Assert
        assert len(all_devices) == 0
    
    def test_all_states_multiple(self):
        """Test getting all devices with multiple devices"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        self.state_store.add_device("device_2", "humidity") 
        self.state_store.add_device("device_3", "pressure")
        
        # Act
        all_states = list(self.state_store.all_states())
        
        # Assert
        assert len(all_states) == 3
        device_ids = [device_id for device_id, state in all_states]
        assert "device_1" in device_ids
        assert "device_2" in device_ids
        assert "device_3" in device_ids
    
    def test_state_persistence(self):
        """Test that device state persists across operations"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        device_state = self.state_store.get("device_1")
        
        # Act - Modify state
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc)
        device_state.last_seen_ts = ts
        device_state.last_value = 25.0
        
        # Assert - Changes persist when retrieving again
        retrieved_state = self.state_store.get("device_1")
        assert retrieved_state.last_seen_ts == ts
        assert retrieved_state.last_value == 25.0
    
    def test_multiple_devices_independence(self):
        """Test that multiple devices maintain independent state"""
        # Arrange
        self.state_store.add_device("device_1", "temperature")
        self.state_store.add_device("device_2", "humidity")
        
        device_1 = self.state_store.get("device_1")
        device_2 = self.state_store.get("device_2")
        
        # Act - Modify only device_1
        device_1.last_value = 25.0
        
        # Assert - device_2 not affected
        assert device_1.last_value == 25.0
        assert device_2.last_value is None
        assert device_1 is not device_2