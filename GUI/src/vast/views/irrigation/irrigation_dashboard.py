# from pathlib import Path
# import sys, random

# # Add current directory to path to allow direct execution
# script_dir = Path(__file__).parent
# sys.path.insert(0, str(script_dir))

# from PyQt6.QtWidgets import (
#     QApplication, QWidget, QVBoxLayout, QDialog, QFormLayout, QScrollArea,
#     QComboBox, QLineEdit, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
#     QHeaderView, QProgressBar, QDialogButtonBox, QGraphicsDropShadowEffect, QLabel
# )
# from map_widget import MapWidget
# from history_panel import HistoryPanel
# # from .sprinkler_details_dialog import SprinklerDetailsDialog
# from sprinkler_details_dialog_new import SprinklerDetailsDialogNew
# from dashboard_bar import DashboardBar
# from PyQt6.QtGui import QPixmap, QMovie, QFont, QColor, QIcon
# from PyQt6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QRect, QEasingCurve

# import psycopg2
# from psycopg2.extras import RealDictCursor

# # ----------------------- DB helpers (unchanged) -----------------------
# def get_db_connection():
#     return psycopg2.connect(
#         # host="postgres",
#         host = "localhost",
#         port=5432,
#         user="missions_user",
#         password="pg123",
#         dbname="missions_db",
#         cursor_factory=RealDictCursor
#     )

# # NOTE: original fetch functions retained (they must exist and behave the same)
# # For brevity we keep their original implementations from the provided file.

# def fetch_sprinkler_history(limit=500):
#     query = f"""
#         SELECT e.device_id, e.dry_ratio, e.decision, e.confidence, e.patch_count, e.extra,
#                p.prev_state, e.ts
#         FROM soil_moisture_events e
#         LEFT JOIN irrigation_policies p ON e.device_id = p.device_id
#         ORDER BY e.ts DESC
#         LIMIT {limit}
#     """
#     with get_db_connection() as conn:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(query)
#             rows = cur.fetchall()

#     for row in rows:
#         prev_state = row.get('prev_state') or 'stop'
#         decision = row['decision']
#         if decision == "noop":
#             new_state = prev_state
#         elif decision in ("run", "stop"):
#             new_state = decision
#         else:
#             new_state = "stop"
#         row['prev_state'] = prev_state
#         row['new_state'] = new_state

#     return rows


# def fetch_sprinkler_data():
#     query = """
#         SELECT e.device_id, e.dry_ratio, e.decision, e.confidence, e.patch_count, e.extra,
#                e.ts, p.prev_state
#         FROM soil_moisture_events e
#         LEFT JOIN irrigation_policies p ON e.device_id = p.device_id
#         WHERE e.ts = (
#             SELECT MAX(ts)
#             FROM soil_moisture_events e2
#             WHERE e2.device_id = e.device_id
#         )
#         ORDER BY e.device_id
#     """

#     with get_db_connection() as conn:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(query)
#             rows = cur.fetchall()

#     for row in rows:
#         prev_state = row.get('prev_state') or 'stop'
#         decision = row['decision']
#         if decision == "noop":
#             new_state = prev_state
#         elif decision in ("run", "stop"):
#             new_state = decision
#         else:
#             new_state = "stop"
#         row['prev_state'] = prev_state
#         row['new_state'] = new_state

#     return rows


# # ----------------------- UI Components -----------------------
# class ImageModal(QDialog):
#     """Modal to show image with dark overlay and details"""
#     def __init__(self, parent, pixmap: QPixmap, details: dict):
#         super().__init__(parent)
#         self.setModal(True)
#         self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

#         self.main = QWidget(self)
#         self.main.setStyleSheet("background: white; border-radius: 12px;")
#         layout = QVBoxLayout(self.main)
#         self.main.setLayout(layout)

#         img_label = QLabel()
#         max_w = int(parent.width() * 0.8)
#         max_h = int(parent.height() * 0.8)
#         img_label.setPixmap(pixmap.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
#         img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         layout.addWidget(img_label)

#         info = QLabel(f"Timestamp: {details.get('ts')} — Decision: {details.get('decision')} — Confidence: {details.get('confidence'):.2f}")
#         layout.addWidget(info)

#         btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
#         btns.rejected.connect(self.close)
#         layout.addWidget(btns)

#         # position central
#         w, h = int(parent.width()*0.85), int(parent.height()*0.85)
#         self.setGeometry((parent.width()-w)//2, (parent.height()-h)//2, w, h)
#         self.main.setGeometry(0, 0, w, h)

# class FloatingDetailsCard(QWidget):
#     """Floating centered card (replaces drawer)"""
#     def __init__(self, parent, device_id, details):
#         super().__init__(parent)
#         self.device_id = device_id
#         self.details = details
#         self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

