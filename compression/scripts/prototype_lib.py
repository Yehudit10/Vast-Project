from pathlib import Path
import subprocess
import tempfile
import time
from minio_client import client, BUCKET_NAME

INPUT_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

RAW_PREFIX = "raw/"
COMP_PREFIX = "compressed/"

def iter_input_files():
    """Yield MinIO object names in RAW_PREFIX with accepted extensions."""
    for obj in client.list_objects(BUCKET_NAME, prefix=RAW_PREFIX, recursive=True):
        if any(obj.object_name.lower().endswith(ext) for ext in INPUT_EXTS):
            yield obj.object_name

def build_ffmpeg_cmds(in_local_path: Path, codec="all", flac_level="5", opus_bitrate="96k"):
    """
    Return ffmpeg commands to encode a local file.
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

def upload_compressed(local_path: Path):
    """Upload encoded file to MinIO compressed folder."""
    target_name = f"{COMP_PREFIX}{int(time.time())}_{local_path.name}"
    client.fput_object(BUCKET_NAME, target_name, str(local_path))
    return target_name

def delete_object(obj_name: str):
    client.remove_object(BUCKET_NAME, obj_name)