from pathlib import Path
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from scripts.prototype_lib import iter_input_files, build_ffmpeg_cmds, INPUT_EXTS, RAW_DIR, COMP_DIR

# Test for iter_input_files function to ensure it retrieves all valid audio files.
def test_iter_input_files():
    files = list(iter_input_files())  # Get list of files returned by the function
    assert len(files) > 0, "No input files found in the raw directory."  # Ensure at least one file is found
    for file in files:
        assert file.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}, \
            f"Unsupported file format: {file.suffix}"  # Ensure file has a valid audio extension

# Test for build_ffmpeg_cmds function to validate the generated ffmpeg commands.
def test_build_ffmpeg_cmds():
    input_path = Path("data/raw/cat.wav")  # Sample audio file
    flac_cmd, opus_cmd = build_ffmpeg_cmds(input_path)  # Generate ffmpeg commands for FLAC and Opus

    # Test FLAC command
    assert flac_cmd[1][0] == "ffmpeg", "FLAC command does not start with 'ffmpeg'"  # Check if the command starts correctly
    assert "-c:a" in flac_cmd[1], "FLAC command does not specify codec"  # Check if codec is specified
    assert "flac" in flac_cmd[1], "FLAC command does not contain the 'flac' codec"  # Ensure FLAC codec is used

    # Test Opus command
    assert opus_cmd[1][0] == "ffmpeg", "Opus command does not start with 'ffmpeg'"  # Check if the command starts correctly
    assert "-c:a" in opus_cmd[1], "Opus command does not specify codec"  # Check if codec is specified
    assert "libopus" in opus_cmd[1], "Opus command does not contain the 'libopus' codec"  # Ensure Opus codec is used

# Test when the directory is empty, ensuring no files are returned.
def test_iter_input_files_empty_directory():
    """Test case where no input files are available."""
    empty_dir = Path("data/empty")  # Path to an empty directory
    # Ensure the directory is empty
    if not empty_dir.exists():
        empty_dir.mkdir(parents=True)
    
    # Simulate the empty directory scenario
    assert len(list(iter_input_files("data/empty"))) == 0, "The directory is empty, but files were found."

# Test to ensure that invalid file extensions are not returned.
def test_iter_input_files_invalid_extension():
    """Test case where files with invalid extensions are present."""
    invalid_file = Path("data/raw/invalid_file.txt")  # Invalid file extension
    invalid_file.touch()  # Create the invalid file
    
    files = list(iter_input_files())  # Get files from the directory
    assert invalid_file not in files, f"Unexpected file with invalid extension: {invalid_file}"  # Assert invalid file is not included

# Additional tests for improving code coverage

# Test with a custom directory to ensure files are handled properly.
def test_iter_input_files_with_custom_directory():
    """Test with a custom directory"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a valid audio file
        audio_file = temp_path / "test.wav"
        audio_file.touch()
        
        files = list(iter_input_files(temp_dir))  # Get files from the custom directory
        assert len(files) == 1  # Ensure only one file is found
        assert files[0].name == "test.wav"  # Verify the file name

# Test case for non-existent directory, should raise an error.
def test_iter_input_files_nonexistent_directory():
    """Test with a non-existent directory"""
    nonexistent_dir = "/path/that/does/not/exist"  # Path that doesn't exist
    
    with pytest.raises(ValueError, match="does not exist"):  # Expecting a ValueError
        list(iter_input_files(nonexistent_dir))  # Try accessing the non-existent directory

# Test case to ensure case-insensitive handling of file extensions.
def test_iter_input_files_case_insensitive():
    """Test that the function handles extensions with uppercase letters"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create files with both lowercase and uppercase extensions
        files_to_create = ["test.WAV", "audio.MP3", "music.flac", "sound.OGG"]
        
        for filename in files_to_create:
            (temp_path / filename).touch()
        
        found_files = list(iter_input_files(temp_dir))  # Get files from the directory
        assert len(found_files) == 4  # Ensure 4 files are found
        
        # Verify that all expected files were found
        found_names = [f.name for f in found_files]
        for expected_file in files_to_create:
            assert expected_file in found_names

