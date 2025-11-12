# # agri_baseline/src/batch_runner.py
# # Max line length: 100

# from __future__ import annotations

# import json
# from dataclasses import asdict, is_dataclass
# from datetime import datetime, timezone
# from pathlib import Path
# from typing import Tuple

# from agri_baseline.src.pipeline.utils import (
#     load_image,
#     image_id_from_path,
#     clamp_bbox,
# )
# from agri_baseline.src.pipeline.db import (
#     get_engine,
#     INSERT_DET,
#     INSERT_COUNT,
#     INSERT_QA,
# )
# from agri_baseline.src.detectors.disease_model import DiseaseDetector


# class BatchRunner:
#     """
#     End-to-end runner:
#     - Load image
#     - Run disease detector
#     - Normalize detections
#     - Write anomalies / counts / QA to RelDB
#     """

#     def __init__(self, mission_id: int = 1, device_id: str = "device-1") -> None:
#         self.mission_id = mission_id
#         self.device_id = device_id  # TEXT FK per schema v2
#         self.engine = get_engine()
#         self.detector = DiseaseDetector()

#     # ----------------------------
#     # Public API
#     # ----------------------------

#     def run_folder(self, folder: Path | str) -> None:
#         """
#         Run pipeline on all images within a folder (non-recursive).
#         Skips non-image files; prints minimal info.
#         """
#         folder = Path(folder)
#         assert folder.exists(), f"Folder not found: {folder.resolve()}"

#         image_paths = sorted(
#             p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
#         )

#         total = 0
#         total_dets = 0
#         for img_path in image_paths:
#             try:
#                 n = self.process_image(img_path)
#                 total += 1
#                 total_dets += n
#             except Exception as ex:
#                 # Keep output tidy; prefer structured logging in production
#                 print(f"[WARN] Failed on {img_path.name}: {ex}")

#         # Record a small QA summary
#         qa = {
#             "images_processed": total,
#             "detections_total": total_dets,
#             "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
#         }
#         with self.engine.begin() as conn:
#             conn.execute(INSERT_QA, {"details": json.dumps(qa)})

#     def process_image(self, img_path: Path | str) -> int:
#         """
#         Run pipeline on a single image, write detections and a simple per-image score.
#         Returns number of detections written.
#         """
#         img_path = Path(img_path)
#         img, W, H = load_image(img_path)

#         image_id = image_id_from_path(img_path)
#         dets = self.detector.run(img)

#         print(f"{image_id}: found {len(dets)} disease spots")

#         # Write detections as anomalies
#         written = 0
#         for d in dets:
#             x, y, w, h = self._extract_bbox(d)
#             x, y, w, h = clamp_bbox(int(x), int(y), int(w), int(h), W, H)
#             cx = x + w / 2.0
#             cy = y + h / 2.0

#             area = float(getattr(d, "area", w * h))
#             label = str(getattr(d, "label", "disease"))
#             conf = float(getattr(d, "confidence", 1.0))

#             details = {
#                 "image_id": image_id,
#                 "label": label,
#                 "bbox": [x, y, w, h],
#                 "area": area,
#                 "confidence": conf,
#             }
#             if is_dataclass(d):
#                 details["raw_detection"] = asdict(d)

#             with self.engine.begin() as conn:
#                 conn.execute(
#                     INSERT_DET,
#                     dict(
#                         mission_id=self.mission_id,
#                         device_id=self.device_id,  # TEXT FK
#                         ts=datetime.now(timezone.utc),
#                         anomaly_type_id=1,  # seeded below
#                         severity=conf,
#                         details=json.dumps(details),
#                         wkt_geom=f"POINT({cx} {cy})",
#                     ),
#                 )
#                 written += 1

#         # Per-image score → tile_stats (tile_id TEXT, geom POLYGON)
#         if dets:
#             anomaly_score = float(len(dets))
#             poly_wkt = self._make_square_polygon_wkt(W / 2.0, H / 2.0, size=1.0)
#             with self.engine.begin() as conn:
#                 conn.execute(
#                     INSERT_COUNT,
#                     dict(
#                         mission_id=self.mission_id,
#                         tile_id=image_id,  # TEXT per schema v2
#                         anomaly_score=anomaly_score,
#                         wkt_geom=poly_wkt,  # POLYGON
#                     ),
#                 )

