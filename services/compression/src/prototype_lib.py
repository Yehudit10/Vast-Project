from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import time
from datetime import datetime
import re
from minio_client import client, BUCKET_NAME

# Supported audio formats for compression
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

RAW_PREFIX = "sound/"

def is_audio_file(filename: str) -> bool:
    """Check if file is an audio file that should be compressed."""
    if filename.lower().endswith((".flac", ".opus")):
        return False  # If it's already compressed, don't compress again
    return any(filename.lower().endswith(ext) for ext in AUDIO_EXTS)

def iter_audio_files():
    """Yield MinIO object names in RAW_PREFIX that are audio files."""
    for obj in client.list_objects(BUCKET_NAME, prefix=RAW_PREFIX, recursive=True):
        if is_audio_file(obj.object_name):
            yield obj.object_name

def parse_timestamp_from_filename(filename: str) -> datetime:
    """
    Extract timestamp from filename pattern: sensor-id_timestamp.ext
    """
    # Pattern: anything_YYYYMMDDtHHMMSSz.ext
    # Case-insensitive for 't' and 'z'
    pattern = r'_(\d{8})[tT](\d{6})[zZ]\.'
    
    match = re.search(pattern, filename)
    if not match:
        print(f"[WARN] Cannot parse timestamp from filename: {filename}")
        return None
    
    date_part = match.group(1)  # YYYYMMDD
    time_part = match.group(2)  # HHMMSS
    
    try:
        # Parse: 20240901 120000
        dt = datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
        # Assume UTC (because of 'z' suffix)
        dt = dt.replace(tzinfo=None)
        return dt
    except ValueError as e:
        print(f"[WARN] Invalid timestamp in filename {filename}: {e}")
        return None

def get_file_age_seconds(obj_name: str) -> float:
    """
    Get age of file in seconds based on timestamp in filename.
    
    Returns:
        Age in seconds, or 0 if timestamp cannot be parsed
    """
    dt = parse_timestamp_from_filename(obj_name)
    if dt is None:
        return 0
    
    now = datetime.utcnow()
    age = now - dt
    return age.total_seconds()

def is_older_than(obj_name: str, age_seconds: int) -> bool:
    """Check if file is older than specified age based on filename timestamp."""
    return get_file_age_seconds(obj_name) >= age_seconds

def build_ffmpeg_cmds(in_local_path: Path, codec="all", flac_level="5", opus_bitrate="96k"):
    """
    Return ffmpeg commands to encode a local audio file.
    Output will be a temporary file (to upload after encode).
    """
    cmds = []
    temp_dir = Path(tempfile.gettempdir())
    
    if codec in ("flac", "all"):
        flac_out = temp_dir / f"{in_local_path.stem}.flac"
        flac_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(in_local_path),
            "-c:a", "flac", "-compression_level", flac_level,
            str(flac_out)
        ]
        cmds.append(("flac", flac_cmd, flac_out))
    
    if codec in ("opus", "all"):
        opus_out = temp_dir / f"{in_local_path.stem}.opus"
        opus_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(in_local_path),
            "-c:a", "libopus", "-b:a", opus_bitrate,
            str(opus_out)
        ]
        cmds.append(("opus", opus_cmd, opus_out))
    
    return cmds

def download_raw_to_temp(obj_name: str) -> Path:
    """Download MinIO raw object to temporary file."""
    local_path = Path(tempfile.gettempdir()) / Path(obj_name).name
    client.fget_object(BUCKET_NAME, obj_name, str(local_path))
    return local_path

def replace_with_compressed(original_obj_name: str, compressed_local_path: Path):
    """
    Replace the original file in MinIO with the compressed version.
    Keeps the same path, only changes the extension.
    
    Example:
        sound/drone-01_20251102t010618z.wav -> sound/drone-01_20251102t010618z.opus
    """
    # Use PurePosixPath to always get forward slashes for MinIO paths
    from pathlib import PurePosixPath
    
    # Parse original path (use PurePosixPath for consistency)
    obj_path = PurePosixPath(original_obj_name)
    stem = obj_path.stem  # e.g., "drone-01_20251102t010618z"
    parent = obj_path.parent  # e.g., "sound"
    
    # New compressed extension
    compressed_ext = compressed_local_path.suffix  # e.g., ".opus"
    new_obj_name = str(parent / f"{stem}{compressed_ext}")
    
    # Upload compressed file to the new path
    client.fput_object(BUCKET_NAME, new_obj_name, str(compressed_local_path))
    
    # Delete original file
    client.remove_object(BUCKET_NAME, original_obj_name)
    
    return new_obj_name

def delete_object(obj_name: str):
    """Delete an object from MinIO."""
    client.remove_object(BUCKET_NAME, obj_name)

def get_compressed_variants(obj_name: str) -> list:
    """
    Given an object name, return possible compressed variants.
    
    Example:
        sound/drone-01_20251102t010618z.wav ->
        [
            "sound/drone-01_20251102t010618z.opus",
            "sound/drone-01_20251102t010618z.flac"
        ]
    """
    obj_path = PurePosixPath(obj_name)
    stem = obj_path.stem
    parent = obj_path.parent
    
    return [
        str(parent / f"{stem}.opus"),
        str(parent / f"{stem}.flac")
    ]