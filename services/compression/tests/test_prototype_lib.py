"""
Tests for prototype_lib.py - Audio compression library
Updated to match the new implementation with same-path compression
"""

from pathlib import Path
import pytest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
from prototype_lib import (
    is_audio_file,
    iter_audio_files,
    parse_timestamp_from_filename,
    get_file_age_seconds,
    is_older_than,
    build_ffmpeg_cmds,
    get_compressed_variants,
    find_file_with_fallback,
    AUDIO_EXTS,
    RAW_PREFIX
)


class TestIsAudioFile:
    """Tests for is_audio_file function"""
    
    def test_valid_audio_extensions(self):
        """Test that valid audio files are recognized"""
        valid_files = [
            "audio.wav", "music.mp3", "sound.flac", "voice.opus",
            "song.ogg", "track.m4a", "audio.aac", "sound.wma"
        ]
        
        for filename in valid_files:
            assert is_audio_file(filename), f"{filename} should be recognized as audio"
    
    def test_case_insensitive(self):
        """Test case insensitivity"""
        assert is_audio_file("AUDIO.WAV")
        assert is_audio_file("Music.MP3")
        assert is_audio_file("SoUnD.fLaC")
    
    def test_invalid_extensions(self):
        """Test that non-audio files are rejected"""
        invalid_files = [
            "doc.txt", "image.jpg", "video.mp4", "data.csv", "script.py"
        ]
        
        for filename in invalid_files:
            assert not is_audio_file(filename), f"{filename} should not be recognized as audio"
    
    def test_audio_exts_constant(self):
        """Test that AUDIO_EXTS contains expected formats"""
        expected = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}
        assert AUDIO_EXTS == expected


class TestIterAudioFiles:
    """Tests for iter_audio_files function"""
    
    @patch('prototype_lib.client')
    def test_iter_audio_files_filters_correctly(self, mock_client):
        """Test that only audio files are returned"""
        # Mock MinIO objects
        mock_objects = [
            Mock(object_name=f"{RAW_PREFIX}drone-01_20251102t010618z.wav"),
            Mock(object_name=f"{RAW_PREFIX}sensor-02_20251102t020000z.mp3"),
            Mock(object_name=f"{RAW_PREFIX}data.txt"),  # Should be filtered out
            Mock(object_name=f"{RAW_PREFIX}image.jpg"),  # Should be filtered out
        ]
        mock_client.list_objects.return_value = mock_objects
        
        files = list(iter_audio_files())
        
        assert len(files) == 2
        assert all(is_audio_file(f) for f in files)
        mock_client.list_objects.assert_called_once()
    
    @patch('prototype_lib.client')
    def test_iter_audio_files_empty_bucket(self, mock_client):
        """Test with empty bucket"""
        mock_client.list_objects.return_value = []
        
        files = list(iter_audio_files())
        
        assert len(files) == 0


class TestParseTimestampFromFilename:
    """Tests for parse_timestamp_from_filename function"""
    
    def test_valid_timestamp_lowercase(self):
        """Test parsing valid timestamp (lowercase t and z)"""
        filename = "drone-01_20251102t010618z.wav"
        dt = parse_timestamp_from_filename(filename)
        
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 11
        assert dt.day == 2
        assert dt.hour == 1
        assert dt.minute == 6
        assert dt.second == 18
    
    def test_valid_timestamp_uppercase(self):
        """Test parsing valid timestamp (uppercase T and Z)"""
        filename = "sensor-06_20251028T080000Z.opus"
        dt = parse_timestamp_from_filename(filename)
        
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 28
        assert dt.hour == 8
        assert dt.minute == 0
        assert dt.second == 0
    
    def test_valid_timestamp_mixed_case(self):
        """Test parsing with mixed case"""
        filename = "device_20240101T120000z.mp3"
        dt = parse_timestamp_from_filename(filename)
        
        assert dt is not None
        assert dt.year == 2024
    
    def test_invalid_timestamp_format(self):
        """Test with invalid timestamp format"""
        invalid_filenames = [
            "audio_without_timestamp.wav",
            "audio_20251102.wav",  # Missing time
            "audio_2025-11-02t01:06:18z.wav",  # Wrong format (hyphens and colons)
        ]
        
        for filename in invalid_filenames:
            dt = parse_timestamp_from_filename(filename)
            assert dt is None, f"Should return None for {filename}"
    
    def test_invalid_date_values(self):
        """Test with invalid date values"""
        # Invalid month (13)
        filename = "audio_20251302t010618z.wav"
        dt = parse_timestamp_from_filename(filename)
        assert dt is None
    
    def test_full_path(self):
        """Test parsing from full MinIO path"""
        full_path = "sound/drone-01_20251102t010618z.wav"
        dt = parse_timestamp_from_filename(full_path)
        
        assert dt is not None
        assert dt.year == 2025


