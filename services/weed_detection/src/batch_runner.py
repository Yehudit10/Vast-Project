# agri_baseline/src/batch_runner.py
# Max line length: 100

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

from src.pipeline.utils import (
    load_image,
    image_id_from_path,
    clamp_bbox,
)
from src.pipeline.db import (
    get_engine,
    INSERT_DET,
    INSERT_COUNT,
    INSERT_QA,
)
from src.detectors.disease_model import DiseaseDetector


class BatchRunner:
    """
    End-to-end runner:
    - Load image
    - Run disease detector
    - Normalize detections
    - Write anomalies / counts / QA to RelDB
    """

    def __init__(self, mission_id: int = 1, device_id: str = "device-1") -> None:
        self.mission_id = mission_id
        self.device_id = device_id  # TEXT FK per schema v2
        self.engine = get_engine()
        self.detector = DiseaseDetector()

    # ----------------------------
    # Public API
    # ----------------------------

    def run_folder(self, folder: Path | str) -> None:
        """
        Run pipeline on all images within a folder (non-recursive).
        Skips non-image files; prints minimal info.
        """
        folder = Path(folder)
        assert folder.exists(), f"Folder not found: {folder.resolve()}"

        image_paths = sorted(
            p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

        total = 0
        total_dets = 0
        for img_path in image_paths:
            try:
                n = self.process_image(img_path)
                total += 1
                total_dets += n
            except Exception as ex:
                # Keep output tidy; prefer structured logging in production
                print(f"[WARN] Failed on {img_path.name}: {ex}")

        # Record a small QA summary
        qa = {
            "images_processed": total,
            "detections_total": total_dets,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self.engine.begin() as conn:
            conn.execute(INSERT_QA, {"details": json.dumps(qa)})

    def process_image(self, img_path: Path | str) -> int:
        """
        Run pipeline on a single image, write detections and a simple per-image score.
        Returns number of detections written.
        """
        img_path = Path(img_path)
        img, W, H = load_image(img_path)

        image_id = image_id_from_path(img_path)
        dets = self.detector.run(img)

        print(f"{image_id}: found {len(dets)} disease spots")

        # Write detections as anomalies
        written = 0
        for d in dets:
            x, y, w, h = self._extract_bbox(d)
            x, y, w, h = clamp_bbox(int(x), int(y), int(w), int(h), W, H)
            cx = x + w / 2.0
            cy = y + h / 2.0

            area = float(getattr(d, "area", w * h))
            label = str(getattr(d, "label", "disease"))
            conf = float(getattr(d, "confidence", 1.0))

            details = {
                "image_id": image_id,
                "label": label,
                "bbox": [x, y, w, h],
                "area": area,
                "confidence": conf,
            }
            if is_dataclass(d):
                details["raw_detection"] = asdict(d)

            with self.engine.begin() as conn:
                conn.execute(
                    INSERT_DET,
                    dict(
                        mission_id=self.mission_id,
                        device_id=self.device_id,  # TEXT FK
                        ts=datetime.now(timezone.utc),
                        anomaly_type_id=1,  # seeded below
                        severity=conf,
                        details=json.dumps(details),
                        wkt_geom=f"POINT({cx} {cy})",
                    ),
                )
                written += 1

        # Per-image score → tile_stats (tile_id TEXT, geom POLYGON)
        if dets:
            anomaly_score = float(len(dets))
            poly_wkt = self._make_square_polygon_wkt(W / 2.0, H / 2.0, size=1.0)
            with self.engine.begin() as conn:
                conn.execute(
                    INSERT_COUNT,
                    dict(
                        mission_id=self.mission_id,
                        tile_id=image_id,  # TEXT per schema v2
                        anomaly_score=anomaly_score,
                        wkt_geom=poly_wkt,  # POLYGON
                    ),
                )

        return written

    # ----------------------------
    # Internals
    # ----------------------------

    @staticmethod
    def _extract_bbox(d) -> Tuple[float, float, float, float]:
        """
        Normalize bbox to (x, y, w, h). Supports:
        - d.x, d.y, d.w, d.h
        - d.bbox == (x, y, w, h)
        - d.xmin, d.ymin, d.xmax, d.ymax
        - d.left, d.top, d.width, d.height
        """
        if all(hasattr(d, a) for a in ("x", "y", "w", "h")):
            return float(d.x), float(d.y), float(d.w), float(d.h)

        if hasattr(d, "bbox"):
            bx = list(d.bbox)
            if len(bx) != 4:
                raise ValueError(f"Unexpected bbox length: {len(bx)} in {bx}")
            x, y, w, h = map(float, bx)
            return x, y, w, h

        if all(hasattr(d, a) for a in ("xmin", "ymin", "xmax", "ymax")):
            x1, y1, x2, y2 = float(d.xmin), float(d.ymin), float(d.xmax), float(d.ymax)
            return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)

        if all(hasattr(d, a) for a in ("left", "top", "width", "height")):
            return float(d.left), float(d.top), float(d.width), float(d.height)

        raise AttributeError(
            "Detection bbox fields missing. Supported: "
            "(x,y,w,h) or bbox or (xmin,ymin,xmax,ymax) or (left,top,width,height)."
        )

    @staticmethod
    def _make_square_polygon_wkt(cx: float, cy: float, size: float = 1.0) -> str:
        """
        Build a tiny square Polygon around (cx, cy) in WKT, closed ring.
        PostGIS expects Polygon for tile_stats.geom (SRID 4326).
        """
        x1, y1 = cx - size, cy - size
        x2, y2 = cx + size, cy + size
        return f"POLYGON(({x1} {y1}, {x2} {y1}, {x2} {y2}, {x1} {y2}, {x1} {y1}))"


# ------------- CLI helper -------------

def main() -> None:
    """
    Local runner:
    python -m agri_baseline.src.batch_runner --input <path-to-image-or-folder>
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run disease detection pipeline.")
    parser.add_argument("--input", type=str, required=True, help="Image file or folder")
    parser.add_argument("--mission", type=int, default=1, help="Numeric mission ID")
    parser.add_argument("--device", type=str, default="device-1", help="Text device ID")
    args = parser.parse_args()

    runner = BatchRunner(mission_id=args.mission, device_id=args.device)
    in_path = Path(args.input)
    if in_path.is_dir():
        runner.run_folder(in_path)
    else:
        runner.process_image(in_path)


if __name__ == "__main__":
    main()