# Test to ensure subdirectories are ignored when iterating files.
def test_iter_input_files_with_subdirectories():
    """Test that the function ignores subdirectories"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a file in the main directory
        audio_file = temp_path / "main.wav"
        audio_file.touch()
        
        # Create a subdirectory with a file inside
        sub_dir = temp_path / "subdirectory"
        sub_dir.mkdir()
        sub_audio = sub_dir / "sub.wav"
        sub_audio.touch()
        
        files = list(iter_input_files(temp_dir))  # Get files from the main directory
        # Should only find the file in the main directory
        assert len(files) == 1
        assert files[0].name == "main.wav"

# Test build_ffmpeg_cmds with custom parameters to ensure command customization works.
def test_build_ffmpeg_cmds_custom_parameters():
    """Test build_ffmpeg_cmds with custom parameters"""
    input_path = Path("test_audio.mp3")  # Sample audio file
    
    flac_cmd, opus_cmd = build_ffmpeg_cmds(input_path, flac_level="8", opus_bitrate="128k")  # Custom parameters
    
    # Check if custom FLAC compression level is included
    assert "8" in flac_cmd[1], "Custom FLAC level not found in command"
    
    # Check if custom Opus bitrate is included
    assert "128k" in opus_cmd[1], "Custom Opus bitrate not found in command"

# Test if the output paths for FLAC and Opus are built correctly.
def test_build_ffmpeg_cmds_output_paths():
    """Test that output paths are built correctly"""
    input_path = Path("my_audio_file.wav")  # Sample audio file
    
    flac_cmd, opus_cmd = build_ffmpeg_cmds(input_path)  # Generate ffmpeg commands
    
    # Check if FLAC output path is correct
    expected_flac_path = str(COMP_DIR / "my_audio_file.flac")
    assert expected_flac_path in flac_cmd[1], "FLAC output path is incorrect"
    
    # Check if Opus output path is correct
    expected_opus_path = str(COMP_DIR / "my_audio_file.opus")
    assert expected_opus_path in opus_cmd[1], "Opus output path is incorrect"

# Test to validate the structure of the return values from build_ffmpeg_cmds.
def test_build_ffmpeg_cmds_return_structure():
    """Test that the return structure is valid"""
    input_path = Path("test.wav")  # Sample audio file
    
    flac_result, opus_result = build_ffmpeg_cmds(input_path)  # Generate ffmpeg commands
    
    # Ensure each result is a tuple of 3 elements
    assert len(flac_result) == 3, "FLAC result should have 3 elements"
    assert len(opus_result) == 3, "Opus result should have 3 elements"
    
    # Check if the first element is the codec name
    assert flac_result[0] == "flac", "First element should be codec name"
    assert opus_result[0] == "opus", "First element should be codec name"
    
    # Ensure the third element is a Path object
    assert isinstance(flac_result[2], Path), "Third element should be Path object"
    assert isinstance(opus_result[2], Path), "Third element should be Path object"

# Test to ensure that the INPUT_EXTS constant matches the expected set of extensions.
def test_input_exts_constant():
    """Test that the INPUT_EXTS constant matches the expected formats"""
    expected_formats = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}
    assert INPUT_EXTS == expected_formats, "INPUT_EXTS constant doesn't match expected formats"

# Test to validate that only valid audio files are returned from a directory containing mixed files.
def test_iter_input_files_mixed_files():
    """Test with a mix of valid and invalid files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create valid audio files
        valid_files = ["audio1.wav", "music.mp3", "sound.flac"]
        for filename in valid_files:
            (temp_path / filename).touch()
        
        # Create invalid files
        invalid_files = ["document.txt", "image.jpg", "video.mp4"]
        for filename in invalid_files:
            (temp_path / filename).touch()
        
        found_files = list(iter_input_files(temp_dir))  # Get files from the directory
        
        # Should find only the valid files
        assert len(found_files) == 3
        found_names = [f.name for f in found_files]
        
        for valid_file in valid_files:
            assert valid_file in found_names
        
        for invalid_file in invalid_files:
            assert invalid_file not in found_names