#         return written

#     # ----------------------------
#     # Internals
#     # ----------------------------

#     @staticmethod
#     def _extract_bbox(d) -> Tuple[float, float, float, float]:
#         """
#         Normalize bbox to (x, y, w, h). Supports:
#         - d.x, d.y, d.w, d.h
#         - d.bbox == (x, y, w, h)
#         - d.xmin, d.ymin, d.xmax, d.ymax
#         - d.left, d.top, d.width, d.height
#         """
#         if all(hasattr(d, a) for a in ("x", "y", "w", "h")):
#             return float(d.x), float(d.y), float(d.w), float(d.h)

#         if hasattr(d, "bbox"):
#             bx = list(d.bbox)
#             if len(bx) != 4:
#                 raise ValueError(f"Unexpected bbox length: {len(bx)} in {bx}")
#             x, y, w, h = map(float, bx)
#             return x, y, w, h

#         if all(hasattr(d, a) for a in ("xmin", "ymin", "xmax", "ymax")):
#             x1, y1, x2, y2 = float(d.xmin), float(d.ymin), float(d.xmax), float(d.ymax)
#             return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)

#         if all(hasattr(d, a) for a in ("left", "top", "width", "height")):
#             return float(d.left), float(d.top), float(d.width), float(d.height)

#         raise AttributeError(
#             "Detection bbox fields missing. Supported: "
#             "(x,y,w,h) or bbox or (xmin,ymin,xmax,ymax) or (left,top,width,height)."
#         )

#     @staticmethod
#     def _make_square_polygon_wkt(cx: float, cy: float, size: float = 1.0) -> str:
#         """
#         Build a tiny square Polygon around (cx, cy) in WKT, closed ring.
#         PostGIS expects Polygon for tile_stats.geom (SRID 4326).
#         """
#         x1, y1 = cx - size, cy - size
#         x2, y2 = cx + size, cy + size
#         return f"POLYGON(({x1} {y1}, {x2} {y1}, {x2} {y2}, {x1} {y2}, {x1} {y1}))"


# # ------------- CLI helper -------------

# # def main() -> None:
# #     """
# #     Local runner:
# #     python -m agri_baseline.src.batch_runner --input <path-to-image-or-folder>
# #     """
# #     import argparse

# #     parser = argparse.ArgumentParser(description="Run disease detection pipeline.")
# #     parser.add_argument("--log-level", default="INFO", help="logging level (ignored by runner)")

# #     parser.add_argument("--input", type=str, required=True, help="Image file or folder")
# #     parser.add_argument("--mission", type=int, default=1, help="Numeric mission ID")
# #     parser.add_argument("--device", type=str, default="device-1", help="Text device ID")
# #     args = parser.parse_args()

# #     runner = BatchRunner(mission_id=args.mission, device_id=args.device)
# #     in_path = Path(args.input)
# #     if in_path.is_dir():
# #         runner.run_folder(in_path)
# #     else:
# #         runner.process_image(in_path)


# # if __name__ == "__main__":
# #     main()
# def main() -> None:
#     """
#     Local runner:
#     python -m agri_baseline.src.batch_runner --input <path-to-image-or-folder>
#     """
#     import argparse

#     parser = argparse.ArgumentParser(description="Run disease detection pipeline.")
#     parser.add_argument("--log-level", type=str, default="INFO",
#                         help="logging level (ignored by runner)")

#     parser.add_argument("--input", type=str, required=True,
#                         help="Image file or folder")
#     # קולט גם מחרוזת וגם מספר, וממיר ל-int תקני
#     parser.add_argument("--mission", type=str, default="baseline",
#                         help=f"Mission name/id ({', '.join(MISSION_ALIASES)} or numeric id)")
#     parser.add_argument("--device", type=str, default="cpu",
#                         choices=["cpu", "cuda"],
#                         help="device to use")

#     args = parser.parse_args()

#     mission_id = parse_mission(args.mission)

#     in_path = Path(args.input)
#     if not in_path.exists():
#         raise FileNotFoundError(f"input does not exist: {in_path}")
#     if in_path.is_dir():
#         # אופציונלי: הגנה על תיקייה ריקה
#         has_files = any(in_path.rglob("*"))
#         if not has_files:
#             raise RuntimeError(f"input folder is empty: {in_path}")

