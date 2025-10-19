from pathlib import Path
from scripts.run_bench import run_and_profile, file_size, main
import subprocess
import csv

# Test the `run_and_profile` function
def test_run_and_profile():
    # Set up a test command for profiling
    cmd = ["ffmpeg", "-version"]  # Test with a simple command (you can replace it with your actual compression command)
    
    # Run the command and get results
    rc, wall_time, cpu, output = run_and_profile(cmd, shell=True)
    
    # Test if the command ran successfully
    assert rc == 0, f"Command failed with return code {rc}"
    assert wall_time > 0, "Wall time should be greater than zero"
    assert cpu >= 0, "CPU usage should be non-negative"
    assert "ffmpeg" in output, "Expected output not found"  # Check if the output contains 'ffmpeg'

# Test the `file_size` function
def test_file_size():
    test_file = Path("data/raw/cat.wav")  # Ensure this file exists for the test
    
    # Make sure the test file exists
    assert test_file.exists(), "Test file does not exist"
    
    # Get the file size
    size = file_size(test_file)
    
    # Test if the file size is greater than zero
    assert size > 0, f"File size should be greater than zero, but got {size}"

# Test the `main` function to check if the CSV is created correctly
def test_main():
    result_path = Path("results/benchmarks.csv")
    
    # Run the main function
    main()

    # Check if the results file was created
    assert result_path.exists(), "The result CSV file was not created"
    
    # Optionally check if it contains rows
    with open(result_path, "r") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        assert len(rows) > 0, "No rows in the results CSV"

# Additional tests for edge cases
def test_file_size_invalid_file():
    """Test the file size function with a non-existent file"""
    invalid_file = Path("data/raw/nonexistent_file.wav")
    size = file_size(invalid_file)
    assert size == 0, f"Expected file size to be 0, but got {size}"