class TestGetFileAgeSeconds:
    """Tests for get_file_age_seconds function"""
    
    @patch('prototype_lib.datetime')
    def test_get_file_age_recent_file(self, mock_datetime_module):
        """Test age calculation for recent file"""
        # Mock current time
        now = datetime(2025, 11, 2, 12, 0, 0)
        mock_datetime_module.utcnow.return_value = now
        mock_datetime_module.strptime = datetime.strptime
        
        # File timestamp: 1 hour ago
        filename = "audio_20251102t110000z.wav"
        
        age = get_file_age_seconds(filename)
        
        assert age == 3600  # 1 hour in seconds
    
    @patch('prototype_lib.datetime')
    def test_get_file_age_old_file(self, mock_datetime_module):
        """Test age calculation for old file"""
        now = datetime(2025, 11, 2, 12, 0, 0)
        mock_datetime_module.utcnow.return_value = now
        mock_datetime_module.strptime = datetime.strptime
        
        # File timestamp: 30 days ago
        filename = "audio_20251003t120000z.wav"
        
        age = get_file_age_seconds(filename)
        
        expected_age = 30 * 86400  # 30 days in seconds
        assert abs(age - expected_age) < 60  # Allow 1 minute tolerance
    
    def test_get_file_age_no_timestamp(self):
        """Test with file that has no parseable timestamp"""
        filename = "audio_no_timestamp.wav"
        
        age = get_file_age_seconds(filename)
        
        assert age == 0


class TestIsOlderThan:
    """Tests for is_older_than function"""
    
    @patch('prototype_lib.get_file_age_seconds')
    def test_is_older_than_true(self, mock_get_age):
        """Test when file is older than threshold"""
        mock_get_age.return_value = 7200  # 2 hours
        
        result = is_older_than("audio.wav", 3600)  # 1 hour threshold
        
        assert result is True
    
    @patch('prototype_lib.get_file_age_seconds')
    def test_is_older_than_false(self, mock_get_age):
        """Test when file is younger than threshold"""
        mock_get_age.return_value = 1800  # 30 minutes
        
        result = is_older_than("audio.wav", 3600)  # 1 hour threshold
        
        assert result is False
    
    @patch('prototype_lib.get_file_age_seconds')
    def test_is_older_than_equal(self, mock_get_age):
        """Test when file age equals threshold"""
        mock_get_age.return_value = 3600
        
        result = is_older_than("audio.wav", 3600)
        
        assert result is True  # >= should return True


class TestBuildFfmpegCmds:
    """Tests for build_ffmpeg_cmds function"""
    
    def test_build_commands_all_codecs(self):
        """Test building commands for all codecs"""
        input_path = Path("test_audio.wav")
        
        cmds = build_ffmpeg_cmds(input_path, codec="all")
        
        assert len(cmds) == 2
        codec_names = [cmd[0] for cmd in cmds]
        assert "flac" in codec_names
        assert "opus" in codec_names
    
    def test_build_commands_flac_only(self):
        """Test building commands for FLAC only"""
        input_path = Path("test_audio.wav")
        
        cmds = build_ffmpeg_cmds(input_path, codec="flac")
        
        assert len(cmds) == 1
        assert cmds[0][0] == "flac"
        assert "-c:a" in cmds[0][1]
        assert "flac" in cmds[0][1]
    
    def test_build_commands_opus_only(self):
        """Test building commands for Opus only"""
        input_path = Path("test_audio.wav")
        
        cmds = build_ffmpeg_cmds(input_path, codec="opus")
        
        assert len(cmds) == 1
        assert cmds[0][0] == "opus"
        assert "-c:a" in cmds[0][1]
        assert "libopus" in cmds[0][1]
    
    def test_build_commands_custom_parameters(self):
        """Test custom compression parameters"""
        input_path = Path("test.wav")
        
        cmds = build_ffmpeg_cmds(input_path, codec="all", 
                                 flac_level="8", opus_bitrate="128k")
        
        flac_cmd = [c for c in cmds if c[0] == "flac"][0]
        opus_cmd = [c for c in cmds if c[0] == "opus"][0]
        
        assert "8" in flac_cmd[1]
        assert "128k" in opus_cmd[1]
    
    def test_build_commands_output_extensions(self):
        """Test that output files have correct extensions"""
        input_path = Path("audio.wav")
        
        cmds = build_ffmpeg_cmds(input_path, codec="all")
        
        for codec, _, output_path in cmds:
            if codec == "flac":
                assert output_path.suffix == ".flac"
            elif codec == "opus":
                assert output_path.suffix == ".opus"
    
    def test_build_commands_preserves_stem(self):
        """Test that file stem is preserved"""
        input_path = Path("my_audio_file.wav")
        
        cmds = build_ffmpeg_cmds(input_path)
        
        for _, _, output_path in cmds:
            assert output_path.stem == "my_audio_file"


