"""
Tests for tiering_job.py - Audio compression and tiering
Updated to match the new implementation with same-path compression
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, call
from tiering_job import (
    encode_and_replace,
    cleanup_compressed,
    main,
    DEFAULT_RAW_MAX_AGE_DAYS,
    DEFAULT_COMP_MAX_AGE_DAYS,
    DEFAULT_LONG_TERM_CODEC
)


class TestEncodeAndReplace:
    """Tests for encode_and_replace function"""
    
    @patch('tiering_job.download_raw_to_temp')
    @patch('tiering_job.build_ffmpeg_cmds')
    @patch('tiering_job.subprocess.call')
    @patch('tiering_job.replace_with_compressed')
    def test_encode_and_replace_success(
        self, mock_replace, mock_subprocess, mock_build, mock_download
    ):
        """Test successful encoding and replacement"""
        # Setup mocks
        mock_local = Mock()
        mock_local.unlink = Mock()
        mock_download.return_value = mock_local
        
        mock_output = Mock()
        mock_output.unlink = Mock()
        mock_build.return_value = [
            ("opus", ["ffmpeg", "-i", "input", "output"], mock_output)
        ]
        
        mock_subprocess.return_value = 0  # Success
        mock_replace.return_value = "sound/audio.opus"
        
        # Execute
        result = encode_and_replace("sound/audio.wav", "opus")
        
        # Verify
        assert result == "sound/audio.opus"
        mock_download.assert_called_once_with("sound/audio.wav")
        mock_build.assert_called_once()
        mock_subprocess.assert_called_once()
        mock_replace.assert_called_once()
        mock_local.unlink.assert_called_once()
        mock_output.unlink.assert_called_once()
    
    @patch('tiering_job.download_raw_to_temp')
    @patch('tiering_job.build_ffmpeg_cmds')
    @patch('tiering_job.subprocess.call')
    def test_encode_and_replace_encode_failure(
        self, mock_subprocess, mock_build, mock_download
    ):
        """Test handling of encoding failure"""
        mock_local = Mock()
        mock_local.unlink = Mock()
        mock_download.return_value = mock_local
        
        mock_output = Mock()
        mock_output.unlink = Mock()
        mock_build.return_value = [
            ("opus", ["ffmpeg"], mock_output)
        ]
        
        mock_subprocess.return_value = 1  # Failure
        
        with pytest.raises(RuntimeError, match="Encode failed"):
            encode_and_replace("sound/audio.wav", "opus")
        
        # Verify cleanup happened
        mock_local.unlink.assert_called_once()
        mock_output.unlink.assert_called_once()
    
    @patch('tiering_job.download_raw_to_temp')
    @patch('tiering_job.build_ffmpeg_cmds')
    def test_encode_and_replace_no_commands(self, mock_build, mock_download):
        """Test when no encode commands are generated"""
        mock_local = Mock()
        mock_local.unlink = Mock()
        mock_download.return_value = mock_local
        
        mock_build.return_value = []  # No commands
        
        with pytest.raises(RuntimeError, match="No encode commands"):
            encode_and_replace("sound/audio.wav", "opus")
        
        mock_local.unlink.assert_called_once()
    
    @patch('tiering_job.download_raw_to_temp')
    @patch('tiering_job.build_ffmpeg_cmds')
    @patch('tiering_job.subprocess.call')
    @patch('tiering_job.replace_with_compressed')
    def test_encode_and_replace_flac_codec(
        self, mock_replace, mock_subprocess, mock_build, mock_download
    ):
        """Test encoding with FLAC codec"""
        mock_local = Mock()
        mock_local.unlink = Mock()
        mock_download.return_value = mock_local
        
        mock_output = Mock()
        mock_output.unlink = Mock()
        mock_build.return_value = [
            ("flac", ["ffmpeg"], mock_output)
        ]
        
        mock_subprocess.return_value = 0
        mock_replace.return_value = "sound/audio.flac"
        
        result = encode_and_replace("sound/audio.wav", "flac")
        
        assert result == "sound/audio.flac"
        mock_build.assert_called_once_with(mock_local, codec="flac")


class TestCleanupCompressed:
    """Tests for cleanup_compressed function"""
    
    @patch('tiering_job.client')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.delete_object')
    def test_cleanup_compressed_deletes_old_files(
        self, mock_delete, mock_age, mock_client
    ):
        """Test deletion of old compressed files"""
        # Mock old compressed files
        mock_obj1 = Mock()
        mock_obj1.object_name = "compressed/old1.opus"
        mock_obj2 = Mock()
        mock_obj2.object_name = "compressed/old2.flac"
        
        mock_client.list_objects.return_value = [mock_obj1, mock_obj2]
        mock_age.side_effect = [100 * 86400, 95 * 86400]  # Both > 90 days
        
        result = cleanup_compressed(90, dry_run=False)
        
        assert result == 2
        assert mock_delete.call_count == 2
        mock_delete.assert_any_call("compressed/old1.opus")
        mock_delete.assert_any_call("compressed/old2.flac")
    
    @patch('tiering_job.client')
    @patch('tiering_job.get_file_age_seconds')
    def test_cleanup_compressed_keeps_new_files(
        self, mock_age, mock_client
    ):
        """Test that new files are not deleted"""
        mock_obj = Mock()
        mock_obj.object_name = "compressed/new.opus"
        
        mock_client.list_objects.return_value = [mock_obj]
        mock_age.return_value = 10 * 86400  # 10 days old
        
        result = cleanup_compressed(90, dry_run=False)
        
        assert result == 0
    
    @patch('tiering_job.client')
    @patch('tiering_job.get_file_age_seconds')
    def test_cleanup_compressed_dry_run(
        self, mock_age, mock_client, capsys
    ):
        """Test dry run mode"""
        mock_obj = Mock()
        mock_obj.object_name = "compressed/old.opus"
        
        mock_client.list_objects.return_value = [mock_obj]
        mock_age.return_value = 100 * 86400
        
        result = cleanup_compressed(90, dry_run=True)
        
        assert result == 0  # Nothing actually deleted
        captured = capsys.readouterr()
        assert "[DRY]" in captured.out
        assert "Would delete" in captured.out
    
    def test_cleanup_compressed_disabled(self):
        """Test when cleanup is disabled (max_age <= 0)"""
        result = cleanup_compressed(0, dry_run=False)
        assert result == 0
        
        result = cleanup_compressed(-1, dry_run=False)
        assert result == 0


class TestMain:
    """Tests for main function"""
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.cleanup_compressed')
    def test_main_no_files(self, mock_cleanup, mock_iter, capsys):
        """Test when no files need processing"""
        mock_iter.return_value = []
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "Audio files compressed: 0" in captured.out
        mock_cleanup.assert_called_once()
    
    @patch('sys.argv', ['tiering_job.py', '--dry-run'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.cleanup_compressed')
    def test_main_dry_run(
        self, mock_cleanup, mock_older, mock_age, mock_iter, capsys
    ):
        """Test dry run mode"""
        mock_iter.return_value = ["sound/audio.wav"]
        mock_age.return_value = 35 * 86400  # 35 days
        mock_older.return_value = True
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "[DRY]" in captured.out
        assert "Would compress" in captured.out
    
    @patch('sys.argv', ['tiering_job.py', '--codec', 'flac', '--raw-max-age-days', '7'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.encode_and_replace')
    @patch('tiering_job.client')
    @patch('tiering_job.cleanup_compressed')
    def test_main_custom_settings(
        self, mock_cleanup, mock_client, mock_encode,
        mock_older, mock_age, mock_iter
    ):
        """Test with custom codec and age threshold"""
        mock_iter.return_value = ["sound/audio.wav"]
        mock_age.return_value = 10 * 86400  # 10 days
        mock_older.return_value = True
        
        # Mock file stats
        mock_orig_stat = Mock()
        mock_orig_stat.size = 10000000
        mock_comp_stat = Mock()
        mock_comp_stat.size = 5000000
        mock_client.stat_object.side_effect = [mock_orig_stat, mock_comp_stat]
        
        mock_encode.return_value = "sound/audio.flac"
        mock_cleanup.return_value = 0
        
        main()
        
        # Verify encode was called with FLAC
        mock_encode.assert_called_once_with("sound/audio.wav", "flac")
        # Verify age threshold was 7 days
        mock_older.assert_called_with("sound/audio.wav", 7 * 86400)
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.encode_and_replace')
    @patch('tiering_job.client')
    @patch('tiering_job.cleanup_compressed')
    def test_main_successful_compression(
        self, mock_cleanup, mock_client, mock_encode, 
        mock_older, mock_age, mock_iter, capsys
    ):
        """Test successful compression workflow"""
        mock_iter.return_value = ["sound/audio.wav"]
        mock_age.return_value = 35 * 86400  # 35 days
        mock_older.return_value = True
        mock_encode.return_value = "sound/audio.opus"
        
        mock_orig_stat = Mock()
        mock_orig_stat.size = 10000000
        mock_comp_stat = Mock()
        mock_comp_stat.size = 500000
        mock_client.stat_object.side_effect = [mock_orig_stat, mock_comp_stat]
        
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "Compressed:" in captured.out
        assert "Audio files compressed: 1" in captured.out
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.encode_and_replace')
    @patch('tiering_job.client')
    @patch('tiering_job.cleanup_compressed')
    def test_main_encoding_failure(
        self, mock_cleanup, mock_client, mock_encode, mock_older, mock_age, mock_iter, capsys
    ):
        """Test handling of encoding failure"""
        mock_iter.return_value = ["sound/audio.wav"]
        mock_age.return_value = 35 * 86400
        mock_older.return_value = True
        
        # Mock the stat_object to return a size for original file
        mock_orig_stat = Mock()
        mock_orig_stat.size = 10000000
        mock_client.stat_object.return_value = mock_orig_stat
        
        mock_encode.side_effect = RuntimeError("Encoding failed")
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "Encoding failed" in captured.out
        assert "Errors: 1" in captured.out
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.cleanup_compressed')
    def test_main_skip_young_files(
        self, mock_cleanup, mock_older, mock_age, mock_iter, capsys
    ):
        """Test that young files are skipped"""
        mock_iter.return_value = ["sound/new_audio.wav"]
        mock_age.return_value = 5 * 86400  # 5 days old
        mock_older.return_value = False  # Not old enough
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "Files skipped (too new):" in captured.out
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.cleanup_compressed')
    def test_main_skip_files_without_timestamp(
        self, mock_cleanup, mock_older, mock_age, mock_iter, capsys
    ):
        """Test skipping files without parseable timestamp"""
        mock_iter.return_value = ["sound/no_timestamp.wav"]
        mock_age.return_value = 0  # No parseable timestamp
        mock_older.return_value = False
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "[SKIP]" in captured.out
        assert "Cannot parse timestamp" in captured.out
    
    @patch('sys.argv', ['tiering_job.py', '--compressed-max-age-days', '60'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.cleanup_compressed')
    def test_main_cleanup_old_compressed(
        self, mock_cleanup, mock_iter
    ):
        """Test cleanup of old compressed files"""
        mock_iter.return_value = []
        mock_cleanup.return_value = 5
        
        main()
        
        mock_cleanup.assert_called_once_with(60, False)


class TestDefaultConstants:
    """Test default configuration constants"""
    
    def test_default_values(self):
        """Test that default values are reasonable"""
        assert DEFAULT_RAW_MAX_AGE_DAYS > 0
        assert DEFAULT_COMP_MAX_AGE_DAYS > 0
        assert DEFAULT_COMP_MAX_AGE_DAYS >= DEFAULT_RAW_MAX_AGE_DAYS
        assert DEFAULT_LONG_TERM_CODEC in ["opus", "flac"]


class TestArgumentParsing:
    """Test command-line argument parsing"""
    
    @patch('sys.argv', ['tiering_job.py', '--help'])
    def test_help_argument(self):
        """Test that help argument works"""
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
    
    @patch('sys.argv', ['tiering_job.py', '--codec', 'invalid'])
    def test_invalid_codec(self):
        """Test error with invalid codec"""
        with pytest.raises(SystemExit):
            main()


class TestEdgeCases:
    """Test edge cases"""
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.encode_and_replace')
    @patch('tiering_job.client')
    @patch('tiering_job.cleanup_compressed')
    def test_main_multiple_files(
        self, mock_cleanup, mock_client, mock_encode,
        mock_older, mock_age, mock_iter
    ):
        """Test processing multiple files"""
        mock_iter.return_value = [
            "sound/audio1.wav",
            "sound/audio2.wav",
            "sound/audio3.wav"
        ]
        mock_age.return_value = 35 * 86400
        mock_older.return_value = True
        mock_encode.side_effect = [
            "sound/audio1.opus",
            "sound/audio2.opus",
            "sound/audio3.opus"
        ]
        
        mock_stat = Mock()
        mock_stat.size = 1000000
        mock_client.stat_object.return_value = mock_stat
        
        mock_cleanup.return_value = 0
        
        main()
        
        assert mock_encode.call_count == 3
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('tiering_job.iter_audio_files')
    @patch('tiering_job.get_file_age_seconds')
    @patch('tiering_job.is_older_than')
    @patch('tiering_job.encode_and_replace')
    @patch('tiering_job.client')
    @patch('tiering_job.cleanup_compressed')
    def test_main_size_calculation(
        self, mock_cleanup, mock_client, mock_encode,
        mock_older, mock_age, mock_iter, capsys
    ):
        """Test size and ratio calculations"""
        mock_iter.return_value = ["sound/audio.wav"]
        mock_age.return_value = 35 * 86400
        mock_older.return_value = True
        mock_encode.return_value = "sound/audio.opus"
        
        # Original: 10MB, Compressed: 1MB (10x ratio)
        mock_orig = Mock()
        mock_orig.size = 10 * 1024 * 1024
        mock_comp = Mock()
        mock_comp.size = 1 * 1024 * 1024
        
        mock_client.stat_object.side_effect = [mock_orig, mock_comp]
        mock_cleanup.return_value = 0
        
        main()
        
        captured = capsys.readouterr()
        assert "Ratio: 10.00x" in captured.out
        assert "Saved: 9,437,184 bytes" in captured.out


class TestIntegration:
    """Integration-like tests"""
    
    def test_imports(self):
        """Test that all required imports work"""
        from tiering_job import (
            encode_and_replace,
            cleanup_compressed,
            main,
            DEFAULT_RAW_MAX_AGE_DAYS,
            DEFAULT_COMP_MAX_AGE_DAYS,
            DEFAULT_LONG_TERM_CODEC
        )
        
        assert callable(encode_and_replace)
        assert callable(cleanup_compressed)
        assert callable(main)