#         self.card = QWidget(self)
#         self.card.setStyleSheet("""
#             background: white;
#             border-radius: 14px;
#         """)

#         shadow = QGraphicsDropShadowEffect(self.card)
#         shadow.setBlurRadius(30)
#         shadow.setOffset(0, 8)
#         shadow.setColor(QColor(0,0,0,100))
#         self.card.setGraphicsEffect(shadow)

#         # layout
#         l = QVBoxLayout(self.card)
#         l.setContentsMargins(20, 20, 20, 20)
#         # title with gradient-like color
#         title = QLabel(f"Sprinkler {device_id}")
#         title.setFont(QFont('Segoe UI', 14, QFont.Weight.Bold))
#         title.setStyleSheet("color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #0891b2);")
#         l.addWidget(title)

#         # status row
#         status_row = QHBoxLayout()
#         status_dot = QLabel('●')
#         status_dot.setFont(QFont('Arial', 16))
#         status_color = '#10b981' if details.get('active') else '#6b7280'
#         status_dot.setStyleSheet(f"color: {status_color}")
#         status_row.addWidget(status_dot)
#         status_row.addWidget(QLabel('Active' if details.get('active') else 'Inactive'))
#         status_row.addStretch()
#         l.addLayout(status_row)

#         # dry ratio progress
#         dry_label = QLabel('💧 Dry Ratio')
#         l.addWidget(dry_label)
#         pb = QProgressBar()
#         pb.setRange(0, 100)
#         pb.setValue(int(details.get('dry_ratio',0)*100))
#         pb.setTextVisible(True)
#         pb.setFormat('%.0f%%' % (pb.value(),))
#         pb.setFixedHeight(18)
#         pb.setStyleSheet("border-radius:9px;")
#         l.addWidget(pb)

#         # confidence with color
#         conf = details.get('confidence',0)
#         conf_label = QLabel(f'🎯 Confidence: {conf:.2f}')
#         if conf >= 0.75:
#             conf_color = '#10b981'
#         elif conf >= 0.4:
#             conf_color = '#f59e0b'
#         else:
#             conf_color = '#ef4444'
#         conf_label.setStyleSheet(f'color: {conf_color}; font-weight: bold')
#         l.addWidget(conf_label)

#         # decision
#         decision_label = QLabel(f'⚙️ Decision: {details.get("decision")}')
#         l.addWidget(decision_label)

#         # button row (bottom)
#         btn_row = QHBoxLayout()
#         btn_row.setSpacing(16)
#         btn_row.addStretch()
#         # Show History button
#         self.show_history_btn = QPushButton('Show History')
#         self.show_history_btn.setStyleSheet('background:#06b6d4; color:white; padding:8px; border-radius:8px')
#         btn_row.addWidget(self.show_history_btn)
#         # Close button
#         self.close_btn = QPushButton('Close')
#         self.close_btn.clicked.connect(self.close_card)
#         self.close_btn.setFixedWidth(120)
#         self.close_btn.setStyleSheet('background:#3b82f6; color:white; padding:8px; border-radius:10px')
#         btn_row.addWidget(self.close_btn)
#         l.addLayout(btn_row)

#         # size and position
#         w, h = int(parent.width()*0.6), int(parent.height()*0.5)
#         self.setGeometry((parent.width()-w)//2, (parent.height()-h)//2, w, h)
#         self.card.setGeometry(0,0,w,h)

#         # fade-in animation
#         self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
#         self.opacity_anim.setDuration(220)
#         self.opacity_anim.setStartValue(0.0)
#         self.opacity_anim.setEndValue(1.0)
#         self.setWindowOpacity(0.0)
#         self.opacity_anim.start()

#     def close_card(self):
#         self.close()

# class IrrigationDashboard(QWidget):
#     def __init__(self):
#         super().__init__()
#         print("[DEBUG] IrrigationDashboard.__init__ called")
#         self.setWindowTitle("Irrigation Dashboard 🌾")
#         self.setGeometry(100, 100, 1100, 820)
#         QApplication.setFont(QFont('Roboto', 10))
#         main = QVBoxLayout(self)
#         main.setContentsMargins(0,0,0,0)
#         self.setStyleSheet("""
#             QWidget#root { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0f9ff, stop:1 #e0f2fe); }
#             QLabel.title { font-family: 'Segoe UI'; font-weight: bold; font-size: 18px; color: #111827 }
#         """)
#         self.setObjectName('root')

