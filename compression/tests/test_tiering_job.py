from pathlib import Path
from scripts.tiering_job import is_older_than, encode, cleanup_compressed

def test_is_older_than():
    file = Path("data/raw/cat.wav")
    assert is_older_than(file, 3600, "mtime"), "File should be older than 1 hour"

def test_encode():
    input_path = Path("data/raw/cat.wav")
    output_path = encode(input_path, "flac")
    assert output_path.exists(), "Encoded file not created"
    assert output_path.suffix == ".flac", "File not encoded in FLAC format"

def test_cleanup_compressed():
    deleted = cleanup_compressed(30, dry_run=True)  # Dry run, should not delete anything
    assert deleted == 0, "Should not delete any files during dry run"
