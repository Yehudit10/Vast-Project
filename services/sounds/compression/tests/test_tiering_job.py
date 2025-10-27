import pytest
from pathlib import Path
import time
import subprocess
import tempfile
import shutil
import os
from unittest.mock import patch, MagicMock, mock_open, Mock
from src.tiering_job import (
    is_older_than, encode, cleanup_compressed, get_age_seconds, main
)


class TestGetAgeSeconds:
    """Tests for the function get_age_seconds"""
    
    def test_get_age_seconds_mtime(self, tmp_path):
        """Test the file age based on mtime"""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")
        
        age = get_age_seconds(test_file, "mtime")
        assert age >= 0
        assert age < 1  # A newly created file should be less than a second old
    
    def test_get_age_seconds_ctime(self, tmp_path):
        """Test the file age based on ctime"""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")
        
        age = get_age_seconds(test_file, "ctime")
        assert age >= 0
        assert age < 1  # A newly created file should be less than a second old
    
    @patch('time.time')
    @patch('os.stat')
    def test_get_age_seconds_old_file(self, mock_stat, mock_time):
        """Test the file age for an old file"""
        mock_time.return_value = 1000000  # Simulated current time
        
        # Creating a mock stat object
        mock_stat_result = Mock()
        mock_stat_result.st_mtime = 996400  # 1000000 - 3600 (1 hour)
        mock_stat_result.st_ctime = 996400
        mock_stat.return_value = mock_stat_result
        
        test_file = Path("old_file.txt")
        
        age_mtime = get_age_seconds(test_file, "mtime")
        age_ctime = get_age_seconds(test_file, "ctime")
        
        assert age_mtime == 3600  # File is 3600 seconds (1 hour) old
        assert age_ctime == 3600  # File is 3600 seconds (1 hour) old


class TestIsOlderThan:
    """Tests for the function is_older_than"""
    
    @patch('scripts.tiering_job.get_age_seconds')
    def test_is_older_than_true(self, mock_get_age):
        """Test when the file is older than the threshold"""
        mock_get_age.return_value = 7200  # 2 hours
        test_path = Path("test.txt")
        
        result = is_older_than(test_path, 3600, "mtime")  # Threshold of 1 hour
        assert result is True
        mock_get_age.assert_called_once_with(test_path, "mtime")
    
    @patch('scripts.tiering_job.get_age_seconds')
    def test_is_older_than_false(self, mock_get_age):
        """Test when the file is younger than the threshold"""
        mock_get_age.return_value = 1800  # 30 minutes
        test_path = Path("test.txt")
        
        result = is_older_than(test_path, 3600, "mtime")  # Threshold of 1 hour
        assert result is False
    
    @patch('scripts.tiering_job.get_age_seconds')
    def test_is_older_than_equal(self, mock_get_age):
        """Test when the file is exactly at the threshold age"""
        mock_get_age.return_value = 3600  # Exactly 1 hour
        test_path = Path("test.txt")
        
        result = is_older_than(test_path, 3600, "mtime")  # Threshold of 1 hour
        assert result is True  # >= should return True
    
    def test_is_older_than_invalid_mode(self):
        """Test invalid mode scenario"""
        test_path = Path("test.txt")
        
        with pytest.raises(ValueError, match="Invalid mode: invalid"):
            is_older_than(test_path, 3600, "invalid")
    
    def test_is_older_than_ctime_mode(self, tmp_path):
        """Test the ctime mode scenario"""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")
        
        # Since the file is new, it should not be older than 10 seconds
        result = is_older_than(test_file, 10, "ctime")
        assert result is False