def test_build_ffmpeg_cmds_all_parameters():
    """Test all parameters in the ffmpeg command."""
    input_path = Path("test_file.wav")
    
    # Generate FFmpeg commands for FLAC and Opus with specific parameters
    flac_result, opus_result = build_ffmpeg_cmds(input_path, flac_level="3", opus_bitrate="64k")
    
    flac_cmd = flac_result[1]
    opus_cmd = opus_result[1]
    
    # Detailed tests for FLAC command
    assert "-y" in flac_cmd, "Missing -y parameter in FLAC command"
    assert "-hide_banner" in flac_cmd, "Missing -hide_banner parameter in FLAC command"
    assert "-loglevel" in flac_cmd, "Missing -loglevel parameter in FLAC command"
    assert "error" in flac_cmd, "Missing error loglevel in FLAC command"
    assert "-i" in flac_cmd, "Missing -i parameter in FLAC command"
    assert "-compression_level" in flac_cmd, "Missing compression_level in FLAC command"
    assert "3" in flac_cmd, "Missing custom compression level in FLAC command"
    
    # Detailed tests for Opus command
    assert "-y" in opus_cmd, "Missing -y parameter in Opus command"
    assert "-hide_banner" in opus_cmd, "Missing -hide_banner parameter in Opus command"
    assert "-loglevel" in opus_cmd, "Missing -loglevel parameter in Opus command"
    assert "error" in opus_cmd, "Missing error loglevel in Opus command"
    assert "-i" in opus_cmd, "Missing -i parameter in Opus command"
    assert "-b:a" in opus_cmd, "Missing -b:a parameter in Opus command"
    assert "64k" in opus_cmd, "Missing custom bitrate in Opus command"

def test_iter_input_files_all_supported_formats():
    """Test that all supported formats are correctly identified."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a file for each supported format
        supported_formats = [".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"]
        
        for ext in supported_formats:
            test_file = temp_path / f"test{ext}"
            test_file.touch()
        
        found_files = list(iter_input_files(temp_dir))
        assert len(found_files) == len(supported_formats), f"Expected {len(supported_formats)} files, found {len(found_files)}"
        
        # Ensure all formats were found
        found_extensions = {f.suffix.lower() for f in found_files}
        expected_extensions = set(supported_formats)
        assert found_extensions == expected_extensions, "Not all supported formats were found"

def test_build_ffmpeg_cmds_default_parameters():
    """Test that default parameters work correctly."""
    input_path = Path("default_test.mp3")
    
    flac_result, opus_result = build_ffmpeg_cmds(input_path)
    
    # Check default parameters
    assert "5" in flac_result[1], "Default FLAC compression level (5) not found"
    assert "96k" in opus_result[1], "Default Opus bitrate (96k) not found"

def test_path_handling_with_special_characters():
    """Test handling of file names with special characters."""
    special_names = [
        "file with spaces.wav",
        "file-with-dashes.mp3", 
        "file_with_underscores.flac",
        "file.with.dots.ogg"
    ]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for name in special_names:
            (temp_path / name).touch()
        
        found_files = list(iter_input_files(temp_dir))
        assert len(found_files) == len(special_names)
        
        found_names = [f.name for f in found_files]
        for expected_name in special_names:
            assert expected_name in found_names

def test_comp_dir_creation_in_build_ffmpeg_cmds():
    """Test that the output paths point to the correct compression directory."""
    input_path = Path("some_audio.wav")
    
    flac_result, opus_result = build_ffmpeg_cmds(input_path)
    
    flac_output_path = flac_result[2]
    opus_output_path = opus_result[2]
    
    # Check that the paths point to COMP_DIR
    assert flac_output_path.parent == COMP_DIR, "FLAC output path parent is not COMP_DIR"
    assert opus_output_path.parent == COMP_DIR, "Opus output path parent is not COMP_DIR"
    
    # Check that the extensions are correct
    assert flac_output_path.suffix == ".flac", "FLAC output doesn't have .flac extension"
    assert opus_output_path.suffix == ".opus", "Opus output doesn't have .opus extension"

def test_iter_input_files_path_object_handling():
    """Test correct handling of Path objects."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        audio_file = temp_path / "path_test.wav"
        audio_file.touch()
        
        # Test with string
        files_str = list(iter_input_files(temp_dir))
        
        # Test with Path object
        files_path = list(iter_input_files(temp_path))
        
        assert len(files_str) == len(files_path) == 1
        assert files_str[0].name == files_path[0].name == "path_test.wav"