#         # MapWidget replaces map logic
#         print("[DEBUG] Creating DashboardBar...")
#         self.dashboard_bar = DashboardBar(self)
#         main.addWidget(self.dashboard_bar)
#         print("[DEBUG] Creating MapWidget...")
#         self.map_widget = MapWidget(self, map_path=str(script_dir / "map_field.jpg"))
#         self.sprinklers = {}  # device_id -> info, for non-map logic (details, etc.)
#         # print("[DEBUG] Creating HistoryPanel...")
#         # self.history_panel = HistoryPanel(self)
#         # self.history_panel.hide()
        
#         # Create map layout with minimal margins to push sprinklers down
#         map_container = QWidget()
#         map_layout = QVBoxLayout(map_container)
#         map_layout.setContentsMargins(0, 10, 0, 0)  # Minimal top margin (10px instead of default)
#         map_layout.setSpacing(0)
#         map_layout.addWidget(self.map_widget)
        
#         main.addWidget(map_container, stretch=3)
#         # main.addWidget(self.history_panel, stretch=1)

#         # timer for data refresh
#         print("[DEBUG] Setting up timer...")
#         self.timer = QTimer()
#         self.timer.timeout.connect(self.safe_update_data)
#         # Delay first update to avoid issues during init
#         self.timer.singleShot(1000, self.safe_update_data)
#         self.timer.start(3000)
#         print("[DEBUG] IrrigationDashboard.__init__ completed")

#     def resizeEvent(self, event):
#         super().resizeEvent(event)
#         # Delegate map resizing to MapWidget
#         if hasattr(self, 'map_widget') and self.map_widget:
#             self.map_widget.resizeEvent(event)

#     def set_sprinkler_state(self, s, active):
#         btn: QPushButton = s['widget']
#         # create / reuse label for movie
#         if 'label' not in s:
#             lbl = QLabel(btn)
#             lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
#             lbl.setGeometry(0,0,btn.width(),btn.height())
#             lbl.raise_()  # Raise label above button to display image
#             s['label'] = lbl
#         lbl = s['label']

#         if active:
#             movie = QMovie(str(script_dir / 'sprinkler_on.gif'))
#             movie.setScaledSize(QSize(btn.width(), btn.height()))
#             lbl.setMovie(movie)
#             movie.start()
#             lbl.raise_()  # Ensure label stays on top
#             lbl.show()
#             btn.setStyleSheet(self.sprinkler_style(active=True))
#             s['movie'] = movie
#         else:
#             # static image
#             pix = QPixmap(str(script_dir / 'sprinkler_off.png')) if (script_dir / 'sprinkler_off.png').exists() else QPixmap(btn.width(), btn.height())
#             if pix.isNull():
#                 pix = QPixmap(btn.width(), btn.height()); pix.fill(QColor('#6b7280'))
#             lbl.setPixmap(pix.scaled(btn.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
#             lbl.raise_()  # Ensure label stays on top
#             lbl.show()
#             btn.setStyleSheet(self.sprinkler_style(active=False))
#             s['movie'] = None
#         s['active'] = active

#     def sprinkler_style(self, active=False):
#         # circular button with colored background (not transparent)
#         base = f"""
#         QPushButton {{
#             width: 56px; height:56px; border-radius:28px; 
            
#             font-weight: bold;
#             color: white;
#         }}
#         QPushButton:hover {{  }}
#         """
#         return base

#     def update_history(self):
#         # Populate filters (preserve current selection) and refresh table
#         rows = fetch_sprinkler_history()
#         prev_dev = self.filter_device.currentText() if self.filter_device.count()>0 else 'All'
#         prev_dec = self.filter_decision.currentText() if self.filter_decision.count()>0 else 'All'

#         unique_devices = sorted({row['device_id'] for row in rows})
#         unique_decisions = sorted({row['decision'] for row in rows})

#         # repopulate while preserving selection when possible
#         self.filter_device.blockSignals(True)
#         self.filter_decision.blockSignals(True)
#         self.filter_device.clear(); self.filter_device.addItem('All'); self.filter_device.addItems(unique_devices)
#         self.filter_decision.clear(); self.filter_decision.addItem('All'); self.filter_decision.addItems(unique_decisions)
#         idx = self.filter_device.findText(prev_dev)
#         if idx >= 0:
#             self.filter_device.setCurrentIndex(idx)
#         idx = self.filter_decision.findText(prev_dec)
#         if idx >= 0:
#             self.filter_decision.setCurrentIndex(idx)
#         self.filter_device.blockSignals(False)
#         self.filter_decision.blockSignals(False)

#         # apply currently selected filters to populate the table
#         self.apply_filters()

#     def apply_filters(self):
#         # fetch and filter rows locally
#         rows = fetch_sprinkler_history()
#         dev = self.filter_device.currentText()
#         dec = self.filter_decision.currentText()
#         if dev and dev != 'All':
#             rows = [r for r in rows if r.get('device_id') == dev]
#         if dec and dec != 'All':
#             rows = [r for r in rows if r.get('decision') == dec]