class TestEncode:
    """Tests for the 'encode' function"""

    @patch('scripts.tiering_job.build_ffmpeg_cmds')
    @patch('subprocess.call')
    def test_encode_success(self, mock_subprocess, mock_build_cmds):
        """Test for successful encoding"""
        test_path = Path("input.wav")  # Input file
        output_path = Path("output.flac")  # Expected output file
        
        # Mock the ffmpeg command building
        mock_build_cmds.return_value = [
            ("flac", ["ffmpeg", "-i", "input.wav", "output.flac"], output_path)
        ]
        mock_subprocess.return_value = 0  # Simulate success
        
        result = encode(test_path, "flac")  # Call the encode function
        
        assert result == output_path  # Check that the result matches the expected output
        mock_build_cmds.assert_called_once_with(test_path)  # Ensure the ffmpeg command was built with the correct input
        mock_subprocess.assert_called_once()  # Ensure subprocess.call was called once

    @patch('scripts.tiering_job.build_ffmpeg_cmds')
    @patch('subprocess.call')
    def test_encode_subprocess_failure(self, mock_subprocess, mock_build_cmds):
        """Test for subprocess failure during encoding"""
        test_path = Path("input.wav")
        output_path = Path("output.flac")
        
        # Mock the ffmpeg command building
        mock_build_cmds.return_value = [
            ("flac", ["ffmpeg", "-i", "input.wav", "output.flac"], output_path)
        ]
        mock_subprocess.return_value = 1  # Simulate failure (non-zero return code)
        
        # Assert that an exception is raised when encoding fails
        with pytest.raises(RuntimeError, match="Encode failed: input.wav -> flac"):
            encode(test_path, "flac")

    @patch('scripts.tiering_job.build_ffmpeg_cmds')
    def test_encode_unsupported_codec(self, mock_build_cmds):
        """Test for unsupported codec during encoding"""
        test_path = Path("input.wav")
        
        # Mock the ffmpeg command building with supported codecs (flac, opus)
        mock_build_cmds.return_value = [
            ("flac", ["ffmpeg", "-i", "input.wav", "output.flac"], Path("output.flac")),
            ("opus", ["ffmpeg", "-i", "input.wav", "output.opus"], Path("output.opus"))
        ]
        
        # Test for an unsupported codec (mp3)
        with pytest.raises(ValueError, match="Unsupported codec: mp3"):
            encode(test_path, "mp3")

    @patch('scripts.tiering_job.build_ffmpeg_cmds')
    @patch('subprocess.call')
    def test_encode_opus(self, mock_subprocess, mock_build_cmds):
        """Test for encoding to opus format"""
        test_path = Path("input.wav")
        output_path = Path("output.opus")
        
        # Mock the ffmpeg command building for opus encoding
        mock_build_cmds.return_value = [
            ("opus", ["ffmpeg", "-i", "input.wav", "output.opus"], output_path)
        ]
        mock_subprocess.return_value = 0  # Simulate success
        
        result = encode(test_path, "opus")  # Call the encode function
        assert result == output_path  # Check that the result matches the expected output

class TestCleanupCompressed:
    """Tests for the cleanup_compressed function"""
    
    def test_cleanup_compressed_negative_age(self):
        """Test for negative age"""
        with pytest.raises(ValueError, match="max_age_days cannot be negative"):
            cleanup_compressed(-1, dry_run=False)  # This should raise an error because the age can't be negative
    
    def test_cleanup_compressed_zero_age(self):
        """Test for zero age - should return 0 without performing any action"""
        result = cleanup_compressed(0, dry_run=False)
        assert result == 0  # No deletion should happen, so result should be 0
    
    @patch('scripts.tiering_job.COMP_DIR')
    @patch('time.time')
    def test_cleanup_compressed_dry_run(self, mock_time, mock_comp_dir, capsys):
        """Test for dry run mode"""
        mock_time.return_value = 1000000  # Mocking the current time
        
        # Creating mock files
        old_file = Mock()
        old_file.name = "old_file.flac"
        old_file.is_file.return_value = True
        old_file_stat = Mock()
        old_file_stat.st_mtime = 1000000 - (2 * 86400)  # 2 days ago
        old_file.stat.return_value = old_file_stat
        
        new_file = Mock()
        new_file.name = "new_file.flac"
        new_file.is_file.return_value = True
        new_file_stat = Mock()
        new_file_stat.st_mtime = 1000000 - 3600  # 1 hour ago
        new_file.stat.return_value = new_file_stat
        
        mock_comp_dir.iterdir.return_value = [old_file, new_file]  # Mocking the directory contents
        
        result = cleanup_compressed(1, dry_run=True)  # In dry run mode, no files should be deleted
        
        assert result == 0  # Nothing should be deleted in dry run mode
        captured = capsys.readouterr()
        assert "[DRY] would delete compressed:" in captured.out  # We expect a dry run message
    
    @patch('scripts.tiering_job.COMP_DIR')
    @patch('time.time')
    def test_cleanup_compressed_actual_deletion(self, mock_time, mock_comp_dir, capsys):
        """Test for actual deletion"""
        mock_time.return_value = 1000000  # Mocking the current time
        
        # Creating mock file to delete
        old_file = Mock()
        old_file.name = "old_file.flac"
        old_file.is_file.return_value = True
        old_file_stat = Mock()
        old_file_stat.st_mtime = 1000000 - (2 * 86400)  # 2 days ago
        old_file.stat.return_value = old_file_stat
        
        mock_comp_dir.iterdir.return_value = [old_file]  # Mocking the directory contents
        
        result = cleanup_compressed(1, dry_run=False)  # In real mode, files should be deleted if older than 1 day
        
        assert result == 1  # One file should be deleted
        old_file.unlink.assert_called_once()  # Checking that unlink was called on the old file
        captured = capsys.readouterr()
        assert "[DEL] compressed old:" in captured.out  # We expect a deletion message
    
    @patch('scripts.tiering_job.COMP_DIR')
    @patch('time.time')
    def test_cleanup_compressed_deletion_error(self, mock_time, mock_comp_dir, capsys):
        """Test for deletion error"""
        mock_time.return_value = 1000000  # Mocking the current time
        
        old_file = Mock()
        old_file.name = "old_file.flac"
        old_file.is_file.return_value = True
        old_file_stat = Mock()
        old_file_stat.st_mtime = 1000000 - (2 * 86400)  # 2 days ago
        old_file.stat.return_value = old_file_stat
        old_file.unlink.side_effect = OSError("Permission denied")  # Mocking an error when trying to delete
        
        mock_comp_dir.iterdir.return_value = [old_file]  # Mocking the directory contents
        
        result = cleanup_compressed(1, dry_run=False)  # Trying to delete with an error
        
        assert result == 0  # No file should be deleted due to the error
        captured = capsys.readouterr()
        assert "[WARN] failed to delete" in captured.out  # We expect a warning message
    
    @patch('scripts.tiering_job.COMP_DIR')
    @patch('time.time')  
    def test_cleanup_compressed_no_old_files(self, mock_time, mock_comp_dir):
        """Test when there are no old files"""
        mock_time.return_value = 1000000  # Mocking the current time
        
        new_file = Mock()
        new_file.name = "new_file.flac"
        new_file.is_file.return_value = True
        new_file_stat = Mock()
        new_file_stat.st_mtime = 1000000 - 3600  # 1 hour ago
        new_file.stat.return_value = new_file_stat
        
        mock_comp_dir.iterdir.return_value = [new_file]  # Mocking the directory contents
        
        result = cleanup_compressed(1, dry_run=False)  # Trying to delete files older than 1 day, but no old files
        
        assert result == 0  # No files should be deleted since they are all too new

