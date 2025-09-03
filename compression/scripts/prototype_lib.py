# scripts/prototype_lib.py
from pathlib import Path

# Project folders
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
COMP_DIR = ROOT / "data" / "compressed"
COMP_DIR.mkdir(parents=True, exist_ok=True)

# Accepted input extensions (case-insensitive)
INPUT_EXTS = {
    ".wav", ".mp3", ".flac", ".ogg",
    ".m4a", ".aac", ".wma", ".opus"
}


def iter_input_files():
    """Yield input audio files from RAW_DIR."""
    for p in RAW_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in INPUT_EXTS:
            yield p


def build_ffmpeg_cmds(in_path: Path, flac_level: str = "5", opus_bitrate: str = "96k"):
    """
    Return the ffmpeg commands (as lists) to encode:
      - FLAC (lossless) -> output path
      - Opus (low-loss) -> output path
    This module only builds commands; it does not run or measure them.
    """
    flac_out = COMP_DIR / f"{in_path.stem}.flac"
    opus_out = COMP_DIR / f"{in_path.stem}.opus"

    flac_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(in_path),
        "-c:a", "flac", "-compression_level", flac_level,
        str(flac_out),
    ]

    opus_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(in_path),
        "-c:a", "libopus", "-b:a", opus_bitrate,
        str(opus_out),
    ]

    return (("flac", flac_cmd, flac_out),
            ("opus", opus_cmd, opus_out))


# Optional: allow quick manual encode (no measurements) if someone runs this file directly.
if __name__ == "__main__":
    import subprocess

    files = list(iter_input_files())
    if not files:
        print(f"No input files in: {RAW_DIR}")
    else:
        for f in files:
            for codec, cmd, outp in build_ffmpeg_cmds(f):
                subprocess.run(cmd, check=True)
                print(f"[OK] {f.name} -> {outp.name}")
        print("Done. Outputs in data/compressed/")