#     runner = BatchRunner(mission_id=mission_id, device_id=args.device)
#     if in_path.is_dir():
#         runner.run_folder(in_path)
#     else:
#         runner.process_image(in_path)

# if __name__ == "__main__":
#     main()
# agri_baseline/src/batch_runner.py
# Max line length: 100

from __future__ import annotations

from sqlalchemy import text
import os
import re
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Tuple

from agri_baseline.src.pipeline.utils import (
    load_image,
    image_id_from_path,
    clamp_bbox,
)
from agri_baseline.src.pipeline.db import (
    get_engine,
)
from agri_baseline.src.detectors.disease_model import DiseaseDetector

# -----------------------------------
# SQL
# -----------------------------------

# anomalies insert (unchanged)
INSERT_ANOMALY = text(
    """
    INSERT INTO public.anomalies
        (mission_id, device_id, ts, anomaly_type_id, severity, details, geom)
    VALUES
        (
            :mission_id,
            :device_id,
            :ts,
            :anomaly_type_id,
            :severity,
            CAST(:details AS JSONB),
            ST_SetSRID(ST_GeomFromText(:wkt_geom), 4326)
        )
    """
)

# NEW: leaf_reports insert (always written)
INSERT_LEAF_REPORT = text(
    """
    INSERT INTO public.leaf_reports
        (device_id, leaf_disease_type_id, ts, confidence, sick)
    VALUES
        (:device_id, :leaf_disease_type_id, :ts, :confidence, :sick)
    """
)

# NEW: upsert/get id for leaf_disease_types by name (case-insensitive)
UPSERT_LEAF_DISEASE_TYPE = text(
    """
    WITH ins AS (
        INSERT INTO public.leaf_disease_types (name)
        VALUES (:name)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
    )
    SELECT id FROM ins
    UNION ALL
    SELECT id FROM public.leaf_disease_types WHERE name = :name
    LIMIT 1
    """
)

INSERT_MISSION_FULL = text(
    """
    INSERT INTO public.missions (mission_id, start_time, end_time, area_geom)
    VALUES (
        :mission_id,
        :start_time,
        :end_time,
        ST_SetSRID(ST_GeomFromText(:wkt_poly), 4326)
    )
    ON CONFLICT (mission_id) DO NOTHING
    """
)


