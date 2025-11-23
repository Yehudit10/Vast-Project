from __future__ import annotations
import time, logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from agguard.core.roi import Roi
from agguard.core.motion import MotionGate
from agguard.specialists.clients.megadetector import MegaDetectorClient
from agguard.core.tracker import BoxMOTWrapper
from agguard.specialists.dispatch import ClassDispatch
from agguard.core.events.aggregator import IncidentAggregator
from agguard.core.events.models import Rule

log = logging.getLogger(__name__)



class FlinkPipelineManager:
    """
    Stateful per-camera pipeline for Flink.
    Does NOT talk to DB or S3; emits events to be sent to Kafka.
    """
    def __init__(self, cfg: Dict[str, Any],s3, rules: List[Rule]):
        self.cfg = cfg
        self.rules = rules
        self.det = MegaDetectorClient(cfg.get("detector", {}))
        self.router = ClassDispatch(cfg.get("specialists", []))
        self.change_thresh = float(cfg.get("change_thresh", 0.02))
        self._states: Dict[str, Dict[str, Any]] = {}
        #added
        self.s3=s3


    def _get_or_create(self, camera_id: str, frame_shape) -> Dict[str, Any]:
        if camera_id in self._states:
            return self._states[camera_id]
        h, w = frame_shape[:2]
        roi_poly = Roi.from_normalized([(0,0),(1,0),(1,1),(0,1)], (w,h))
        gate = MotionGate(roi_poly)
        trk = BoxMOTWrapper()

        video_bucket = self.cfg.get("video_bucket", "imagery")
        media_base = self.cfg.get("media_base", "http://media-proxy:8080")

        aggregator = IncidentAggregator(
            rules=self.rules,
            camera_id=camera_id,
            s3=self.s3,                     # ✅ your S3 client (already passed into manager)
            video_bucket=video_bucket,      # ✅ bucket for uploads
            video_prefix="security/incidents",
            media_base=media_base,          # ✅ Base URL for HLS/VOD
        )

        self._states[camera_id] = {
            "roi": roi_poly, "gate": gate, "trk": trk,
            "aggregator": aggregator, "fps_ema": None, "prev": time.perf_counter()
        }
        return self._states[camera_id]

    def process(self, camera_id: str, ts_sec: float,
                frame_idx: Optional[int], frame_bgr: np.ndarray) -> Optional[Dict[str,Any]]:
        
        # Start timing for the whole frame
        start_time = time.perf_counter()
        log.info("[FlinkPipeline] ▶ START frame_idx=%s cam=%s", frame_idx, camera_id)

        p = self._get_or_create(camera_id, frame_bgr.shape)
        gate, trk, aggregator = p["gate"], p["trk"], p["aggregator"]

        # ---- 1. Motion gate check ----
        reading = gate.update(frame_bgr)
        if reading.score < self.change_thresh:
            log.debug("[FlinkPipeline] frame_idx=%s cam=%s — skipped (static frame, score=%.4f)",
                    frame_idx, camera_id, reading.score)
            return None

        # ---- 2. Detection ----
        t_det = time.perf_counter()
        dets = self.det.detect(frame_bgr)
        log.debug("[FlinkPipeline] frame_idx=%s cam=%s — detected %d objects in %.3fs",
                frame_idx, camera_id, len(dets), time.perf_counter() - t_det)

        # ---- 3. Tracking ----
        t_trk = time.perf_counter()
        tracks = trk.update(dets, frame_bgr)
        # tracks = trk.update([(d.cls, d.conf, d.bbox) for d in dets], frame_bgr)
        log.debug("[FlinkPipeline] frame_idx=%s cam=%s — tracker updated %d tracks in %.3fs",
                frame_idx, camera_id, len(tracks), time.perf_counter() - t_trk)

        # ---- 4. Specialists (dispatchers) ----
        t_spec = time.perf_counter()
        outs = self.router.run(frame_bgr, dets)
        log.debug("[FlinkPipeline] frame_idx=%s cam=%s — all specialists done in %.3fs, outputs=%s",
                frame_idx, camera_id, time.perf_counter() - t_spec,
                {k: len(v) for k, v in outs.items()})

        # ---- 5. Aggregation ----
        t_agg = time.perf_counter()
        evt = aggregator.update(frame_idx, ts_sec, frame_bgr, tracks, outs)
        log.debug("[FlinkPipeline] frame_idx=%s cam=%s — aggregator done in %.3fs",
                frame_idx, camera_id, time.perf_counter() - t_agg)

        total_time = time.perf_counter() - start_time
        log.info("[FlinkPipeline] ✅ DONE frame_idx=%s cam=%s total=%.3fs evt=%s",
                frame_idx, camera_id, total_time,
                "none" if evt is None else ("open" if evt.opened_incident_id else "close" if evt.closed_incident_id else "other"))

    
        
        if not evt:
            return None
        
        if not (evt.opened_incident_id or evt.closed_incident_id):
            return None
        # Prefer closed_data (has more fields), else opened_data
        data = evt.closed_data or evt.opened_data or {}

        # Build alert dictionary (only non-None fields)
        alert = {}

        # Core identifiers
        alert_id = evt.opened_incident_id or evt.closed_incident_id
        if alert_id:
            alert["alert_id"] = alert_id
        else:
            alert["alert_id"] = f"alert-{int(time.time()*1000)}"

        # Conditionally add non-empty fields
        def put_if_value(key, value):
            if value is not None:
                alert[key] = value

        put_if_value("alert_type", data.get("kind"))
        put_if_value("device_id", camera_id)
        put_if_value("started_at", data.get("ts_iso"))
        put_if_value("ended_at", data.get("ended_at_iso"))
        put_if_value("severity", data.get("severity"))
        put_if_value("vod", data.get("vod"))
        put_if_value("hls", data.get("hls"))
        # Optionally extend later:
    

        meta = {"category": "security"}
        subject = data.get("subject")
        if subject:
            meta["subject"] = subject
        alert["meta"] = meta
        print(alert)
        return alert  # return dict, not JSON string