class TestGetCompressedVariants:
    """Tests for get_compressed_variants function"""
    
    def test_get_variants_basic(self):
        """Test getting compressed variants"""
        obj_name = "sound/drone-01_20251102t010618z.wav"
        
        variants = get_compressed_variants(obj_name)
        
        assert len(variants) == 2
        assert "sound/drone-01_20251102t010618z.opus" in variants
        assert "sound/drone-01_20251102t010618z.flac" in variants
    
    def test_get_variants_already_compressed(self):
        """Test variants for already compressed file"""
        obj_name = "sound/audio.opus"
        
        variants = get_compressed_variants(obj_name)
        
        assert "sound/audio.opus" in variants
        assert "sound/audio.flac" in variants
    
    def test_get_variants_nested_path(self):
        """Test with nested directory structure"""
        obj_name = "sound/folder1/folder2/audio.mp3"
        
        variants = get_compressed_variants(obj_name)
        
        assert all("folder1/folder2" in v for v in variants)


class TestFindFileWithFallback:
    """Tests for find_file_with_fallback function"""
    
    @patch('prototype_lib.client')
    def test_find_original_exists(self, mock_client):
        """Test when original file exists"""
        obj_name = "sound/audio.wav"
        mock_client.stat_object.return_value = Mock()
        
        found, exists = find_file_with_fallback(obj_name)
        
        assert exists is True
        assert found == obj_name
        mock_client.stat_object.assert_called_once()
    
    @patch('prototype_lib.client')
    def test_find_compressed_variant(self, mock_client):
        """Test fallback to compressed variant"""
        obj_name = "sound/audio.wav"
        
        # First call (original) fails, second call (opus variant) succeeds
        mock_client.stat_object.side_effect = [
            Exception("Not found"),  # Original doesn't exist
            Mock(),  # Opus variant exists
        ]
        
        found, exists = find_file_with_fallback(obj_name)
        
        assert exists is True
        assert found == "sound/audio.opus"
        assert mock_client.stat_object.call_count == 2
    
    @patch('prototype_lib.client')
    def test_find_no_variants_exist(self, mock_client):
        """Test when no variants exist"""
        obj_name = "sound/audio.wav"
        mock_client.stat_object.side_effect = Exception("Not found")
        
        found, exists = find_file_with_fallback(obj_name)
        
        assert exists is False
        assert found == obj_name
        assert mock_client.stat_object.call_count == 3  # Original + 2 variants


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_parse_timestamp_edge_dates(self):
        """Test with edge case dates"""
        # New Year
        dt = parse_timestamp_from_filename("audio_20250101t000000z.wav")
        assert dt.month == 1 and dt.day == 1
        
        # End of year
        dt = parse_timestamp_from_filename("audio_20251231t235959z.wav")
        assert dt.month == 12 and dt.day == 31
    
    def test_build_ffmpeg_special_characters(self):
        """Test with special characters in filename"""
        special_names = [
            Path("file with spaces.wav"),
            Path("file-with-dashes.mp3"),
            Path("file_with_underscores.flac"),
        ]
        
        for input_path in special_names:
            cmds = build_ffmpeg_cmds(input_path)
            assert len(cmds) > 0
    
    def test_audio_extensions_lowercase(self):
        """Ensure all extensions in AUDIO_EXTS are lowercase"""
        for ext in AUDIO_EXTS:
            assert ext.islower(), f"Extension {ext} should be lowercase"
            assert ext.startswith("."), f"Extension {ext} should start with dot"


class TestIntegration:
    """Integration tests"""
    
    @patch('prototype_lib.datetime')
    @patch('prototype_lib.client')
    def test_full_workflow_simulation(self, mock_client, mock_datetime_module):
        """Simulate full workflow: list -> filter -> check age -> find"""
        # Setup
        now = datetime(2025, 11, 2, 12, 0, 0)
        mock_datetime_module.utcnow.return_value = now
        mock_datetime_module.strptime = datetime.strptime
        
        # Mock MinIO files (one old, one new)
        mock_objects = [
            Mock(object_name="sound/old_20251001t120000z.wav"),  # 32 days old
            Mock(object_name="sound/new_20251102t100000z.wav"),  # 2 hours old
        ]
        mock_client.list_objects.return_value = mock_objects
        
        # Get all audio files
        files = list(iter_audio_files())
        assert len(files) == 2
        
        # Check which are old (30+ days)
        threshold = 30 * 86400
        old_files = [f for f in files if is_older_than(f, threshold)]
        
        assert len(old_files) == 1
        assert "old_" in old_files[0]
