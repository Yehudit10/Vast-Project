# make_tiles.py  —  run this from the OSGeo4W Shell
import os
import sys
import subprocess
from datetime import datetime

try:
    from osgeo import gdal
except ImportError:
    print("ERROR: Could not import GDAL. Please run this script from the OSGeo4W Shell.")
    sys.exit(1)

# ==== CONFIG ====
INPUT_TIF = r".\field_x10.tif"
OUTPUT_DIR = r".\tiles"
ZOOM_RANGE = "10-18"                # change if needed
RESAMPLING = "bilinear"             # 'near'/'bilinear'/'cubic'/...
TARGET_SRS = "EPSG:3857"            # Web Mercator for XYZ
TILESIZE_PREFERRED = 512            # try 512 first; fall back to 256
NUM_THREADS = "ALL_CPUS"            # speed-up for warp
# ===============

def run_cmd(args):
    # show nice, quoted command for readability
    print(">>", " ".join(f'"{a}"' if " " in a else a for a in args))
    cp = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(cp.stdout)
    cp.check_returncode()
    return cp

def warp_to_3857(src_path, dst_path):
    print(f"[{datetime.now():%H:%M:%S}] Reprojecting to {TARGET_SRS} ...")
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    warp_opts = gdal.WarpOptions(
        dstSRS=TARGET_SRS,
        resampleAlg=RESAMPLING,
        multithread=True,
        warpOptions=[f"NUM_THREADS={NUM_THREADS}"]
    )
    ds = gdal.Warp(dst_path, src_path, options=warp_opts)
    if ds is None:
        raise RuntimeError("gdal.Warp failed")
    ds = None
    print(f"[{datetime.now():%H:%M:%S}] Reprojected -> {dst_path}")

def gdal2tiles_xyz(src_path, out_dir, zoom_range, tilesize=None):
    """
    Call GDAL's tiler via module execution to avoid Win32 exec issues:
    python -m osgeo_utils.gdal2tiles --xyz ...
    """
    cmd = [sys.executable, "-m", "osgeo_utils.gdal2tiles", "--xyz",
           "-z", zoom_range, "-r", RESAMPLING, "-w", "none"]
    if tilesize:
        cmd += ["--tilesize", str(tilesize)]
    cmd += [src_path, out_dir]
    return run_cmd(cmd)

def main():
    if not os.path.isfile(INPUT_TIF):
        print(f"ERROR: Input not found: {INPUT_TIF}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    temp_3857 = os.path.join(os.path.dirname(OUTPUT_DIR), "_tmp_3857.tif")

    # 1) Reproject to Web Mercator
    warp_to_3857(INPUT_TIF, temp_3857)

    # 2) Generate tiles (try 512; fallback to 256 if unsupported)
    chosen_tile_size = TILESIZE_PREFERRED
    try:
        print(f"[{datetime.now():%H:%M:%S}] Generating tiles (XYZ) at {TILESIZE_PREFERRED}×{TILESIZE_PREFERRED} ...")
        gdal2tiles_xyz(temp_3857, OUTPUT_DIR, ZOOM_RANGE, tilesize=TILESIZE_PREFERRED)
    except subprocess.CalledProcessError as e:
        print("WARN: Your GDAL may not support --tilesize. Falling back to 256×256 ...")
        chosen_tile_size = 256
        # rerun without --tilesize (defaults to 256)
        gdal2tiles_xyz(temp_3857, OUTPUT_DIR, ZOOM_RANGE, tilesize=None)

    print(f"[{datetime.now():%H:%M:%S}] DONE. Tiles at: {OUTPUT_DIR}")
    print(f"Tile size used: {chosen_tile_size} × {chosen_tile_size}")
    print("Scheme: XYZ (no Y flip).")

    # Quick sanity listing
    try:
        zs = sorted(int(d) for d in os.listdir(OUTPUT_DIR) if d.isdigit())
        if zs:
            top = zs[-1]
            x_root = os.path.join(OUTPUT_DIR, str(top))
            xs = [d for d in os.listdir(x_root) if d.isdigit()]
            print(f"Highest zoom: z={top}, sample X: {xs[:5]}")
            if xs:
                y_root = os.path.join(x_root, xs[0])
                ys = [f for f in os.listdir(y_root) if f.lower().endswith(('.png','.jpg','.jpeg'))]
                print(f"Sample files at z={top}/{xs[0]}: {ys[:5]}")
        else:
            print("No zoom folders found—check the logs above.")
    except Exception as e:
        print("Sanity-list failed:", e)

if __name__ == "__main__":
    main()
