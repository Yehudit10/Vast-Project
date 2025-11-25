# agguard/events/aggregator.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import uuid, datetime as _dt
import cv2, numpy as np, time, threading

from .models import Rule, Incident, Box
from agguard.media.hls_recorder import HlsRecorder, HlsConfig
from agguard.media.mp4_recorder import Mp4Recorder
import logging
log = logging.getLogger(__name__)


@dataclass
class IncidentEvent:
    opened_incident_id: str | None = None
    updated_incident_id: str | None = None
    closed_incident_id: str | None = None
    opened_data: Optional[Any] = None
    closed_data: Optional[Any] = None


@dataclass
class _EventState:
    consec: int = 0
    cooldown_left: int = 0
    open_incident: Optional[Incident] = None
    last_seen_frame: int = -1
    last_seen_ts: float = 0.0

    # detections for the *current* frame (for record_frame): list of dicts
    # {"x1": int, "y1": int, "x2": int, "y2": int, "conf": float|None}
    detections: List[Dict[str, Any]] = field(default_factory=list)

    # For severity = mean tracks per frame during the incident
    total_tracks: int = 0
    total_frames: int = 0
    subject: Optional[str] = None


def _iou(a: Box, b: Box) -> float:
    x1, y1, x2, y2 = a
    X1, Y1, X2, Y2 = b
    ix1, iy1 = max(x1, X1), max(y1, Y1)
    ix2, iy2 = min(x2, X2), min(y2, Y2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (x2 - x1) * (y2 - y1) + (X2 - X1) * (Y2 - Y1) - inter
    return inter / max(union, 1e-6)


def _clamp_box(box: Box, w: int, h: int) -> Box:
    x1, y1, x2, y2 = box
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(0, min(w - 1, int(x2)))
    y2 = max(0, min(h - 1, int(y2)))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (x1, y1, x2, y2)


class IncidentAggregator:
    """
    Aggregates evidence PER (camera_id, rule.name).
    Computes severity as mean tracks per frame.
    Persists ALL detections (bbox+conf) per frame in a single DB row.
    """

    def __init__(
        self,
        rules: List[Rule],
        camera_id: Optional[str] = None,
        roi_pixels: Optional[List[Tuple[int, int]]] = None,
        assoc_iou: float = 0.3,
        sample_every: int = 1,
        s3=None, video_bucket=None, video_prefix="security/incidents",
        fps=12, hls_segment_time=3.0, hls_list_size=20, hls_use_cmaf=False,
        draw_thickness=2, media_base: Optional[str] = None, media_token: Optional[str] = None
    ):

        self.rules = rules
        self.camera_id = camera_id
        self.roi_pixels = roi_pixels
        self.assoc_iou = float(assoc_iou)
        self.sample_every = int(sample_every)
        # key: (camera_id, rule.name) -> _EventState
        self._states: Dict[Tuple[str, str], _EventState] = {}
        self.s3 = s3
        self.video_bucket = video_bucket
        self.video_prefix = video_prefix.strip("/")
        self.fps = int(max(1, fps))
        self._hls_cfg = HlsConfig(
            fps=self.fps, segment_time=hls_segment_time, list_size=hls_list_size,
            use_cmaf=hls_use_cmaf, preset="veryfast", crf=23, gop_segments=2, upload_interval_sec=0.25
        )
        self.draw_thickness = int(max(1, draw_thickness))

        self.media_base = (media_base or "").rstrip("/")
        self.media_token = media_token or ""

    # helper for drawing (add this method inside the class)
    def _render_frame_with_boxes(self, frame_bgr, dets):
        out = frame_bgr.copy()
        t = self.draw_thickness
        for d in dets or []:
            x1, y1, x2, y2 = int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"])
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), t)
            tid = d.get("track_id")
            if tid is not None:
                cv2.putText(
                    out,
                    str(tid),
                    (x1, max(0, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )
        return out

    # helper to compute s3 prefix
    def _hls_prefix(self, inc):
        cam = self.camera_id or "unknown"
        return f"{self.video_prefix}/{cam}/{inc.incident_id}"

    # ------------- convenience setters -------------

    def set_camera(self, camera_id: Optional[str]) -> None:
        self.camera_id = camera_id

    def set_roi_pixels(self, roi_pixels: Optional[List[Tuple[int, int]]]) -> None:
        self.roi_pixels = roi_pixels

    # ------------- internals -------------

    def _key(self, rule: Rule) -> Tuple[str, str]:
        cam = self.camera_id or "unknown"
        return (cam, rule.name)

    def _state(self, rule: Rule) -> _EventState:
        k = self._key(rule)
        if k not in self._states:
            self._states[k] = _EventState()
        return self._states[k]

    @staticmethod
    def _class_match(t_cls: Any, rule: Rule) -> bool:
        """
        True if track class matches rule by name or id (if provided).
        If rule doesn't restrict class, accept all.
        """
        t_name = str(t_cls).lower()
        by_name = (rule.target_cls and t_name == str(rule.target_cls).lower())
        by_id = (rule.target_cls_id is not None and str(t_cls) == str(rule.target_cls_id))
        return bool(by_name or by_id) if (rule.target_cls or rule.target_cls_id is not None) else True

    def _match_classes(self, rule: Rule, preds: List) -> bool:
        """
        Return True if any prediction class name matches one of rule.match_classes.
        Includes detailed debug logging for diagnosis.
        """
        if not preds:
            log.info("[_match_classes] ⚠️ No predictions passed for rule '%s'", rule.name)
            return False

        classes = [c.lower().strip() for c in (rule.match_classes or [])]
        if not classes:
            log.info("[_match_classes] 🟢 Rule '%s' has empty match_classes → treating as always True", rule.name)
            return True

        log.info(
            "[_match_classes] 🔍 Evaluating rule='%s' | match_classes=%s | min_conf=%.2f",
            rule.name,
            classes,
            float(rule.min_conf or 0.0),
        )

        matched = False
        for idx, p in enumerate(preds):
            try:
                # Handle dict-style predictions
                if isinstance(p, dict):
                    cls_name = str(
                        p.get("label") or p.get("cls") or p.get("class_name") or ""
                    ).strip().lower()
                    conf = float(p.get("confidence", p.get("conf", 0.0)))
                # Handle object-style (protobuf / custom)
                elif hasattr(p, "label") or hasattr(p, "cls") or hasattr(p, "class_name"):
                    cls_name = str(
                        getattr(p, "label", getattr(p, "cls", getattr(p, "class_name", "")))
                    ).strip().lower()
                    conf = float(getattr(p, "confidence", getattr(p, "conf", 0.0)))
                else:
                    log.warning("[_match_classes] 🚫 Unsupported prediction type %s → skipping", type(p))
                    continue

                log.info("[_match_classes]   • Pred #%d → label='%s' conf=%.3f", idx, cls_name, conf)

                # Check confidence
                if conf < float(rule.min_conf or 0.0):
                    log.info(
                        "[_match_classes]     ↳ below min_conf=%.2f → SKIP",
                        float(rule.min_conf or 0.0),
                    )
                    continue

                # Check class match
                for c in classes:
                    if c == cls_name:
                        log.info("[_match_classes] ✅ EXACT MATCH '%s' for rule '%s'", cls_name, rule.name)
                        matched = True
                        break
                    elif c in cls_name or cls_name in c:
                        log.info(
                            "[_match_classes] ⚡ PARTIAL MATCH '%s' ~ '%s' for rule '%s'",
                            cls_name,
                            c,
                            rule.name,
                        )
                        matched = True
                        break

            except Exception as e:
                log.exception("[_match_classes] ❌ Error parsing prediction #%d: %s", idx, e)

        if not matched:
            log.info(
                "[_match_classes] ❌ No matches found for rule '%s'. Predictions checked: %d",
                rule.name,
                len(preds),
            )

        return matched

    # ------------- HLS deletion scheduler -------------

    def _schedule_hls_deletion(self, hls_recorder, delay_sec: float = 120.0) -> None:
        """
        Delete HLS content after a delay (default 2 minutes), in a background thread.
        """
        if not hls_recorder:
            return

        def _worker():
            try:
                log.info(
                    "[_schedule_hls_deletion] Sleeping %.1f seconds before deleting HLS...",
                    delay_sec,
                )
                time.sleep(delay_sec)

                try:
                    hls_recorder.delete_remote_hls()
                except Exception as e:
                    log.exception("[_schedule_hls_deletion] remote delete error: %s", e)

                try:
                    hls_recorder.delete_hls_files_only()
                except Exception as e:
                    log.exception("[_schedule_hls_deletion] local delete error: %s", e)

                log.info("[_schedule_hls_deletion] HLS cleanup finished.")
            except Exception as e:
                log.exception("[_schedule_hls_deletion] Unexpected error: %s", e)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------- open / close incidents -------------

    def _open_incident(
        self,
        st: _EventState,
        rule: Rule,
        ts_sec: float,
        frame_idx: int,
        frame_bgr,
    ) -> dict:
        log.info(
            "[_open_incident] Opening new incident for rule '%s' at frame %d ts=%.3f",
            rule.name,
            frame_idx,
            ts_sec,
        )
        inc = Incident(
            incident_id=str(uuid.uuid4()),
            kind=rule.name,
            camera_id=self.camera_id,
            started_ts=ts_sec,
            frame_start=frame_idx,
            roi=self.roi_pixels,
            severity=getattr(rule, "severity", 0),
        )
        st.open_incident = inc
        st.cooldown_left = int(rule.cooldown)
        st.total_tracks = 0
        st.total_frames = 0

        # Start HLS recorder immediately (so index.m3u8 appears fast)
        if self.s3 and self.video_bucket:
            # --- Live HLS recorder ---
            st._hls = HlsRecorder(
                s3=self.s3,
                bucket=self.video_bucket,
                prefix=self._hls_prefix(inc),
                cfg=self._hls_cfg,
            )
            H, W = frame_bgr.shape[:2]
            st._hls.start((H, W))
            st._hls.write_bgr(self._render_frame_with_boxes(frame_bgr, st.detections))

            # --- MP4 recorder (for final video only) ---
            st._mp4 = Mp4Recorder(
                s3=self.s3,
                bucket=self.video_bucket,
                prefix=self._hls_prefix(inc),
                cfg=self._hls_cfg,
            )
            st._mp4.start((H, W))
            st._mp4.write_bgr(self._render_frame_with_boxes(frame_bgr, st.detections))

        # Only notify external world once the playlist definitely exists
        if self.media_base and hasattr(st, "_hls") and st._hls:
            log.info("[_open_incident] Waiting for playlist readiness...")
            st._hls.wait_ready(timeout=6.0)  # usually quick (first segment_time)
            camera = inc.camera_id
            incident_id = inc.incident_id
            hls_url = f"{camera}/{incident_id}/index.m3u8"
            vod_url = f"{camera}/{incident_id}/final.mp4"
            anomaly = inc.kind or "unknown"
            sev = "info"
            log.info(
                "[_open_incident] Sending alert to Alertmanager for incident_id=%s hls_url=%s",
                incident_id,
                hls_url,
            )
        else:
            hls_url = None
            vod_url = None

        opened_data = {
            "incident_id": inc.incident_id,
            "camera_id": inc.camera_id,
            "kind": rule.name,
            "ts_iso": _dt.datetime.utcfromtimestamp(ts_sec).isoformat() + "Z",
            "frame_start": frame_idx,
            "roi": self.roi_pixels,
            "severity": getattr(rule, "severity", 0),
            "hls": hls_url,
            "subject": getattr(st, "subject", None),
        }
        return opened_data

    def _close_incident(
        self,
        key: Tuple[str, str],
        st: _EventState,
        ts_sec: float,
        frame_idx: int,
    ) -> dict:
        inc = st.open_incident
        if not inc:
            log.info("[_close_incident] No open incident to close for key=%s", key)
            return

        log.info("[_close_incident] Closing incident %s (rule=%s)", inc.incident_id, key[1])

        inc.ended_ts = ts_sec
        inc.frame_end = frame_idx
        inc.duration_sec = max(0.0, inc.ended_ts - inc.started_ts)

        # severity = mean tracks per frame during the incident
        severity = round(float(st.total_tracks) / max(st.total_frames, 1))
        log.info(
            "[_close_incident] Computed severity=%.3f (tracks=%d frames=%d)",
            severity,
            st.total_tracks,
            st.total_frames,
        )

        mp4_key = None

        if self.s3 and self.video_bucket and hasattr(st, "_hls") and st._hls:
            try:
                log.info(
                    "[_close_incident] Finalizing HLS to MP4 for incident_id=%s",
                    inc.incident_id,
                )

                if st._hls:
                    try:
                        # 1️⃣ Stop ffmpeg FIRST — always
                        st._hls.stop()
                        log.info(
                            "[DEBUG] ffmpeg alive? %s",
                            st._hls._proc and st._hls._proc.poll() is None,
                        )

                        time.sleep(0.2)

                        # 2️⃣ Finalize MP4 — now safe
                        mp4_key = st._mp4.finalize() if hasattr(st, "_mp4") and st._mp4 else None
                        log.info(
                            "[_close_incident] finalize_to_mp4() returned mp4_key=%s",
                            mp4_key,
                        )

                        # 3️⃣ Schedule HLS deletion in 2 minutes
                        self._schedule_hls_deletion(st._hls, delay_sec=120.0)

                    except Exception as e:
                        log.exception("[_close_incident] Cleanup error: %s", e)
            except Exception as e:
                log.exception("[_close_incident] Error finalizing MP4: %s", e)
        else:
            log.info(
                "[_close_incident] Skipping MP4 finalization — missing s3/video_bucket or no _hls"
            )

        # Reset state for this (camera, rule)
        self._states[key] = _EventState()

        closed_data = {
            "incident_id": inc.incident_id,
            "kind": inc.kind,
            "ended_at_iso": _dt.datetime.utcfromtimestamp(ts_sec).isoformat() + "Z",
            "ts_iso": _dt.datetime.utcfromtimestamp(inc.started_ts).isoformat() + "Z",
            "duration_sec": inc.duration_sec,
            "frame_end": frame_idx,
            "severity": inc.severity + severity,
            "vod": f"{inc.camera_id}/{inc.incident_id}/final.mp4",
            "subject": getattr(st, "subject", None),
        }
        return closed_data

    # ------------- public API -------------

    def update(
        self,
        frame_idx: int,
        ts_sec: float,
        frame_bgr,
        tracks: List,
        outputs: Dict[str, List],
    ) -> IncidentEvent:
        """
        Evaluate evidence per (camera_id, rule). Maintain incident state.
        Also captures ALL detections (bbox + conf) for record_frame().
        Returns IncidentEvent to signal opens/updates/closes to the caller.
        """
        log.info(
            "[update] frame_idx=%d ts=%.3f num_tracks=%d num_outputs=%d",
            frame_idx,
            ts_sec,
            len(tracks),
            len(outputs or {}),
        )

        H, W = frame_bgr.shape[:2]
        by_cls = outputs or {}
        evt = IncidentEvent()

        for rule in self.rules:
            # Only skip 'intruding animal' if climbing_fence truly matched
            if rule.name == "intruding animal":
                cf_preds = by_cls.get("climbing_fence", [])
                climbing_rule = next(
                    (r for r in self.rules if r.name == "climbing_fence"),
                    None,
                )

                if climbing_rule and self._match_classes(climbing_rule, cf_preds):
                    log.info(
                        "[update] Valid climbing_fence detected → suppressing intruding animal."
                    )
                    continue

            log.info(
                "[update] Evaluating rule '%s' (target_cls=%s cooldown=%s)",
                rule.name,
                getattr(rule, "target_cls", None),
                getattr(rule, "cooldown", None),
            )

            candidate_tracks = [t for t in tracks if self._class_match(t.cls, rule)]
            preds = by_cls.get(rule.name, []) or by_cls.get(rule.target_cls, [])

            st = self._state(rule)

            # 🧠 Prefer subject propagated from "intruding animal" (via outputs["_subject"])
            if "_subject" in outputs and outputs["_subject"]:
                st.subject = outputs["_subject"][0]  # e.g. "bear"
                conf_val = None  # no confidence value for propagated subject
                log.info(
                    "[update] 🐾 Propagated subject from intruding animal: %s",
                    st.subject,
                )

            # 🐾 Otherwise, derive subject from current rule's predictions
            elif preds:
                best_pred = max(
                    preds,
                    key=lambda p: getattr(
                        p,
                        "confidence",
                        p.get("confidence", 0.0) if isinstance(p, dict) else 0.0,
                    ),
                )

                if isinstance(best_pred, dict):
                    st.subject = best_pred.get("label")
                    conf_val = best_pred.get("confidence", 0.0)
                else:
                    st.subject = getattr(best_pred, "label", None)
                    conf_val = getattr(best_pred, "confidence", 0.0)

                log.info(
                    "[update] 🐾 Subject detected for rule '%s': %s (conf=%.2f)",
                    rule.name,
                    st.subject,
                    conf_val,
                )
            else:
                st.subject = None
                conf_val = 0.0

            log.info(
                "[update] Found %d candidate tracks and %d predictions for rule '%s'",
                len(candidate_tracks),
                len(preds),
                rule.name,
            )

            evidence = False
            frame_detections: List[Dict[str, Any]] = []

            for t in candidate_tracks:
                bx = _clamp_box(tuple(map(int, t.bbox)), W, H)
                if self._match_classes(rule, preds):
                    evidence = True
                    log.info(
                        "[update] Evidence matched for rule '%s' on track_id=%s bbox=%s",
                        rule.name,
                        getattr(t, "track_id", None),
                        bx,
                    )

                x1, y1, x2, y2 = bx
                try:
                    conf_val = float(t.conf)
                except Exception:
                    conf_val = None
                frame_detections.append(
                    {
                        "track_id": int(t.track_id)
                        if getattr(t, "track_id", None) is not None
                        else None,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "conf": conf_val,
                    }
                )

            st = self._state(rule)
            key = self._key(rule)
            log.info(
                "[update] Current state for key=%s consec=%d cooldown_left=%d open_incident=%s",
                key,
                st.consec,
                st.cooldown_left,
                getattr(st.open_incident, "incident_id", None),
            )

            # If recording, write current frame (with boxes) continuously
            if st.open_incident is not None:
                rendered = self._render_frame_with_boxes(frame_bgr, st.detections)
                if hasattr(st, "_hls") and st._hls:
                    st._hls.write_bgr(rendered)  # continuous live feed
                if hasattr(st, "_mp4") and st._mp4:
                    st._mp4.write_bgr(rendered)  # only called when new frames arrive

                st.total_tracks += len(frame_detections)
                st.total_frames += 1
                log.info(
                    "[update] Recorded frame for active incident=%s total_tracks=%d total_frames=%d",
                    st.open_incident.incident_id,
                    st.total_tracks,
                    st.total_frames,
                )

            st.last_seen_frame = frame_idx
            st.last_seen_ts = ts_sec
            st.detections = frame_detections

            prev_consec = st.consec
            st.consec = st.consec + 1 if evidence else 0
            log.info(
                "[update] Consecutive evidence count changed from %d -> %d (rule='%s')",
                prev_consec,
                st.consec,
                rule.name,
            )

            if st.open_incident is None and st.consec >= int(rule.min_consec or 1):
                log.info("[update] Triggering _open_incident for rule '%s'", rule.name)
                opened_data = self._open_incident(
                    st,
                    rule,
                    ts_sec,
                    frame_idx,
                    frame_bgr,
                )
                evt.opened_incident_id = st.open_incident.incident_id
                evt.opened_data = opened_data
                log.info(
                    "[update] Opened new incident_id=%s for rule='%s'",
                    evt.opened_incident_id,
                    rule.name,
                )

            if st.open_incident is not None:
                # sample a representative bbox to append to incident trail
                if (
                    self.sample_every > 0
                    and (frame_idx % self.sample_every == 0)
                    and st.detections
                ):
                    bx = max(
                        (
                            (d["x2"] - d["x1"]) * (d["y2"] - d["y1"]),
                            d,
                        )
                        for d in st.detections
                    )[1]
                    st.open_incident.boxes.append(
                        (bx["x1"], bx["y1"], bx["x2"], bx["y2"])
                    )
                    st.open_incident.confs.append(1.0)
                    log.info(
                        "[update] Appended sample bbox=%s to incident trail for %s",
                        bx,
                        st.open_incident.incident_id,
                    )

                # cooldown logic
                prev_cooldown = st.cooldown_left
                st.cooldown_left = (
                    int(rule.cooldown) if evidence else (st.cooldown_left - 1)
                )
                log.info(
                    "[update] Cooldown changed %d -> %d (evidence=%s)",
                    prev_cooldown,
                    st.cooldown_left,
                    evidence,
                )

                if not evidence and st.cooldown_left <= 0:
                    closed_id = st.open_incident.incident_id
                    log.info(
                        "[update] Closing incident %s (cooldown expired)",
                        closed_id,
                    )
                    closed_data = self._close_incident(
                        key,
                        st,
                        ts_sec,
                        frame_idx,
                    )
                    evt.closed_incident_id = closed_id
                    evt.closed_data = closed_data

                else:
                    evt.updated_incident_id = st.open_incident.incident_id
                    log.info(
                        "[update] Updating active incident %s (evidence=%s cooldown=%d)",
                        st.open_incident.incident_id,
                        evidence,
                        st.cooldown_left,
                    )

        log.info(
            "[update] Returning IncidentEvent opened=%s updated=%s closed=%s",
            evt.opened_incident_id,
            evt.updated_incident_id,
            evt.closed_incident_id,
        )
        return evt

    def flush(self, ts_sec: float, frame_idx: int):
        """Close any open incidents across all cameras/rules."""
        for key, st in list(self._states.items()):
            if st.open_incident is not None:
                self._close_incident(key, st, ts_sec, frame_idx)
