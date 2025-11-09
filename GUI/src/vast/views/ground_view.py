
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QMessageBox, QSizePolicy, QFrame
)

# The client does not access MinIO directly; everything goes through DashboardApi
from vast.dashboard_api import DashboardApi

GROUND_BUCKET = os.getenv("GROUND_BUCKET", "ground")
GROUND_PREFIX = os.getenv("GROUND_PREFIX", "")

# ----------------------------
# PHI data model
# ----------------------------
@dataclass
class PhiSnapshot:
    phi: Optional[float]           # 0..100 or None
    density: Optional[float]
    coverage: Optional[float]
    severity_avg: Optional[float]
    trend: Optional[float]
    week_start: Optional[str]
    source: str = ""               # textual hint of data source


def _phi_band_color(v: float) -> str:
    if v >= 80:
        return "#16a34a"  # green-600
    if v >= 50:
        return "#f59e0b"  # amber-500
    return "#dc2626"      # red-600


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


class GroundView(QWidget):
    """
    Gallery mode:
      - Loads all object keys from MinIO bucket=GROUND_BUCKET, prefix=GROUND_PREFIX.
      - Keeps current index; supports Prev/Next buttons and keyboard arrows.
      - On image change, loads bytes via DashboardApi and refreshes PHI for that key.

    Design goals:
      - No direct MinIO client on the GUI.
      - Be resilient to missing API methods; fail gracefully.
    """

    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api

        # State for gallery
        self._keys: List[str] = []
        self._idx: int = -1

        # ---------- UI ----------
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("🌿 Ground — Gallery & PHI")
        title.setStyleSheet("font-size:20px;font-weight:800;color:#0f172a;")
        root.addWidget(title)

        toolbar = QHBoxLayout()
        self.btn_refresh_list = QPushButton("Reload list")
        self.btn_refresh_list.clicked.connect(self.reload_keys)

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.next_image)

        self.btn_show_phi = QPushButton("Show PHI")
        self.btn_show_phi.clicked.connect(self.refresh_phi_current)

        self.counter_label = QLabel("(0 / 0)")
        self.counter_label.setStyleSheet("color:#475569;font-size:12px;")

        toolbar.addWidget(self.btn_refresh_list)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.btn_prev)
        toolbar.addWidget(self.btn_next)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.btn_show_phi)
        toolbar.addStretch(1)
        toolbar.addWidget(self.counter_label)
        root.addLayout(toolbar)

        # Image frame
        img_frame = QFrame()
        img_frame.setStyleSheet("background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;")
        img_layout = QVBoxLayout(img_frame)
        img_layout.setContentsMargins(8, 8, 8, 8)
        img_layout.setSpacing(6)

        self.image_label = QLabel("(No image loaded yet)")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setMinimumHeight(260)
        img_layout.addWidget(self.image_label)

        self.img_meta = QLabel("")
        self.img_meta.setStyleSheet("color:#475569;font-size:12px;")
        img_layout.addWidget(self.img_meta)

        root.addWidget(img_frame, stretch=2)

        # PHI area
        phi_frame = QFrame()
        phi_frame.setStyleSheet("background:#ffffff;border:1px solid #cbd5e1;border-radius:10px;")
        phi_layout = QVBoxLayout(phi_frame)
        phi_layout.setContentsMargins(12, 12, 12, 12)
        phi_layout.setSpacing(8)

        row = QHBoxLayout()
        self.phi_label = QLabel("PHI: –")
        self.phi_label.setStyleSheet("font-size:16px;font-weight:700;color:#0f172a;")
        row.addWidget(self.phi_label)
        row.addStretch(1)
        self.phi_details = QLabel("")
        self.phi_details.setStyleSheet("color:#475569;font-size:12px;")
        row.addWidget(self.phi_details)
        phi_layout.addLayout(row)

        self.phi_bar = QProgressBar()
        self.phi_bar.setRange(0, 100)
        self.phi_bar.setValue(0)
        self.phi_bar.setFormat("%v")
        self._style_phi_bar(None)
        phi_layout.addWidget(self.phi_bar)

        root.addWidget(phi_frame, stretch=1)

        # Auto-refresh PHI every 2 min (optional)
        self.timer = QTimer(self)
        self.timer.setInterval(120_000)
        self.timer.timeout.connect(self.refresh_phi_current)
        self.timer.start()

        # Initial load
        QTimer.singleShot(200, self.reload_keys)

        # So that arrow keys work even without inner focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ----------------------------
    # Styling helpers
    # ----------------------------
    def _style_phi_bar(self, value: Optional[float]) -> None:
        color = "#64748b" if value is None else _phi_band_color(float(value))
        self.phi_bar.setStyleSheet(
            f"QProgressBar {{ border:1px solid #cbd5e1;border-radius:6px;height:18px; }} "
            f"QProgressBar::chunk {{ background:{color}; border-radius:6px; }}"
        )

    def _warn(self, msg: str) -> None:
        try:
            def _show():
                try:
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Icon.Warning)
                    box.setWindowTitle("Ground")
                    box.setText(str(msg))
                    box.setStandardButtons(QMessageBox.StandardButton.Ok)
                    box.setWindowModality(Qt.WindowModality.NonModal)
                    box.show()
                except BaseException:
                    print(f"[GroundView] WARN(fallback): {msg}")
            QTimer.singleShot(0, _show)
        except BaseException:
            print(f"[GroundView] WARN: {msg}")

    def _try_api(self, names: List[str], *args, **kwargs) -> Any:
        for name in names:
            fn = getattr(self.api, name, None)
            if callable(fn):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    print(f"[GroundView] API call {name} failed: {e}")
        return None

    # ----------------------------
    # Gallery: load keys & navigation
    # ----------------------------
    def reload_keys(self) -> None:
        """Load all object keys from MinIO (sorted newest→oldest)."""
        try:
            objs = self._try_api(
                ["list_minio_objects", "list_objects"],
                bucket=GROUND_BUCKET, prefix=GROUND_PREFIX, limit=1000
            )
            keys: List[str] = []
            if isinstance(objs, list):
                # Sort by last_modified/LastModified desc when available
                def _lm(o):
                    if not isinstance(o, dict):
                        return ""
                    return o.get("last_modified") or o.get("LastModified") or ""
                try:
                    objs = sorted(objs, key=_lm, reverse=True)
                except Exception:
                    pass
                for o in objs:
                    if isinstance(o, dict):
                        for f in ("key", "name", "object_name", "path"):
                            v = o.get(f)
                            if isinstance(v, str) and v.strip():
                                keys.append(v.strip())
                                break

            self._keys = keys
            self._idx = 0 if self._keys else -1
            self._update_counter()
            if self._idx >= 0:
                self.load_current_image()
            else:
                self._set_image(None)
                self.img_meta.setText("No objects found in MinIO.")
                self._render_phi_none()

        except Exception as e:
            self._warn(f"reload_keys error: {e}")

    def _update_counter(self) -> None:
        total = len(self._keys)
        pos = (self._idx + 1) if self._idx >= 0 else 0
        self.counter_label.setText(f"({pos} / {total})")

    def prev_image(self) -> None:
        if not self._keys:
            return
        self._idx = (self._idx - 1) % len(self._keys)
        self._update_counter()
        self.load_current_image()

    def next_image(self) -> None:
        if not self._keys:
            return
        self._idx = (self._idx + 1) % len(self._keys)
        self._update_counter()
        self.load_current_image()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_A):
            self.prev_image()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_D):
            self.next_image()
            event.accept()
            return
        super().keyPressEvent(event)

    # ----------------------------
    # Image load + PHI for current key
    # ----------------------------
    def _set_image(self, pix: Optional[QPixmap]) -> None:
        if pix is None or pix.isNull():
            self.image_label.setText("(No image)")
            self.image_label.setPixmap(QPixmap())
            return
        target_size: QSize = self.image_label.size()
        if target_size.width() <= 4 or target_size.height() <= 4:
            self.image_label.setPixmap(pix)
            return
        scaled = pix.scaled(
            target_size.width(),
            target_size.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        pix = self.image_label.pixmap()
        if pix is not None and not pix.isNull():
            self._set_image(pix)

    def load_current_image(self) -> None:
        """Load image bytes for current key and refresh PHI."""
        try:
            if self._idx < 0 or self._idx >= len(self._keys):
                self._set_image(None)
                self.img_meta.setText("No selection.")
                self._render_phi_none()
                return

            key = self._keys[self._idx]
            getter = getattr(self.api, "get_image_bytes_from_minio", None)
            if not callable(getter):
                self._warn("DashboardApi.get_image_bytes_from_minio is missing.")
                return

            data = None
            try:
                data = getter(key, bucket=GROUND_BUCKET)
            except TypeError:
                data = getter(key)
            except Exception as e:
                self._warn(f"Failed fetching image bytes: {e}")
                data = None

            if not data:
                self._set_image(None)
                self.img_meta.setText(f"Failed to read: {GROUND_BUCKET}/{key}")
                self._render_phi_none()
                return

            pix = QPixmap()
            if not pix.loadFromData(data):
                self._set_image(None)
                self.img_meta.setText(f"Unsupported bytes: {GROUND_BUCKET}/{key}")
                self._render_phi_none()
                return

            self._set_image(pix)
            self.img_meta.setText(f"{GROUND_BUCKET}/{key}")
            # After image displayed, refresh PHI
            self._refresh_phi_for_key(key)

        except Exception as e:
            self._warn(f"load_current_image error: {e}")

    # ----------------------------
    # PHI flow
    # ----------------------------
    def _map_phi_dict(self, d: Dict[str, Any], source: str) -> PhiSnapshot:
        return PhiSnapshot(
            phi=_safe_float(d.get("phi")),
            density=_safe_float(d.get("density")),
            coverage=_safe_float(d.get("coverage")),
            severity_avg=_safe_float(d.get("severity_avg")),
            trend=_safe_float(d.get("trend")),
            week_start=str(d.get("week_start")) if d.get("week_start") is not None else None,
            source=source,
        )

    def _render_phi_none(self) -> None:
        self.phi_label.setText("PHI: –")
        self.phi_details.setText("No PHI available.")
        self.phi_bar.setValue(0)
        self._style_phi_bar(None)

    def _refresh_phi_for_key(self, key: str) -> None:
        """Try best-effort PHI for the specific image key."""
        try:
            # Preferred API: PHI for an explicit image key
            d = self._try_api(["get_phi_for_image"], key)
            if isinstance(d, dict) and (d.get("phi") is not None or d.get("severity_avg") is not None):
                snap = self._map_phi_dict(d, "phi_by_key")
                return self._render_phi(snap)

            # Fallbacks (like your previous logic)
            # 1) PHI for current image (if API tracks it)
            d = self._try_api(["get_phi_for_current_image"])
            if isinstance(d, dict) and (d.get("phi") is not None or d.get("severity_avg") is not None):
                snap = self._map_phi_dict(d, "phi_current")
                return self._render_phi(snap)

            # 2) weekly/global PHI
            d = self._try_api(["get_weekly_phi"])
            if isinstance(d, dict) and (d.get("phi") is not None or d.get("severity_avg") is not None):
                snap = self._map_phi_dict(d, "weekly")
                return self._render_phi(snap)

            # 3) derive from latest rows (very rough)
            rows = self._try_api(["get_latest_rows", "get_latest_detections", "get_latest_ground_rows"], limit=1) or []
            if rows and isinstance(rows, list) and isinstance(rows[0], dict):
                sev = None
                cov = None
                for k in ("severity_avg", "severity", "mean_severity"):
                    sev = _safe_float(rows[0].get(k))
                    if sev is not None:
                        break
                for k in ("coverage", "plant_coverage"):
                    cov = _safe_float(rows[0].get(k))
                    if cov is not None:
                        break
                phi_val = None
                if sev is not None:
                    s = sev if sev <= 1.0 else min(sev, 10.0) / 10.0
                    phi_val = max(0.0, min(100.0, 100.0 * (1.0 - s)))
                elif cov is not None:
                    c = max(0.0, min(1.0, cov))
                    phi_val = 100.0 * c
                if phi_val is not None:
                    snap = PhiSnapshot(
                        phi=phi_val, density=None, coverage=cov, severity_avg=sev,
                        trend=None, week_start=None, source="derived_from_rows"
                    )
                    return self._render_phi(snap)

            self._render_phi_none()

        except Exception as e:
            self._warn(f"_refresh_phi_for_key error: {e}")
            self._render_phi_none()

    def _render_phi(self, snap: PhiSnapshot) -> None:
        if snap is None or snap.phi is None:
            self._render_phi_none()
            return
        val = max(0, min(100, int(round(snap.phi))))
        self.phi_label.setText(f"PHI: {val}")
        parts = []
        if snap.density is not None:
            parts.append(f"density={snap.density:.2f}")
        if snap.coverage is not None:
            parts.append(f"coverage={snap.coverage:.2f}")
        if snap.severity_avg is not None:
            parts.append(f"severity={snap.severity_avg:.2f}")
        if snap.trend is not None:
            parts.append(f"trend={snap.trend:+.2f}")
        if snap.week_start:
            parts.append(f"week={snap.week_start}")
        if snap.source:
            parts.append(f"src={snap.source}")
        self.phi_details.setText(" | ".join(parts))
        self.phi_bar.setValue(val)
        self._style_phi_bar(val)

    def refresh_phi_current(self) -> None:
        """Public slot for the 'Show PHI' button; uses current image key."""
        if 0 <= self._idx < len(self._keys):
            self._refresh_phi_for_key(self._keys[self._idx])
        else:
            self._render_phi_none()
