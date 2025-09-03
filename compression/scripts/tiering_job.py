from pathlib import Path
import time
import argparse
import subprocess
from prototype_lib import ROOT, RAW_DIR, COMP_DIR, iter_input_files, build_ffmpeg_cmds

# Defaults
DEFAULT_RAW_MAX_AGE_HOURS = 24
DEFAULT_COMP_MAX_AGE_DAYS = 90
DEFAULT_LONG_TERM_CODEC = "opus"


def get_age_seconds(p: Path, mode: str) -> float:
    """
    Return file age in seconds based on chosen timestamp field.
    mode:
      'mtime' -> last modification time
      'ctime' -> creation time (Windows) / inode change time (Unix)
    """
    st = p.stat()
    ts = getattr(st, "st_ctime", st.st_mtime) if mode == "ctime" else st.st_mtime
    return time.time() - ts


def is_older_than(p: Path, age_seconds: int, mode: str) -> bool:
    """Check if file age (by mode) is >= threshold."""
    return get_age_seconds(p, mode) >= age_seconds


def encode(in_path: Path, codec: str) -> Path:
    """Encode a single RAW file to the chosen codec. Returns output path."""
    cmds = build_ffmpeg_cmds(in_path)
    target = next((t for t in cmds if t[0] == codec), None)
    if target is None:
        raise ValueError(f"Unsupported codec: {codec}")

    _, cmd, out_path = target
    rc = subprocess.call(cmd)
    if rc != 0:
        raise RuntimeError(f"Encode failed: {in_path.name} -> {codec}")
    return out_path


def cleanup_compressed(max_age_days: int, dry_run: bool) -> int:
    """
    Delete compressed files older than <max_age_days>.
    Returns count deleted.
    """
    if max_age_days <= 0:
        return 0

    cutoff_sec = max_age_days * 86400
    now = time.time()
    deleted = 0

    for p in COMP_DIR.iterdir():
        if p.is_file() and (now - p.stat().st_mtime) >= cutoff_sec:
            if dry_run:
                print(f"[DRY] would delete compressed: {p.name}")
            else:
                try:
                    p.unlink()
                    deleted += 1
                    print(f"[DEL] compressed old: {p.name}")
                except Exception as e:
                    print(f"[WARN] failed to delete {p.name}: {e}")
    return deleted


def main():
    ap = argparse.ArgumentParser(
        description="Two-tier storage job: move+compress RAW, retain COMPRESSED."
    )
    ap.add_argument("--raw-max-age-hours", type=int, default=None,
                    help="Move+compress RAW files older than N hours.")
    ap.add_argument("--raw-max-age-minutes", type=int, default=None,
                    help="Move+compress RAW files older than N minutes.")
    ap.add_argument("--age-mode", choices=["mtime", "ctime"], default="mtime",
                    help="Which timestamp to use: mtime (default) or ctime (Windows creation time).")
    ap.add_argument("--codec", choices=["opus", "flac"], default=DEFAULT_LONG_TERM_CODEC,
                    help='Long-term codec ("opus" or "flac").')
    ap.add_argument("--delete-raw-after", action="store_true",
                    help="Delete RAW after successful encode.")
    ap.add_argument("--compressed-max-age-days", type=int, default=DEFAULT_COMP_MAX_AGE_DAYS,
                    help="Delete compressed files older than N days (0 = disable).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Plan only: print actions without encoding/deleting.")

    args = ap.parse_args()

    # Decide raw age threshold in seconds
    if args.raw_max_age_minutes is not None:
        raw_age_seconds = args.raw_max_age_minutes * 60
    elif args.raw_max_age_hours is not None:
        raw_age_seconds = args.raw_max_age_hours * 3600
    else:
        raw_age_seconds = DEFAULT_RAW_MAX_AGE_HOURS * 3600

    processed, raw_deleted = 0, 0

    # 1) Move+compress RAW files
    for f in iter_input_files():
        if is_older_than(f, raw_age_seconds, args.age_mode):
            if args.dry_run:
                print(f"[DRY] would encode {f.name} -> {args.codec.upper()} "
                      f"and delete RAW: {bool(args.delete_raw_after)}")
                processed += 1
                continue

            try:
                outp = encode(f, args.codec)
                print(f"[OK] {f.name} -> {outp.name} ({args.codec})")
                processed += 1

                if args.delete_raw_after and outp.exists():
                    try:
                        f.unlink()
                        raw_deleted += 1
                        print(f"[DEL] raw: {f.name}")
                    except Exception as e:
                        print(f"[WARN] failed to delete raw {f.name}: {e}")

            except Exception as e:
                print(f"[FAIL] {f.name}: {e}")

    # 2) Retention on compressed
    comp_deleted = cleanup_compressed(args.compressed_max_age_days, args.dry_run)

    # Summary
    print(f"Done. Processed={processed}, Raw deletions={raw_deleted}, "
          f"Compressed deletions={comp_deleted}, Mode={args.age_mode}, "
          f"Threshold={raw_age_seconds}s")


if __name__ == "__main__":
    main()