#         # date filter
#         try:
#             dfrom = self.filter_date_from.date().toPyDate()
#             dto = self.filter_date_to.date().toPyDate()
#             # only apply if user set meaningful range (non-default)
#             if dfrom and dto and dfrom <= dto:
#                 rows = [r for r in rows if r.get('ts') and dfrom <= r['ts'].date() <= dto]
#         except Exception:
#             pass

#         # numeric filters
#         try:
#             drymin = float(self.filter_dry_min.text()) if self.filter_dry_min.text() else None
#             confmin = float(self.filter_conf_min.text()) if self.filter_conf_min.text() else None
#             if drymin is not None:
#                 rows = [r for r in rows if r.get('dry_ratio', 0) >= drymin]
#             if confmin is not None:
#                 rows = [r for r in rows if r.get('confidence', 0) >= confmin]
#         except Exception:
#             pass

#         self.populate_history_table(rows)

#     def populate_history_table(self, rows):
#         self.history_table.setRowCount(0)
#         for row in rows:
#             r = self.history_table.rowCount()
#             self.history_table.insertRow(r)
#             self.history_table.setItem(r,0, QTableWidgetItem(str(row['ts'])))
#             self.history_table.setItem(r,1, QTableWidgetItem(row['device_id']))
#             dec_item = QTableWidgetItem(row['decision'])
#             if row['decision']=='run': dec_item.setBackground(QColor('#10b981'))
#             elif row['decision']=='stop': dec_item.setBackground(QColor('#ef4444'))
#             else: dec_item.setBackground(QColor('#f59e0b'))
#             self.history_table.setItem(r,2, dec_item)
#             self.history_table.setItem(r,3, QTableWidgetItem(f"{row['confidence']:.2f}"))
#             self.history_table.setItem(r,4, QTableWidgetItem(f"{row['dry_ratio']:.2f}"))
#             view_btn = QPushButton('View Image')
#             view_btn.clicked.connect(lambda _checked, rr=row: self.show_image_modal(rr))
#             self.history_table.setCellWidget(r,5, view_btn)

#     def show_image_modal(self, row):
#         # for demo: try to load an image from disk or show placeholder
#         img_path = script_dir / 'sprinkler_image_placeholder.jpg'
#         if img_path.exists():
#             pix = QPixmap(str(img_path))
#         else:
#             pix = QPixmap(400,300)
#             pix.fill(QColor('#ddd'))
#         m = ImageModal(self, pix, row)
#         m.exec()

#     def update_data(self):
#         try:
#             rows = fetch_sprinkler_data()
#             healthy = True
#         except Exception as e:
#             print('Error fetching data:', e)
#             import traceback
#             traceback.print_exc()
#             rows = []
#             healthy = False

#         # Update sprinklers on map
#         active_count = 0
#         irrigated_area = 0.0
#         last_update = '--'
#         max_timestamp = None
#         for i, row in enumerate(rows):
#             device_id = row['device_id']
#             dry_ratio = row['dry_ratio']
#             decision = row['decision']
#             confidence = row['confidence']
#             new_state = row['new_state']
#             active = new_state == 'run'
#             if active:
#                 active_count += 1
#             irrigated_area += dry_ratio if active else 0
            
#             # Track the most recent timestamp across all sprinklers
#             ts = row.get('ts')
#             if ts and (max_timestamp is None or ts > max_timestamp):
#                 max_timestamp = ts
            
#             # MapWidget handles display and GIF/image ONLY (no shapes)
#             if device_id not in self.map_widget.sprinklers:
#                 rel_x = (100 + i*120 + random.randint(-20, 20)) / max(1, self.map_widget.map_pixmap.width())
#                 rel_y = (300 + random.randint(-100, 100)) / max(1, self.map_widget.map_pixmap.height())
#                 rel_size = 0.025
#                 btn = self.map_widget.add_sprinkler(device_id, rel_x, rel_y, rel_size, active, name=device_id)
#                 try:
#                     btn.clicked.connect(lambda _e, d=device_id: self.show_details(d))
#                 except Exception as e:
#                     print(f"[ERROR] Failed to connect clicked signal for {device_id}: {e}")
            
#             s = self.map_widget.sprinklers[device_id]
#             # ALWAYS set sprinkler state on every update - ensures images/GIFs shown for new sprinklers added after startup
#             self.set_sprinkler_state(s, active)
#             s.update({'dry_ratio': dry_ratio, 'decision': decision, 'confidence': confidence})
#             # Update main window's sprinkler info for details dialog
#             self.sprinklers[device_id] = s
        