def test_build_ffmpeg_cmds_extreme_parameters():
    """Test with extreme parameters."""
    input_path = Path("extreme_test.wav")
    
    # Extreme parameters
    flac_result, opus_result = build_ffmpeg_cmds(
        input_path, 
        flac_level="12",  # Maximum
        opus_bitrate="512k"  # Very high
    )
    
    assert "12" in flac_result[1], "Extreme FLAC level not found"
    assert "512k" in opus_result[1], "Extreme Opus bitrate not found"

def test_constants_and_globals():
    """Test constants and global variables."""
    from scripts.prototype_lib import ROOT, RAW_DIR, COMP_DIR, INPUT_EXTS
    
    # Check that all constants are Path objects or sets
    assert isinstance(ROOT, Path), "ROOT should be a Path object"
    assert isinstance(RAW_DIR, Path), "RAW_DIR should be a Path object"
    assert isinstance(COMP_DIR, Path), "COMP_DIR should be a Path object"
    assert isinstance(INPUT_EXTS, set), "INPUT_EXTS should be a set"
    
    # Check that the paths are logical
    assert RAW_DIR.name == "raw", "RAW_DIR should end with 'raw'"
    assert COMP_DIR.name == "compressed", "COMP_DIR should end with 'compressed'"
    
    # Check that all extensions in INPUT_EXTS start with a dot
    for ext in INPUT_EXTS:
        assert ext.startswith("."), f"Extension {ext} should start with dot"
        assert ext.islower(), f"Extension {ext} should be lowercase"

def test_iter_input_files_file_vs_directory():
    """Test that the function ignores directories that look like audio files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a valid file
        valid_file = temp_path / "audio.wav"
        valid_file.touch()
        
        # Create a directory with a name that looks like an audio file
        fake_audio_dir = temp_path / "fake_audio.mp3"
        fake_audio_dir.mkdir()
        
        files = list(iter_input_files(temp_dir))
        
        # Should find only the valid file
        assert len(files) == 1
        assert files[0].name == "audio.wav"

def test_build_ffmpeg_cmds_file_stem_handling():
    """Test that handling of file stems works correctly."""
    test_cases = [
        ("simple.wav", "simple"),
        ("file.with.dots.mp3", "file.with.dots"),
        ("no_extension", "no_extension"),
        ("multiple.dots.in.name.flac", "multiple.dots.in.name")
    ]
    
    for input_name, expected_stem in test_cases:
        input_path = Path(input_name)
        flac_result, opus_result = build_ffmpeg_cmds(input_path)
        
        flac_output = flac_result[2]
        opus_output = opus_result[2]
        
        assert flac_output.stem == expected_stem, f"FLAC stem mismatch for {input_name}"
        assert opus_output.stem == expected_stem, f"Opus stem mismatch for {input_name}"

def test_iter_input_files_empty_files():
    """Test with empty files - should still be considered valid."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create empty files with valid extensions
        empty_files = ["empty1.wav", "empty2.mp3", "empty3.flac"]
        
        for filename in empty_files:
            (temp_path / filename).touch()
        
        files = list(iter_input_files(temp_dir))
        
        assert len(files) == len(empty_files)
        found_names = [f.name for f in files]
        
        for expected_file in empty_files:
            assert expected_file in found_names