class BatchRunner:
    """
    End-to-end runner:
    - Parse device & timestamp from file name: <device>_<YYYYMMDD>T<HHMMSS>Z[ _suffix].ext
    - Run disease detector
    - ALWAYS write a row into public.leaf_reports for each detection
    - Write into public.anomalies ONLY if label is 'sick' (i.e., does NOT contain 'healthy')
    - Ensure supporting FKs exist (devices:<name>, missions: fixed 60, leaf_disease_types:<name>)

    Notes:
    * mission_id is fixed to 60 per requirement.
    * geom is the pixel-center point of the detection bbox (WKT, SRID 4326).
    """

    # Fixed mission per request
    FIXED_MISSION_ID = 60

    def __init__(self, mission_id: int | None = None, device_id: str = "device-1") -> None:
        # mission_id ignored; always use 60, but keep signature for CLI compatibility
        self.mission_id = BatchRunner.FIXED_MISSION_ID
        self.fallback_device_id = device_id  # used only if filename parsing fails
        self.engine = get_engine()
        self.detector = DiseaseDetector()

        # anomaly_types entry for LEAF_DISEASE (used only for anomalies table)
        self.leaf_anomaly_type_id = self._ensure_anomaly_type(
            code="LEAF_DISEASE", description="Leaf disease detected"
        )

    # ----------------------------
    # Public API
    # ----------------------------

    @staticmethod
    def _parse_device_and_ts_from_name(img_path: Path) -> tuple[str, datetime]:
        """
        Accepts:
          <device>_<YYYYMMDD>T<HHMMSS>Z.<ext>
          <device>_<YYYYMMDD>T<HHMMSS>Z_<suffix>.<ext>
        Returns (device_id, ts_utc). Raises ValueError if the pattern doesn't match.
        """
        stem = img_path.stem
        parts = stem.split("_")
        if len(parts) < 2:
            raise ValueError(
                f"Filename '{img_path.name}' must be '<device>_<YYYYMMDD>T<HHMMSS>Z[ _suffix].ext'"
            )
        device = parts[0]
        ts_str = parts[1]
        if not re.fullmatch(r"\d{8}T\d{6}Z", ts_str):
            raise ValueError(
                f"Filename '{img_path.name}' must include timestamp as <YYYYMMDD>T<HHMMSS>Z"
            )
        ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return device, ts

    def run_folder(self, folder: Path | str) -> None:
        """
        Run pipeline on all images within a folder (non-recursive).
        """
        folder = Path(folder)
        assert folder.exists(), f"Folder not found: {folder.resolve()}"

        image_paths = sorted(
            p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

        total, total_dets = 0, 0
        for img_path in image_paths:
            try:
                n = self.process_image(img_path)
                total += 1
                total_dets += n
            except Exception as ex:
                print(f"[WARN] Failed on {img_path.name}: {ex}")

        print(f"Processed {total} images, wrote {total_dets} detections")

    def process_image(self, img_path: Path | str) -> int:
        """
        Run pipeline on a single image and insert rows into leaf_reports (always)
        and anomalies (only if sick). Returns number of detections processed.
        """
        img_path = Path(img_path)
        # img_path = Path(img_path)

# Parse from filename (with fallback for your current crop file names)
        try:
            device_id, det_ts = self._parse_device_and_ts_from_name(img_path)
        except Exception:
            device_id = self.fallback_device_id
            # timestamp: file mtime if available, otherwise now (UTC)
            try:
                det_ts = datetime.fromtimestamp(img_path.stat().st_mtime, tz=timezone.utc)
            except Exception:
                det_ts = datetime.now(timezone.utc)

        # Parse from filename
        device_id, det_ts = self._parse_device_and_ts_from_name(img_path)

        # Ensure FKs exist
        self._ensure_device(device_id)
        self._ensure_mission_full(self.mission_id, det_ts)

        # Load image & run detector
        img, W, H = load_image(img_path)
        image_id = image_id_from_path(img_path)
        dets = self.detector.run(img)

        print(f"{image_id}: found {len(dets)} detections")

        written = 0
        for d in dets:
            x, y, w, h = self._extract_bbox(d)
            x, y, w, h = clamp_bbox(int(x), int(y), int(w), int(h), W, H)
            cx = x + w / 2.0
            cy = y + h / 2.0

            area = float(getattr(d, "area", w * h))
            label = str(getattr(d, "label", "disease"))
            conf = float(getattr(d, "confidence", 1.0))

            # Build details JSON (used only in anomalies)
            details = {
                "image_id": image_id,
                "label": label,
                "bbox": [x, y, w, h],
                "area": area,
                "confidence": conf,
                "device_id": device_id,
                "ts": det_ts.isoformat(),
            }
            minio_url = self._minio_url(img_path)
            if minio_url:
                details["minio_url"] = minio_url
            details.setdefault("crop_type", None)
            details.setdefault("disease_type", label)
            if is_dataclass(d):
                details["raw_detection"] = asdict(d)

            # Decide sick/healthy by label
            sick = not self._is_healthy_label(label)

            # Map label → disease_type_name (part after "__" if present)
            disease_type_name = self._disease_type_from_label(label)

            with self.engine.begin() as conn:
                # ensure disease type exists and get id
                leaf_type_id = self._ensure_leaf_disease_type(conn, disease_type_name)

                # 1) ALWAYS insert a leaf report
                conn.execute(
                    INSERT_LEAF_REPORT,
                    dict(
                        device_id=device_id,
                        leaf_disease_type_id=leaf_type_id,
                        ts=det_ts,
                        confidence=conf,
                        sick=sick,
                    ),
                )

                # 2) Insert anomaly ONLY if sick
                if sick:
                    conn.execute(
                        INSERT_ANOMALY,
                        dict(
                            mission_id=self.mission_id,
                            device_id=device_id,
                            ts=det_ts,
                            anomaly_type_id=self.leaf_anomaly_type_id,
                            severity=conf,
                            details=json.dumps(details),
                            wkt_geom=f"POINT({cx} {cy})",
                        ),
                    )

                written += 1

        return written

    # ----------------------------
    # Internals
    # ----------------------------

    @staticmethod
    def _is_healthy_label(label: str) -> bool:
        """Return True if label contains 'healthy' (case-insensitive)."""
        return "healthy" in label.lower()

    @staticmethod
    def _disease_type_from_label(label: str) -> str:
        """
        Extract disease type token from label. If label contains 'a__b', return 'b'; else return label.
        Keeps underscores as-is for consistency with the model outputs.
        """
        if "__" in label:
            return label.split("__", 1)[1]
        return label

    def _ensure_anomaly_type(self, code: str, description: str) -> int:
        """Return anomaly_type_id for `code`, inserting if needed (idempotent)."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT anomaly_type_id FROM public.anomaly_types WHERE code = :c"),
                {"c": code},
            ).first()
            if row:
                return int(row[0])

            row = conn.execute(
                text(
                    """
                    INSERT INTO public.anomaly_types (code, description)
                    VALUES (:c, :d)
                    ON CONFLICT (code)
                    DO UPDATE SET description = EXCLUDED.description
                    RETURNING anomaly_type_id
                    """
                ),
                {"c": code, "d": description},
            ).first()
            return int(row[0])

    def _ensure_leaf_disease_type(self, conn, name: str) -> int:
        """
        Ensure a row exists in public.leaf_disease_types for the given name and return its id.
        Uses an upsert with RETURNING to be idempotent.
        """
        row = conn.execute(UPSERT_LEAF_DISEASE_TYPE, {"name": name}).first()
        return int(row[0])

    def _ensure_device(self, device_id: str) -> None:
        """Ensure a row exists in public.devices (TEXT PK/UNIQUE)."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO public.devices (device_id)
                    VALUES (:d)
                    ON CONFLICT (device_id) DO NOTHING
                    """
                ),
                {"d": device_id},
            )

    def _ensure_mission_full(self, mission_id: int, ts: datetime) -> None:
        """
        Ensure mission row exists and matches your table shape.
        If not exists: start_time=ts, end_time=ts+1h, area=default 1x1° square near (0,0).
        """
        with self.engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM public.missions WHERE mission_id = :id"),
                {"id": mission_id},
            ).first()
            if exists:
                return
            start = ts
            end = ts + timedelta(hours=1)
            wkt_poly = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
            conn.execute(
                INSERT_MISSION_FULL,
                {
                    "mission_id": mission_id,
                    "start_time": start,
                    "end_time": end,
                    "wkt_poly": wkt_poly,
                },
            )

    @staticmethod
    def _extract_bbox(d) -> Tuple[float, float, float, float]:
        """
        Normalize bbox to (x, y, w, h). Supports multiple field layouts.
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
    def _minio_url(img_path: Path) -> str | None:
        """
        Build a MinIO object URL if MINIO_* env vars are provided.
        """
        endpoint = os.getenv("MINIO_ENDPOINT")
        bucket = os.getenv("MINIO_BUCKET")
        prefix = os.getenv("MINIO_PREFIX", "").strip("/")
        if not endpoint or not bucket:
            return None
        endpoint = endpoint.rstrip("/")
        key = f"{prefix}/{img_path.name}" if prefix else img_path.name
        return f"{endpoint}/{bucket}/{key}"


# ------------- CLI helper -------------

def main() -> None:
    """
    Local runner:
    python -m agri_baseline.src.batch_runner --input <path-to-image-or-folder>
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Run disease detection pipeline: leaf_reports (always), anomalies (sick only)."
    )
    parser.add_argument("--input", type=str, required=True, help="Image file or folder")
    parser.add_argument("--mission", type=int, default=60, help="Ignored; always fixed to 60")
    parser.add_argument("--device", type=str, default="device-1", help="Fallback device (unused)")
    args = parser.parse_args()

    runner = BatchRunner(mission_id=args.mission, device_id=args.device)
    in_path = Path(args.input)
    if in_path.is_dir():
        runner.run_folder(in_path)
    else:
        runner.process_image(in_path)


if __name__ == "__main__":
    main()