#         # Set last_update to the most recent timestamp
#         if max_timestamp:
#             last_update = str(max_timestamp)

#         total_area = len(rows)
#         irrigated_percent = (irrigated_area / total_area * 100) if total_area else 0.0
#         self.dashboard_bar.update_status(active_count, irrigated_percent, last_update, healthy)

#     def safe_update_data(self):
#         """Safe wrapper for update_data that catches exceptions"""
#         try:
#             self.update_data()
#         except Exception as e:
#             print(f"[ERROR] safe_update_data failed: {e}")
#             import traceback
#             traceback.print_exc()

#     def show_details(self, device_id):
#         print(f"[DEBUG] show_details() called for device_id={device_id}")
#         if device_id not in self.sprinklers:
#             print(f"[DEBUG] Device {device_id} not found in sprinklers dict")
#             return
#         # Close previous details dialog if open
#         if hasattr(self, '_details_card') and self._details_card:
#             print(f"[DEBUG] Closing previous details card")
#             self._details_card.close()
#         s = self.sprinklers[device_id]
#         details = {
#             'active': s.get('active', False),
#             'dry_ratio': s.get('dry_ratio', 0),
#             'confidence': s.get('confidence', 0),
#             'decision': s.get('decision', 'noop')
#         }
#         print(f"[DEBUG] Creating new SprinklerDetailsDialogNew with details: {details}")
#         # Use new tabbed dialog
#         card = SprinklerDetailsDialogNew(self, device_id, details)
#         card.history_requested.connect(lambda d: self.show_history_panel(d))
#         self._details_card = card
#         print(f"[DEBUG] Calling card.show()")
#         card.show()
#         print(f"[DEBUG] Dialog shown")

#     def show_history_panel(self, device_id):
#         # Close previous details dialog if open
#         if hasattr(self, '_details_card') and self._details_card:
#             self._details_card.close()
#         # Fetch last 10 records for this sprinkler
#         all_history = fetch_sprinkler_history(limit=100)
#         records = [r for r in all_history if r['device_id'] == device_id][:10]
#         self.history_panel.show_history(records)
#         self.history_panel.show()
#         self.map_widget.setFixedWidth(int(self.width() * 0.6))
#         # Add close button to history panel
#         if not hasattr(self.history_panel, 'close_btn'):
#             from PyQt6.QtWidgets import QPushButton
#             close_btn = QPushButton('Close History')
#             close_btn.setStyleSheet('background:#ef4444; color:white; padding:6px; border-radius:8px')
#             close_btn.clicked.connect(self.hide_history_panel)
#             layout = self.history_panel.layout()
#             layout.addWidget(close_btn)
#             self.history_panel.close_btn = close_btn

#     def hide_history_panel(self):
#         self.history_panel.hide()
#         self.map_widget.setFixedWidth(self.width())
#         # Ensure details dialog can be reopened after closing history
#         self._details_card = None

#     def on_history_clicked(self, row, col):
#         # show full details card when any non-button cell is clicked
#         try:
#             device = self.history_table.item(row,1).text()
#             if device:
#                 self.show_details(device)
#         except Exception:
#             pass

# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     window = IrrigationDashboard()
#     window.show()
#     sys.exit(app.exec())


from pathlib import Path
import sys, random
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QDialog, QFormLayout, QScrollArea,
    QComboBox, QLineEdit, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QDialogButtonBox, QGraphicsDropShadowEffect, QLabel
)
from .map_widget import MapWidget
from .history_panel import HistoryPanel
from .sprinkler_details_dialog_new import SprinklerDetailsDialogNew
from .dashboard_bar import DashboardBar
from PyQt6.QtGui import QPixmap, QMovie, QFont, QColor, QIcon
from PyQt6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QRect, QEasingCurve

import psycopg2
from psycopg2.extras import RealDictCursor

# ----------------------- DB helpers (unchanged) -----------------------
def get_db_connection():
    return psycopg2.connect(
        host="postgres",
        port=5432,
        user="missions_user",
        password="pg123",
        dbname="missions_db",
        cursor_factory=RealDictCursor
    )

# NOTE: original fetch functions retained (they must exist and behave the same)
# For brevity we keep their original implementations from the provided file.

