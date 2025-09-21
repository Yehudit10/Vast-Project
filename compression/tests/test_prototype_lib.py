from pathlib import Path
from scripts.prototype_lib import iter_input_files, build_ffmpeg_cmds

def test_iter_input_files():
    files = list(iter_input_files())
    assert len(files) > 0, "No input files found in the raw directory."
    for file in files:
        assert file.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}, \
            f"Unsupported file format: {file.suffix}"

def test_build_ffmpeg_cmds():
    input_path = Path("data/raw/cat.wav")
    flac_cmd, opus_cmd = build_ffmpeg_cmds(input_path)

    # Test FLAC command
    assert flac_cmd[1][0] == "ffmpeg", "FLAC command does not start with 'ffmpeg'"
    assert "-c:a" in flac_cmd[1], "FLAC command does not specify codec"
    assert "flac" in flac_cmd[1], "FLAC command does not contain the 'flac' codec"

    # Test Opus command
    assert opus_cmd[1][0] == "ffmpeg", "Opus command does not start with 'ffmpeg'"
    assert "-c:a" in opus_cmd[1], "Opus command does not specify codec"
    assert "libopus" in opus_cmd[1], "Opus command does not contain the 'libopus' codec"

