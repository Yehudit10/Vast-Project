from pathlib import Path
from run_bench import run_and_profile, file_size_minio, main
from unittest.mock import patch, Mock, MagicMock, call
import subprocess
import csv
import pytest

# Test the `run_and_profile` function
@patch('psutil.Process')
@patch('psutil.NoSuchProcess', new=Exception)
@patch('run_bench.subprocess.Popen')
def test_run_and_profile(mock_popen, mock_process_class):
    """Test run_and_profile function with mocked subprocess and psutil"""
    # Setup mocks
    mock_proc = Mock()
    mock_proc.pid = 12345
    mock_proc.poll.side_effect = [None, None, 0]  # Simulate process running then finishing
    mock_proc.communicate.return_value = (b"ffmpeg version", b"")
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc
    
    # Mock psutil Process
    mock_parent = Mock()
    mock_parent.cpu_percent.return_value = 50.0
    mock_parent.children.return_value = []
    mock_process_class.return_value = mock_parent
    
    # Set up a test command for profiling
    cmd = ["ffmpeg", "-version"]
    
    # Run the command and get results
    rc, wall_time, cpu, output = run_and_profile(cmd)
    
    # Test if the command ran successfully
    assert rc == 0, f"Command failed with return code {rc}"
    assert wall_time > 0, "Wall time should be greater than zero"
    assert cpu >= 0, "CPU usage should be non-negative"
    assert b"ffmpeg" in output, "Expected output not found"


# Test the `file_size_minio` function
@patch('run_bench.client')
def test_file_size(mock_client):
    """Test file_size_minio function with mocked MinIO client"""
    test_obj_name = "sound/drone-01_20251102t010618z.wav"
    
    # Mock stat_object to return a size
    mock_stat = Mock()
    mock_stat.size = 1024000  # 1MB
    mock_client.stat_object.return_value = mock_stat
    
    # Get the file size
    size = file_size_minio(test_obj_name)
    
    # Test if the file size is correct
    assert size == 1024000, f"Expected file size 1024000, but got {size}"
    mock_client.stat_object.assert_called_once()


# Test the `main` function to check if the CSV is created correctly
@patch('run_bench.client')
@patch('run_bench.iter_audio_files')
@patch('run_bench.download_raw_to_temp')
@patch('run_bench.replace_with_compressed')
@patch('run_bench.run_and_profile')
@patch('run_bench.parse_timestamp_from_filename')
@patch('run_bench.get_file_age_seconds')
@patch('run_bench.build_ffmpeg_cmds')
def test_main(mock_build, mock_get_age, mock_parse_ts, mock_profile, 
              mock_replace, mock_download, mock_iter, mock_client):
    """Test main function with all dependencies mocked"""
    from datetime import datetime
    
    # Setup mocks
    test_obj = "sound/test_20251102t120000z.wav"
    mock_iter.return_value = [test_obj]
    
    mock_dt = datetime(2025, 11, 2, 12, 0, 0)
    mock_parse_ts.return_value = mock_dt
    mock_get_age.return_value = 86400  # 1 day
    
    # Mock local file
    mock_local = Mock()
    mock_local.stat.return_value.st_size = 2000000  # 2MB original
    mock_local.unlink = Mock()
    mock_download.return_value = mock_local
    
    # Mock encoding
    mock_profile.return_value = (0, 5.0, 75.0, b"")  # success, 5s, 75% CPU
    
    # Mock MinIO client for file_size_minio
    mock_stat = Mock()
    mock_stat.size = 500000  # 500KB compressed
    mock_client.stat_object.return_value = mock_stat
    
    # Mock replace operation
    mock_replace.return_value = "sound/test_20251102t120000z.opus"
    
    # Mock output file
    mock_output = Mock()
    mock_output.unlink = Mock()
    
    # Mock build_ffmpeg_cmds
    mock_build.return_value = [
        ("opus", ["ffmpeg", "-i", "test.wav", "test.opus"], mock_output)
    ]
    
    # Run main
    result_path = Path("results/benchmarks.csv")
    if result_path.exists():
        result_path.unlink()
    
    main()
    
    # Check if the results file was created
    assert result_path.exists(), "The result CSV file was not created"
    
    # Check if it contains rows
    with open(result_path, "r") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        assert len(rows) > 0, "No rows in the results CSV"
        
        # Verify row contents
        row = rows[0]
        assert row["codec"] == "opus"
        assert float(row["compression_ratio_orig_over_encoded"]) == 4.0  # 2MB / 500KB


# Additional tests for edge cases
@patch('run_bench.client')
def test_file_size_invalid_file(mock_client):
    """Test the file size function with a non-existent file"""
    invalid_obj = "sound/nonexistent_file.wav"
    
    # Mock stat_object to raise exception
    mock_client.stat_object.side_effect = Exception("Object not found")
    
    size = file_size_minio(invalid_obj)
    assert size == 0, f"Expected file size to be 0, but got {size}"


@patch('run_bench.client')
@patch('run_bench.iter_audio_files')
def test_main_no_files(mock_iter, mock_client, capsys):
    """Test main function when no files are found"""
    mock_iter.return_value = []
    
    main()
    
    captured = capsys.readouterr()
    assert "No audio files found" in captured.out


@patch('run_bench.client')
@patch('run_bench.iter_audio_files')
@patch('run_bench.download_raw_to_temp')
@patch('run_bench.run_and_profile')
@patch('run_bench.parse_timestamp_from_filename')
@patch('run_bench.get_file_age_seconds')
@patch('run_bench.build_ffmpeg_cmds')
def test_main_encoding_failure(mock_build, mock_get_age, mock_parse_ts, 
                               mock_profile, mock_download, mock_iter, mock_client):
    """Test main function when encoding fails"""
    from datetime import datetime
    
    test_obj = "sound/test.wav"
    mock_iter.return_value = [test_obj]
    
    mock_parse_ts.return_value = datetime(2025, 11, 2, 12, 0, 0)
    mock_get_age.return_value = 0
    
    mock_local = Mock()
    mock_local.stat.return_value.st_size = 1000000
    mock_local.unlink = Mock()
    mock_download.return_value = mock_local
    
    # Mock failed encoding (return code != 0)
    mock_profile.return_value = (1, 0.0, 0.0, b"error")
    
    mock_output = Mock()
    mock_output.unlink = Mock()
    
    mock_build.return_value = [
        ("opus", ["ffmpeg", "-i", "test.wav", "test.opus"], mock_output)
    ]
    
    result_path = Path("results/benchmarks.csv")
    if result_path.exists():
        result_path.unlink()
    
    main()
    
    # CSV should not be created or should be empty
    if result_path.exists():
        with open(result_path, "r") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            assert len(rows) == 0, "Should have no successful encodings"