def fetch_sprinkler_history(limit=500):
    query = f"""
        SELECT e.device_id, e.dry_ratio, e.decision, e.confidence, e.patch_count, e.extra,
               p.prev_state, e.ts
        FROM soil_moisture_events e
        LEFT JOIN irrigation_policies p ON e.device_id = p.device_id
        ORDER BY e.ts DESC
        LIMIT {limit}
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()

    for row in rows:
        prev_state = row.get('prev_state') or 'stop'
        decision = row['decision']
        if decision == "noop":
            new_state = prev_state
        elif decision in ("run", "stop"):
            new_state = decision
        else:
            new_state = "stop"
        row['prev_state'] = prev_state
        row['new_state'] = new_state

    return rows


def fetch_sprinkler_data():
    query = """
        SELECT e.device_id, e.dry_ratio, e.decision, e.confidence, e.patch_count, e.extra,
               e.ts, p.prev_state
        FROM soil_moisture_events e
        LEFT JOIN irrigation_policies p ON e.device_id = p.device_id
        WHERE e.ts = (
            SELECT MAX(ts)
            FROM soil_moisture_events e2
            WHERE e2.device_id = e.device_id
        )
        ORDER BY e.device_id
    """

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()

    for row in rows:
        prev_state = row.get('prev_state') or 'stop'
        decision = row['decision']
        if decision == "noop":
            new_state = prev_state
        elif decision in ("run", "stop"):
            new_state = decision
        else:
            new_state = "stop"
        row['prev_state'] = prev_state
        row['new_state'] = new_state

    return rows


script_dir = Path(__file__).parent

# # ----------------------- UI Components -----------------------
# class ImageModal(QDialog):
#     """Modal to show image with dark overlay and details"""
#     def __init__(self, parent, pixmap: QPixmap, details: dict):
#         super().__init__(parent)
#         self.setModal(True)
#         self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

#         self.main = QWidget(self)
#         self.main.setStyleSheet("background: white; border-radius: 12px;")
#         layout = QVBoxLayout(self.main)
#         self.main.setLayout(layout)

#         img_label = QLabel()
#         max_w = int(parent.width() * 0.8)
#         max_h = int(parent.height() * 0.8)
#         img_label.setPixmap(pixmap.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
#         img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         layout.addWidget(img_label)

#         info = QLabel(f"Timestamp: {details.get('ts')} — Decision: {details.get('decision')} — Confidence: {details.get('confidence'):.2f}")
#         layout.addWidget(info)

#         btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
#         btns.rejected.connect(self.close)
#         layout.addWidget(btns)

#         # position central
#         w, h = int(parent.width()*0.85), int(parent.height()*0.85)
#         self.setGeometry((parent.width()-w)//2, (parent.height()-h)//2, w, h)
#         self.main.setGeometry(0, 0, w, h)

class IrrigationDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Irrigation Dashboard 🌾")
        self.setGeometry(100, 100, 1100, 820)
        QApplication.setFont(QFont('Roboto', 10))
        main = QVBoxLayout(self)
        main.setContentsMargins(0,0,0,0)
        self.setStyleSheet("""
            QWidget#root { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0f9ff, stop:1 #e0f2fe); }
            QLabel.title { font-family: 'Segoe UI'; font-weight: bold; font-size: 18px; color: #111827 }
        """)
        self.setObjectName('root')

        # MapWidget replaces map logic
        self.dashboard_bar = DashboardBar(self)
        main.addWidget(self.dashboard_bar)
        self.map_widget = MapWidget(self, map_path=str(script_dir / "map_field.jpg"))
        self.sprinklers = {}  # device_id -> info, for non-map logic (details, etc.)
        self.history_panel = HistoryPanel(self)
        self.history_panel.hide()
        
        # Create map layout with minimal margins to push sprinklers down
        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)
        map_layout.setContentsMargins(0, 10, 0, 0)  # Minimal top margin (10px instead of default)
        map_layout.setSpacing(0)
        map_layout.addWidget(self.map_widget)
        
        main.addWidget(map_container, stretch=3)
        main.addWidget(self.history_panel, stretch=1)

        # timer for data refresh
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(3000)
        self.update_data()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Delegate map resizing to MapWidget
        if hasattr(self, 'map_widget') and self.map_widget:
            self.map_widget.resizeEvent(event)

    def set_sprinkler_state(self, s, active):
        #print(f"Setting sprinkler {s['name']} state to {'active' if active else 'inactive'}")
        btn: QPushButton = s['widget']
        # create / reuse label for movie
        if 'label' not in s:
            lbl = QLabel(btn)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setGeometry(0,0,btn.width(),btn.height())
            s['label'] = lbl
        lbl = s['label']

        if active:
            movie = QMovie(str(script_dir / 'sprinkler_on.gif'))
            movie.setScaledSize(QSize(btn.width(), btn.height()))
            lbl.setMovie(movie)
            movie.start()
            lbl.show()
            btn.setStyleSheet(self.sprinkler_style(active=True))
            s['movie'] = movie
        else:
            # static image
            pix = QPixmap(str(script_dir / 'sprinkler_off.png')) if (script_dir / 'sprinkler_off.png').exists() else QPixmap(btn.width(), btn.height())
            if pix.isNull():
                pix = QPixmap(btn.width(), btn.height()); pix.fill(QColor('#6b7280'))
            lbl.setPixmap(pix.scaled(btn.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            lbl.show()
            btn.setStyleSheet(self.sprinkler_style(active=False))
            s['movie'] = None
        s['active'] = active

    def sprinkler_style(self, active=False):
        #background: {"#86c7db26" if active else "#6b72801c"}; 
        # circular button with shadow and badge placeholder
        base = f"""
        QPushButton {{
            width: 120px; height:120px; border-radius:28px; 
            
            font-weight: bold;
            color: white;
        }}
        QPushButton:hover {{  }}
        """
        return base

    # def update_history(self):
    #     # Populate filters (preserve current selection) and refresh table
    #     rows = fetch_sprinkler_history()
    #     prev_dev = self.filter_device.currentText() if self.filter_device.count()>0 else 'All'
    #     prev_dec = self.filter_decision.currentText() if self.filter_decision.count()>0 else 'All'

    #     unique_devices = sorted({row['device_id'] for row in rows})
    #     unique_decisions = sorted({row['decision'] for row in rows})

    #     # repopulate while preserving selection when possible
    #     self.filter_device.blockSignals(True)
    #     self.filter_decision.blockSignals(True)
    #     self.filter_device.clear(); self.filter_device.addItem('All'); self.filter_device.addItems(unique_devices)
    #     self.filter_decision.clear(); self.filter_decision.addItem('All'); self.filter_decision.addItems(unique_decisions)
    #     idx = self.filter_device.findText(prev_dev)
    #     if idx >= 0:
    #         self.filter_device.setCurrentIndex(idx)
    #     idx = self.filter_decision.findText(prev_dec)
    #     if idx >= 0:
    #         self.filter_decision.setCurrentIndex(idx)
    #     self.filter_device.blockSignals(False)
    #     self.filter_decision.blockSignals(False)

    #     # apply currently selected filters to populate the table
    #     self.apply_filters()

    # def apply_filters(self):
    #     # fetch and filter rows locally
    #     rows = fetch_sprinkler_history()
    #     dev = self.filter_device.currentText()
    #     dec = self.filter_decision.currentText()
    #     if dev and dev != 'All':
    #         rows = [r for r in rows if r.get('device_id') == dev]
    #     if dec and dec != 'All':
    #         rows = [r for r in rows if r.get('decision') == dec]

    #     # date filter
    #     try:
    #         dfrom = self.filter_date_from.date().toPyDate()
    #         dto = self.filter_date_to.date().toPyDate()
    #         # only apply if user set meaningful range (non-default)
    #         if dfrom and dto and dfrom <= dto:
    #             rows = [r for r in rows if r.get('ts') and dfrom <= r['ts'].date() <= dto]
    #     except Exception:
    #         pass

    #     # numeric filters
    #     try:
    #         drymin = float(self.filter_dry_min.text()) if self.filter_dry_min.text() else None
    #         confmin = float(self.filter_conf_min.text()) if self.filter_conf_min.text() else None
    #         if drymin is not None:
    #             rows = [r for r in rows if r.get('dry_ratio', 0) >= drymin]
    #         if confmin is not None:
    #             rows = [r for r in rows if r.get('confidence', 0) >= confmin]
    #     except Exception:
    #         pass

    #     self.populate_history_table(rows)

    # def populate_history_table(self, rows):
    #     self.history_table.setRowCount(0)
    #     for row in rows:
    #         r = self.history_table.rowCount()
    #         self.history_table.insertRow(r)
    #         self.history_table.setItem(r,0, QTableWidgetItem(str(row['ts'])))
    #         self.history_table.setItem(r,1, QTableWidgetItem(row['device_id']))
    #         dec_item = QTableWidgetItem(row['decision'])
    #         if row['decision']=='run': dec_item.setBackground(QColor('#10b981'))
    #         elif row['decision']=='stop': dec_item.setBackground(QColor('#ef4444'))
    #         else: dec_item.setBackground(QColor('#f59e0b'))
    #         self.history_table.setItem(r,2, dec_item)
    #         self.history_table.setItem(r,3, QTableWidgetItem(f"{row['confidence']:.2f}"))
    #         self.history_table.setItem(r,4, QTableWidgetItem(f"{row['dry_ratio']:.2f}"))
    #         view_btn = QPushButton('View Image')
    #         view_btn.clicked.connect(lambda _checked, rr=row: self.show_image_modal(rr))
    #         self.history_table.setCellWidget(r,5, view_btn)

    # def show_image_modal(self, row):
    #     # for demo: try to load an image from disk or show placeholder
    #     img_path = script_dir / 'sprinkler_image_placeholder.jpg'
    #     if img_path.exists():
    #         pix = QPixmap(str(img_path))
    #     else:
    #         pix = QPixmap(400,300)
    #         pix.fill(QColor('#ddd'))
    #     m = ImageModal(self, pix, row)
    #     m.exec()

    def update_data(self):
        try:
            rows = fetch_sprinkler_data()
            healthy = True
        except Exception as e:
            print('Error fetching data:', e)
            rows = []
            healthy = False

        # Update sprinklers on map
        active_count = 0
        irrigated_area = 0.0
        last_update = '--'
        max_timestamp = None
        for i, row in enumerate(rows):
            device_id = row['device_id']
            dry_ratio = row['dry_ratio']
            decision = row['decision']
            confidence = row['confidence']
            new_state = row['new_state']
            active = new_state == 'run'
            if active:
                active_count += 1
            irrigated_area += dry_ratio if active else 0
            
            # Track the most recent timestamp across all sprinklers
            ts = row.get('ts')
            if ts and (max_timestamp is None or ts > max_timestamp):
                max_timestamp = ts
            
            # MapWidget handles display and GIF/image ONLY (no shapes)
            if device_id not in self.map_widget.sprinklers:
                rel_x = (100 + i*233 + random.randint(-20, 20)) / max(1, self.map_widget.map_pixmap.width())
                rel_y = (550 + random.randint(-230, 230)) / max(1, self.map_widget.map_pixmap.height())
                rel_size = 0.025
                btn = self.map_widget.add_sprinkler(device_id, rel_x, rel_y, rel_size, active, name=device_id)
                btn.clicked.connect(lambda _e, d=device_id: self.show_details(d))
            s = self.map_widget.sprinklers[device_id]
            # Always set sprinkler state to ensure image/GIF is shown, never fallback to shapes
            self.set_sprinkler_state(s, active)
            s.update({'dry_ratio': dry_ratio, 'decision': decision, 'confidence': confidence})
            # Update main window's sprinkler info for details dialog
            self.sprinklers[device_id] = s
        
        # Set last_update to the most recent timestamp
        if max_timestamp:
            last_update = str(max_timestamp)

        total_area = len(rows)
        irrigated_percent = (irrigated_area / total_area * 100) if total_area else 0.0
        self.dashboard_bar.update_status(active_count, irrigated_percent, last_update, healthy)

    def show_details(self, device_id):
        if device_id not in self.sprinklers:
            return
        # Close previous details dialog if open
        if hasattr(self, '_details_card') and self._details_card:
            self._details_card.close()
        s = self.sprinklers[device_id]
        details = {
            'active': s.get('active', False),
            'dry_ratio': s.get('dry_ratio', 0),
            'confidence': s.get('confidence', 0),
            'decision': s.get('decision', 'noop')
        }
        # Use new tabbed dialog
        card = SprinklerDetailsDialogNew(self, device_id, details)
        card.history_requested.connect(lambda d: self.show_history_panel(d))
        self._details_card = card
        card.show()

    # def show_history_panel(self, device_id):
    #     # Close previous details dialog if open
    #     if hasattr(self, '_details_card') and self._details_card:
    #         self._details_card.close()
    #     # Fetch last 10 records for this sprinkler
    #     all_history = fetch_sprinkler_history(limit=100)
    #     records = [r for r in all_history if r['device_id'] == device_id][:10]
    #     self.history_panel.show_history(records)
    #     self.history_panel.show()
    #     self.map_widget.setFixedWidth(int(self.width() * 0.6))
    #     # Add close button to history panel
    #     if not hasattr(self.history_panel, 'close_btn'):
    #         from PyQt6.QtWidgets import QPushButton
    #         close_btn = QPushButton('Close History')
    #         close_btn.setStyleSheet('background:#ef4444; color:white; padding:6px; border-radius:8px')
    #         close_btn.clicked.connect(self.hide_history_panel)
    #         layout = self.history_panel.layout()
    #         layout.addWidget(close_btn)
    #         self.history_panel.close_btn = close_btn

    # def hide_history_panel(self):
    #     self.history_panel.hide()
    #     self.map_widget.setFixedWidth(self.width())
    #     # Ensure details dialog can be reopened after closing history
    #     self._details_card = None

    # def on_history_clicked(self, row, col):
    #     # show full details card when any non-button cell is clicked
    #     try:
    #         device = self.history_table.item(row,1).text()
    #         if device:
    #             self.show_details(device)
    #     except Exception:
    #         pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = IrrigationDashboard()
    window.show()
    sys.exit(app.exec())