class TestMain:
    """Tests for the main function in the 'tiering_job.py' script."""
    
    @patch('sys.argv', ['tiering_job.py', '--dry-run'])
    @patch('scripts.tiering_job.iter_input_files')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_dry_run_default_settings(self, mock_cleanup, mock_iter, capsys):
        """Test dry run with default settings"""
        mock_iter.return_value = []  # Mock that no files are returned
        mock_cleanup.return_value = 0  # Mock that cleanup doesn't delete anything
        
        main()  # Run the main function
        
        # Assert that cleanup was called once with default parameters (90 days, dry_run=True)
        mock_cleanup.assert_called_once_with(90, True)  
        captured = capsys.readouterr()  # Capture the output printed to the console
        assert "Done. Processed=0" in captured.out  # Assert the output indicates no files were processed
    
    @patch('sys.argv', ['tiering_job.py', '--raw-max-age-minutes', '30', '--codec', 'opus'])
    @patch('scripts.tiering_job.iter_input_files')
    @patch('scripts.tiering_job.is_older_than')
    @patch('scripts.tiering_job.encode')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_with_minutes_and_opus(self, mock_cleanup, mock_encode, mock_older, mock_iter):
        """Test with custom settings: max age in minutes and codec set to opus"""
        test_file = Mock()  # Mock a file object
        test_file.name = "test.wav"  # Set the file name
        output_file = Mock()  # Mock an output file after encoding
        output_file.exists.return_value = True  # Mock that the encoded file exists
        
        mock_iter.return_value = [test_file]  # Mock iter_input_files to return our test file
        mock_older.return_value = True  # Mock that the file is older than 30 minutes
        mock_encode.return_value = output_file  # Mock the encoding function
        mock_cleanup.return_value = 1  # Mock cleanup indicating one file was processed
        
        main()  # Run the main function
        
        # Assert that is_older_than was called with the correct arguments
        mock_older.assert_called_with(test_file, 30 * 60, 'mtime')  # 30 minutes in seconds
        # Assert that encode was called with the correct codec ('opus')
        mock_encode.assert_called_with(test_file, 'opus')
        # Assert that cleanup was called with custom settings (90 days, not dry_run)
        mock_cleanup.assert_called_with(90, False)  
    
    @patch('sys.argv', ['tiering_job.py', '--delete-raw-after', '--age-mode', 'ctime'])
    @patch('scripts.tiering_job.iter_input_files')
    @patch('scripts.tiering_job.is_older_than')
    @patch('scripts.tiering_job.encode')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_delete_raw_after(self, mock_cleanup, mock_encode, mock_older, mock_iter, capsys):
        """Test deleting raw files after encoding"""
        test_file = Mock()  # Mock a file object
        test_file.name = "test.wav"
        output_file = Mock()  # Mock the encoded output file
        output_file.exists.return_value = True  # Mock that the encoded file exists
        
        mock_iter.return_value = [test_file]  # Mock iter_input_files to return our test file
        mock_older.return_value = True  # Mock that the file is older than 30 minutes
        mock_encode.return_value = output_file  # Mock the encoding function
        mock_cleanup.return_value = 0  # Mock cleanup showing no files processed
        
        main()  # Run the main function
        
        # Assert that the raw file was deleted after encoding
        test_file.unlink.assert_called_once()
        captured = capsys.readouterr()  # Capture the console output
        # Assert that the raw file deletion was logged in the output
        assert "[DEL] raw:" in captured.out
    
    @patch('sys.argv', ['tiering_job.py', '--compressed-max-age-days', '30'])
    @patch('scripts.tiering_job.iter_input_files')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_custom_compressed_age(self, mock_cleanup, mock_iter):
        """Test setting a custom age for compressed files"""
        mock_iter.return_value = []  # Mock that no files are returned
        mock_cleanup.return_value = 5  # Mock that 5 files were processed
        
        main()  # Run the main function
        
        # Assert that cleanup was called with the custom compressed file age (30 days)
        mock_cleanup.assert_called_once_with(30, False)
    
    @patch('sys.argv', ['tiering_job.py'])
    @patch('scripts.tiering_job.iter_input_files')
    @patch('scripts.tiering_job.is_older_than')
    @patch('scripts.tiering_job.encode')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_encode_failure(self, mock_cleanup, mock_encode, mock_older, mock_iter, capsys):
        """Test handling of encoding failure"""
        test_file = Mock()  # Mock a file object
        test_file.name = "test.wav"
        
        mock_iter.return_value = [test_file]  # Mock iter_input_files to return our test file
        mock_older.return_value = True  # Mock that the file is older than 30 minutes
        mock_encode.side_effect = RuntimeError("Encoding failed")  # Mock encoding failure
        mock_cleanup.return_value = 0  # Mock cleanup showing no files processed
        
        main()  # Run the main function
        
        # Capture the console output
        captured = capsys.readouterr()
        # Assert that the failure was logged in the output
        assert "[FAIL]" in captured.out
        assert "Encoding failed" in captured.out
    
    @patch('sys.argv', ['tiering_job.py', '--raw-max-age-hours', '12'])
    @patch('scripts.tiering_job.iter_input_files')  
    @patch('scripts.tiering_job.is_older_than')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_with_hours_setting(self, mock_cleanup, mock_older, mock_iter):
        """Test setting file age in hours"""
        mock_iter.return_value = []  # Mock that no files are returned
        mock_older.return_value = False  # Mock that the file is not older than the specified hours
        mock_cleanup.return_value = 0  # Mock cleanup showing no files processed
        
        main()  # Run the main function
        
        # Assert that cleanup was called with default settings (90 days, not dry_run)
        mock_cleanup.assert_called_once_with(90, False)

    @patch('sys.argv', ['tiering_job.py', '--dry-run'])
    @patch('scripts.tiering_job.iter_input_files')
    @patch('scripts.tiering_job.is_older_than')
    @patch('scripts.tiering_job.cleanup_compressed')
    def test_main_dry_run_with_files(self, mock_cleanup, mock_older, mock_iter, capsys):
        """Test dry run with files"""
        test_file = Mock()  # Mock a file object
        test_file.name = "test.wav"
        
        mock_iter.return_value = [test_file]  # Mock iter_input_files to return our test file
        mock_older.return_value = True  # Mock that the file is older than 30 minutes
        mock_cleanup.return_value = 0  # Mock cleanup showing no files processed
        
        main()  # Run the main function
        
        # Capture the console output
        captured = capsys.readouterr()
        # Assert that the dry run simulation was logged in the output
        assert "[DRY] would encode" in captured.out
        assert "Done. Processed=1" in captured.out