def test_iter_input_files_hidden_files():
    """Test with hidden files (starting with a dot)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create regular files
        normal_file = temp_path / "normal.wav"
        normal_file.touch()
        
        # Create a hidden file
        hidden_file = temp_path / ".hidden.mp3"
        hidden_file.touch()
        
        files = list(iter_input_files(temp_dir))
        found_names = [f.name for f in files]
        
        # Hidden files should be found if they have a valid extension
        assert "normal.wav" in found_names
        assert ".hidden.mp3" in found_names
        assert len(files) == 2

def test_build_ffmpeg_cmds_command_order():
    """Test that the order of parameters in the ffmpeg command is correct."""
    input_path = Path("test.wav")
    flac_result, opus_result = build_ffmpeg_cmds(input_path)
    
    flac_cmd = flac_result[1]
    opus_cmd = opus_result[1]
    
    # Check parameter order for FLAC
    assert flac_cmd[0] == "ffmpeg"
    assert flac_cmd[1] == "-y"
    assert flac_cmd[2] == "-hide_banner"
    assert "-i" in flac_cmd
    assert "-c:a" in flac_cmd
    
    # Check parameter order for Opus
    assert opus_cmd[0] == "ffmpeg"
    assert opus_cmd[1] == "-y"
    assert opus_cmd[2] == "-hide_banner"
    assert "-i" in opus_cmd
    assert "-c:a" in opus_cmd

def test_input_path_as_string_in_build_ffmpeg_cmds():
    """Test that the function handles string paths correctly."""
    input_path = Path("string_path.wav")
    
    flac_result, opus_result = build_ffmpeg_cmds(input_path)
    
    # The path should appear as a string in the command
    flac_cmd = flac_result[1]
    opus_cmd = opus_result[1]
    
    input_str = str(input_path)
    assert input_str in flac_cmd, "Input path not found as string in FLAC command"
    assert input_str in opus_cmd, "Input path not found as string in Opus command"

def test_comp_dir_mkdir_functionality():
    """Test that COMP_DIR is created correctly."""
    from scripts.prototype_lib import COMP_DIR
    
    # COMP_DIR should be defined and accessible
    assert COMP_DIR is not None
    assert isinstance(COMP_DIR, Path)
    
    # Check that the path is logical
    assert "compressed" in str(COMP_DIR)

def test_root_path_calculation():
    """Test that ROOT path calculation is correct."""
    from scripts.prototype_lib import ROOT
    
    # ROOT should be a Path object
    assert isinstance(ROOT, Path)
    
    # ROOT should be an absolute path
    assert ROOT.is_absolute()

def test_various_audio_extensions_case_combinations():
    """Test different combinations of uppercase and lowercase audio extensions."""
    test_extensions = [
        ".wav", ".WAV", ".Wav", ".wAv",
        ".mp3", ".MP3", ".Mp3", ".mP3",
        ".flac", ".FLAC", ".Flac", ".fLaC"
    ]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for i, ext in enumerate(test_extensions):
            test_file = temp_path / f"test{i}{ext}"
            test_file.touch()
        
        files = list(iter_input_files(temp_dir))
        
        # All files should be found (case insensitive)
        assert len(files) == len(test_extensions)

def test_build_ffmpeg_cmds_output_file_extensions():
    """Detailed test of output file extensions."""
    test_inputs = [
        ("audio.wav", ".flac", ".opus"),
        ("music.mp3", ".flac", ".opus"), 
        ("sound.m4a", ".flac", ".opus")
    ]
    
    for input_name, expected_flac_ext, expected_opus_ext in test_inputs:
        input_path = Path(input_name)
        flac_result, opus_result = build_ffmpeg_cmds(input_path)
        
        flac_output = flac_result[2]
        opus_output = opus_result[2]
        
        assert flac_output.suffix == expected_flac_ext, f"Wrong FLAC extension for {input_name}"
        assert opus_output.suffix == expected_opus_ext, f"Wrong Opus extension for {input_name}"
