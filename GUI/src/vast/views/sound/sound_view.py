from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QComboBox, QPushButton, QLineEdit, QDateEdit, 
    QFrame, QMessageBox, QTabWidget, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget, QSizePolicy, QCheckBox, QToolBar, QScrollArea
)
from PyQt6.QtCore import Qt, QDate, QUrl, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QColor, QCursor, QPainter, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWebEngineWidgets import QWebEngineView
from dashboard_api import DashboardApi
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from datetime import datetime, timedelta
from vast.dashboard_api import DashboardApi
import requests
import os
import math
import tempfile

MINIO_BASE = os.getenv("MINIO_PUBLIC_BASE", "http://minio-hot:9000")

def normalize_minio_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    url = url.lstrip("/")
    if url.startswith("sounds/"):
        url = "sound/" + url
    return f"{MINIO_BASE.rstrip('/')}/{url}"


# ==========================================================
#                 Audio Waveform Visualizer
# ==========================================================
class AudioWaveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setMaximumHeight(220)
        self.bars = []
        self.animation_offset = 0
        self.is_playing = False
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        
        self.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0f0c29, stop:0.5 #302b63, stop:1 #24243e);
            border: none;
            border-radius: 12px;
        """)
        
        self.default_text = "🎵 Press Play to Visualize Audio 🎵"
    
    def start_animation(self):
        self.is_playing = True
        self.bars = [0.2 + (i % 5) * 0.15 for i in range(100)]
        self.timer.start(40)
    
    def stop_animation(self):
        self.is_playing = False
        self.timer.stop()
        self.bars = []
        self.update()
    
    def animate(self):
        if not self.is_playing:
            return
        
        self.animation_offset = (self.animation_offset + 2) % 360
        
        for i in range(len(self.bars)):
            wave1 = math.sin((self.animation_offset + i * 8) * math.pi / 180)
            wave2 = math.cos((self.animation_offset + i * 12) * math.pi / 180)
            self.bars[i] = 0.25 + abs(wave1 * 0.35) + abs(wave2 * 0.25)
        
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        if not self.bars:
            painter.setPen(QColor(150, 180, 230, 200))
            font = painter.font()
            font.setPointSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(0, 0, width, height, 
                           Qt.AlignmentFlag.AlignCenter, 
                           self.default_text)
            return
        
        bar_width = width / len(self.bars)
        center_y = height / 2
        
        gradient_colors = [
            (QColor(102, 126, 234), QColor(118, 75, 162)),
            (QColor(67, 233, 123), QColor(56, 249, 215)),
            (QColor(251, 200, 212), QColor(151, 149, 240)),
            (QColor(250, 208, 196), QColor(255, 209, 255))
        ]
        
        for i, amplitude in enumerate(self.bars):
            x = i * bar_width
            bar_height = amplitude * (height - 30)
            y_top = center_y - bar_height / 2
            y_bottom = center_y + bar_height / 2
            
            gradient_idx = (i // 25) % len(gradient_colors)
            color1, color2 = gradient_colors[gradient_idx]
            
            from PyQt6.QtGui import QLinearGradient
            gradient = QLinearGradient(x, y_top, x, y_bottom)
            gradient.setColorAt(0, color1)
            gradient.setColorAt(1, color2)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            
            bar_rect_width = max(2, bar_width - 1.5)
            painter.drawRoundedRect(
                int(x + 0.75), int(y_top), 
                int(bar_rect_width), int(bar_height), 
                3, 3
            )
            
            glow = QColor(255, 255, 255, 30)
            painter.setBrush(glow)
            painter.drawRoundedRect(
                int(x + bar_width * 0.2), int(y_top + 2),
                int(bar_rect_width * 0.3), int(bar_height * 0.4),
                2, 2
            )


# ==========================================================
#                 Microphone Button Widget
# ==========================================================
class MicrophoneButton(QPushButton):
    def __init__(self, mic_id: str, mic_name: str, mic_type: str, parent=None):
        super().__init__(parent)
        self.mic_id = mic_id
        self.mic_name = mic_name
        self.mic_type = mic_type
        self.is_selected = False

        if mic_type == "audio":
            self.setFixedSize(70, 70)
            self.shape_style = "border-radius: 35px;"  
        else:
            self.setFixedSize(70, 70)
            self.shape_style = "border-radius: 8px;" 

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.base_color = "#000000"      
        self.selected_color = "#0078d4"  
        self.hover_color = "#222222"     
        self.disabled_color = "#888888"

        self.update_style()
        self.setText(f"{mic_id.upper()}")
        self.setToolTip(f"<b>{mic_name}</b><br>Type: {mic_type}<br>Click to select")

    def update_style(self):
        if not self.isEnabled():
            color = self.disabled_color
            border = "#555"
        elif self.is_selected:
            color = self.selected_color
            border = "#1e90ff"
        else:
            color = self.base_color
            border = "white"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: 3px solid {border};
                {self.shape_style}
                font-size: 15px;
                font-weight: bold;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: {self.hover_color};
            }}
        """)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update_style()

    def set_disabled_state(self, disabled: bool):
        self.setEnabled(not disabled)
        self.update_style()


# ==========================================================
#                 Interactive Map with Image
# ==========================================================
class ImageMapView(QWidget):
    def __init__(self, parent=None, api=None):
        super().__init__(parent)
        self.api = api  
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.selected_mics = []
        self.selected_type = None
        self.mic_buttons = {}

        self.stacked_widget = QStackedWidget()
        
        self.map_page = QWidget()
        layout = QVBoxLayout(self.map_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        control_panel = QFrame()
        control_panel.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #d1d5da;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        control_layout = QHBoxLayout(control_panel)
        
        self.selection_label = QLabel("Select microphones to view recordings")
        self.selection_label.setStyleSheet("font-weight: bold; color: #333;")
        
        self.view_button = QPushButton("View Selected Recordings")
        self.view_button.setEnabled(False)
        self.view_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.view_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
            }
        """)
        self.view_button.clicked.connect(self.view_selected_recordings)
        
        self.clear_button = QPushButton("✕ Clear Selection")
        self.clear_button.setEnabled(False)
        self.clear_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
            }
        """)
        self.clear_button.clicked.connect(self.clear_selection)
        
        control_layout.addWidget(self.selection_label)
        control_layout.addStretch()
        control_layout.addWidget(self.clear_button)
        control_layout.addWidget(self.view_button)

        subtitle = QLabel("Click on microphones to select them (same type only)")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #666; padding: 5px;")

        self.map_container = QWidget()
        self.map_container.setMinimumSize(800, 600)
        self.map_container.setStyleSheet("""
            background-color: #e8f4f8;
            border: 3px solid #4A90E2;
            border-radius: 15px;
        """)

        self.background_label = QLabel(self.map_container)
        self.background_label.setGeometry(0, 0, 800, 600)
        self.background_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._load_map_image()

        self.microphones = [
            {"id": "MIC-01", "name": "Environment Mic", "type": "audio", "position": (200, 150)},
            {"id": "MIC-02", "name": "Plant Ultrasound", "type": "ultrasound", "position": (500, 300)},
            {"id": "MIC-03", "name": "Environment Mic", "type": "audio", "position": (350, 450)}
        ]

        for mic in self.microphones:
            btn = MicrophoneButton(mic["id"], mic["name"], mic["type"], self.map_container)
            btn.move(mic["position"][0], mic["position"][1])
            btn.clicked.connect(lambda checked, m=mic, b=btn: self.on_microphone_clicked(m, b))
            self.mic_buttons[mic["id"]] = btn

        legend = QLabel("🎤 circle = Audio Sensor  •  🔊 square = Ultrasound Sensor")
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend.setStyleSheet("""
            font-size: 14px;
            font-weight: 500;
            padding: 10px;
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            color: #333;
        """)

        layout.addWidget(control_panel)
        layout.addWidget(subtitle)
        layout.addWidget(self.map_container, 1)
        layout.addWidget(legend)

        self.stacked_widget.addWidget(self.map_page)
        self.recordings_page = None
        
        self.main_layout.addWidget(self.stacked_widget)

    def _load_map_image(self):
        possible_paths = [
            "map_background.png",
            "./map_background.png",
            "../map_background.png",
            os.path.join(os.getcwd(), "map_background.png"),
            os.path.join(os.path.dirname(__file__), "map_background.png")
        ]
        
        image_loaded = False
        for path in possible_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, 
                                          Qt.TransformationMode.SmoothTransformation)
                    self.background_label.setPixmap(scaled)
                    image_loaded = True
                    break
        
        if not image_loaded:
            self.background_label.setStyleSheet("font-size: 16px; color: #888; background-color: #d0e8f2;")
            self.background_label.setText("Sensor Locations\n\n(Map image not found)")

    def on_microphone_clicked(self, mic_data, button):
        mic_id = mic_data["id"]
        mic_type = mic_data["type"]
        
        if mic_id in self.selected_mics:
            self.selected_mics.remove(mic_id)
            button.set_selected(False)
            
            if not self.selected_mics:
                self.selected_type = None
                self.enable_all_buttons()
            
            self.update_selection_display()
            return
        
        if self.selected_type is None:
            self.selected_type = mic_type
            self.disable_other_type_buttons(mic_type)
        
        if mic_type == self.selected_type:
            self.selected_mics.append(mic_id)
            button.set_selected(True)
            self.update_selection_display()
    
    def disable_other_type_buttons(self, allowed_type):
        for mic in self.microphones:
            if mic["type"] != allowed_type:
                self.mic_buttons[mic["id"]].set_disabled_state(True)
    
    def enable_all_buttons(self):
        for btn in self.mic_buttons.values():
            btn.set_disabled_state(False)
    
    def clear_selection(self):
        self.selected_mics = []
        self.selected_type = None
        for btn in self.mic_buttons.values():
            btn.set_selected(False)
            btn.set_disabled_state(False)
        self.update_selection_display()
    
    def update_selection_display(self):
        count = len(self.selected_mics)
        if count == 0:
            self.selection_label.setText("Select microphones to view recordings")
            self.view_button.setEnabled(False)
            self.clear_button.setEnabled(False)
        else:
            type_text = "Audio" if self.selected_type == "audio" else "Ultrasound"
            self.selection_label.setText(
                f"Selected {count} {type_text} microphone(s): {', '.join([m.upper() for m in self.selected_mics])}"
            )
            self.view_button.setEnabled(True)
            self.clear_button.setEnabled(True)
    
    def view_selected_recordings(self):
        if not self.selected_mics:
            return
        
        selected_mic_data = [mic for mic in self.microphones if mic["id"] in self.selected_mics]
        
        if self.recordings_page:
            self.stacked_widget.removeWidget(self.recordings_page)
            self.recordings_page.deleteLater()
        
        self.recordings_page = QWidget()
        recordings_layout = QVBoxLayout(self.recordings_page)
        recordings_layout.setContentsMargins(0, 0, 0, 0)
        recordings_layout.setSpacing(0)
        
        header_container = QWidget()
        color = "#4A90E2" if self.selected_type == "audio" else "#50C878"
        header_container.setStyleSheet(f"background-color: {color};")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 10, 10, 10)
        
        back_button = QPushButton("← Back to Map")
        back_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.3); }
        """)
        back_button.clicked.connect(self.show_map)
        
        mic_names = ", ".join([m["name"] for m in selected_mic_data])
        header = QLabel(f"Recordings: {mic_names}")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        
        header_layout.addWidget(back_button)
        header_layout.addWidget(header, 1)
        header_layout.addStretch()

        type_text = "AUDIO" if self.selected_type == "audio" else "ULTRASOUND"
        mic_ids = ", ".join([m["id"].upper() for m in selected_mic_data])
        subtitle = QLabel(f"Type: {type_text}  •  Microphones: {mic_ids}")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("""
            font-size: 13px; color: white; padding: 5px;
            background-color: rgba(0, 0, 0, 0.2);
        """)

        recordings_layout.addWidget(header_container)
        recordings_layout.addWidget(subtitle)

        mic_ids_list = [m["id"] for m in selected_mic_data]
        sound_tab = RecordingsTab(
            mic_ids=mic_ids_list,
            recording_type=self.selected_type,
            parent=self,
            api=self.api, 
        )
        recordings_layout.addWidget(sound_tab)

        self.stacked_widget.addWidget(self.recordings_page)
        self.stacked_widget.setCurrentWidget(self.recordings_page)
    
    def show_map(self):
        self.stacked_widget.setCurrentWidget(self.map_page)


# ==========================================================
#                      Recordings Tab
# ==========================================================
class RecordingsTab(QWidget):
    def __init__(self, mic_ids=None, recording_type="audio", parent=None, api=None):
        super().__init__(parent)
        self.mic_ids = mic_ids if mic_ids else []
        self.recording_type = recording_type
        self.api = api

        if recording_type == "ultrasound":
            self.api_url = "http://db_api_service:8001/api/files/plant-predictions/"
        else:
            self.api_url = "http://db_api_service:8001/api/files/audio-aggregates/"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        filter_frame = self._create_filter_frame()
        
        list_label = QLabel("Available Recordings")
        list_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; padding: 5px;")

        self.file_table = self._create_table()
        
        waveform_container = self._create_waveform_container()

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 13px; color: #666; padding: 8px;
            background-color: #f6f8fa; border-radius: 6px; border: 1px solid #d1d5da;
        """)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)
        self._current_temp_file = None
        self._current_play_btn = None
        self._current_stop_btn = None

        layout.addWidget(filter_frame)
        layout.addWidget(list_label)
        layout.addWidget(self.file_table, 1)

        if self.recording_type == "audio":
            layout.addWidget(waveform_container)

        layout.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.update_list)
        self.update_list()

    def _create_filter_frame(self):
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame { background-color: #ffffff; border-radius: 12px; padding: 15px; }
        """)
        filters_layout = QVBoxLayout(filter_frame)
        filters_layout.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.setContentsMargins(0, 0, 0, 0)

        type_label = QLabel("Type:")
        type_label.setStyleSheet("font-weight: bold; color: #333; font-size: 11px;")
        filter_row.addWidget(type_label)

        self.noise_filter = QComboBox()
        self.noise_filter.setMaximumWidth(180)
        self.noise_filter.setStyleSheet("""
            QComboBox { 
                padding: 6px 10px; 
                border: 1px solid #d1d5da; 
                border-radius: 4px;
                background: white; 
                font-size: 12px;
            }
            QComboBox:hover { border: 1px solid #4A90E2; }
        """)

        if self.recording_type == "ultrasound":
            self.noise_filter.addItems([
                "All signals", "Drought-stressed plant", 
                "Empty Pot", "Greenhouse Noises"
            ])
        else:
            self.noise_filter.addItems([
                "All types", "predatory_animals", "non_predatory_animals",
                "birds", "fire", "footsteps", "insects", "screaming", 
                "shotgun", "stormy_weather", "streaming_water", "vehicle", "Other"
            ])

        filter_row.addWidget(self.noise_filter)

        date_label = QLabel("  From:")
        date_label.setStyleSheet("font-weight: bold; color: #333; font-size: 11px;")
        filter_row.addWidget(date_label)

        today = QDate.currentDate()
        first_day = QDate(today.year(), today.month(), 1)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(first_day)
        self.date_from.setMaximumWidth(120)
        self.date_from.setStyleSheet("""
            QDateEdit { 
                padding: 6px 8px; 
                border: 1px solid #d1d5da;
                border-radius: 4px; 
                background: white;
                font-size: 12px;
            }
        """)
        filter_row.addWidget(self.date_from)

        filter_row.addWidget(QLabel("→"))

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(today)
        self.date_to.setMaximumWidth(120)
        self.date_to.setStyleSheet(self.date_from.styleSheet())
        filter_row.addWidget(self.date_to)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search filename...")
        self.search_box.setMaximumWidth(200)
        self.search_box.setStyleSheet("""
            QLineEdit { 
                padding: 6px 10px; 
                border: 1px solid #d1d5da; 
                border-radius: 4px;
                background: white; 
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #4A90E2; }
        """)
        filter_row.addWidget(self.search_box)

        filter_row.addStretch()

        filter_row.addWidget(QLabel("sort by:"))
        self.sort_by = QComboBox()
        self.sort_by.addItems(["date", "name", "device"])
        self.sort_by.setMaximumWidth(130)
        self.sort_by.setStyleSheet("""
            QComboBox {
                padding: 6px 10px;
                border: 1px solid #d1d5da;
                border-radius: 4px;
                background: white;
                font-size: 12px;
            }
        """)
        filter_row.addWidget(self.sort_by)

        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.refresh_button.setStyleSheet("""
            QPushButton { 
                background-color: #4A90E2; 
                color: white; 
                border-radius: 6px;
                padding: 8px 16px; 
                font-weight: bold; 
                font-size: 12px;
            }
            QPushButton:hover { background-color: #357ABD; }
        """)
        filter_row.addWidget(self.refresh_button)

        filters_layout.addLayout(filter_row)
        
        return filter_frame

    def _create_table(self):
        table = QTableWidget()

        if self.recording_type == "ultrasound":
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels([
                "File", "Device", "Predicted Label", "Confidence", "Watering Status", "Format"
            ])
        else:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels([
                "File", "Device", "Predicted Label", "Probability", "Format", "Actions"
            ])

        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for i in range(table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        table.setStyleSheet("""
            QTableWidget {
                background: #ffffff;
                border: 2px solid #d1d5da;
                border-radius: 10px;
                gridline-color: #e1e4e8;
                font-size: 14px;
            }
            QTableWidget::item { padding: 8px; }
            QTableWidget::item:hover { background-color: #f6f8fa; }
            QTableWidget::item:selected { background-color: #d6eaff; color: #0366d6; }
            QHeaderView::section {
                background-color: #f6f8fa;
                padding: 10px;
                border: 1px solid #d1d5da;
                font-weight: bold;
                color: #24292e;
            }
        """)

        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        
        return table

    def _create_waveform_container(self):
        waveform_container = QFrame()
        waveform_container.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

        waveform_layout = QVBoxLayout(waveform_container)
        waveform_layout.setSpacing(5)
        
        self.waveform = AudioWaveform()
        self.waveform.setMinimumHeight(100)
        self.waveform.setMaximumHeight(120)
        
        waveform_layout.addWidget(self.waveform)
        
        return waveform_container
    
    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.waveform.start_animation()
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self.waveform.stop_animation()
            if self.status_label.text().startswith("Playing:"):
                self.status_label.setText("Finished")
            if hasattr(self, '_current_play_btn') and self._current_play_btn:
                self._reset_button_pair(self._current_play_btn, self._current_stop_btn)
                self._current_play_btn = None
                self._current_stop_btn = None

    def _map_ultrasound_label(self, raw: str) -> str:
        if not raw:
            return "Unknown"
        lower = raw.lower()
        if "tomato" in lower or "tobacco" in lower:
            return "Drought-stressed plant"
        return raw

    def update_list(self):
        self.file_table.setRowCount(0)
        self.file_table.verticalHeader().setDefaultSectionSize(60)
        self.status_label.setText("Loading...")

        params = {
            "date_from": self.date_from.date().toString("yyyy-MM-dd"),
            "date_to": self.date_to.date().toString("yyyy-MM-dd"),
            "search": self.search_box.text().strip(),
            "sort_by": self.sort_by.currentText(),
            "limit": 100
        }
        
        filter_value = self.noise_filter.currentText()
        if self.recording_type == "ultrasound":
            if filter_value in ("Empty Pot", "Greenhouse Noises"):
                params["predicted_class"] = filter_value
        else:
            if filter_value not in ("All types", "All signals"):
                params["type"] = filter_value
        
        if self.mic_ids:
            params["device_ids"] = ",".join(self.mic_ids)
        
        try:
            # Check if API is available and authenticated
            if not self.api or not hasattr(self.api, 'http'):
                self.status_label.setText("⚠ API connection not available")
                QMessageBox.warning(
                    self, 
                    "Authentication Required",
                    "Please login first to access recordings."
                )
                return
            
            # Use the authenticated session
            response = self.api.http.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            print(f"[DEBUG] Successfully fetched {len(data)} records from {self.api_url}")
            for f in data:
                row = self.file_table.rowCount()
                self.file_table.insertRow(row)
                self.file_table.setRowHeight(row, 60)

                filename = f.get("filename") or f.get("file", "")
                is_compressed = f.get("is_compressed", False)
                
                text_color = QColor("#888888") if is_compressed else QColor("#000000")

                if self.recording_type == "ultrasound":
                    device_id = f.get("device_id", "N/A")
                    pred_class_raw = f.get("predicted_class", "Unknown")
                    pred_class = self._map_ultrasound_label(pred_class_raw)
                    confidence = f.get("confidence", 0)
                    watering_status = f.get("watering_status", "N/A")
                    url = normalize_minio_url(f.get("url", ""))

                    format_str = "OPUS (Compressed)" if is_compressed else "WAV (Original)"

                    item0 = QTableWidgetItem(filename)
                    item0.setForeground(text_color)
                    self.file_table.setItem(row, 0, item0)
                    
                    item1 = QTableWidgetItem(device_id)
                    item1.setForeground(text_color)
                    self.file_table.setItem(row, 1, item1)
                    
                    item2 = QTableWidgetItem(pred_class)
                    item2.setForeground(text_color)
                    self.file_table.setItem(row, 2, item2)
                    
                    item3 = QTableWidgetItem(f"{confidence:.2%}")
                    item3.setForeground(text_color)
                    self.file_table.setItem(row, 3, item3)
                    
                    item4 = QTableWidgetItem(watering_status)
                    item4.setForeground(text_color)
                    self.file_table.setItem(row, 4, item4)
                    
                    item5 = QTableWidgetItem(format_str)
                    item5.setForeground(text_color)
                    self.file_table.setItem(row, 5, item5)
                else:
                    device_id = f.get("device_id", "N/A")
                    label = f.get("predicted_label", "Unknown")
                    prob = f.get("probability", 0)
                    url = normalize_minio_url(f.get("url", ""))

                    format_str = "OPUS (Compressed)" if is_compressed else "WAV (Original)"

                    item0 = QTableWidgetItem(filename)
                    item0.setForeground(text_color)
                    self.file_table.setItem(row, 0, item0)
                    
                    item1 = QTableWidgetItem(device_id)
                    item1.setForeground(text_color)
                    self.file_table.setItem(row, 1, item1)
                    
                    item2 = QTableWidgetItem(label)
                    item2.setForeground(text_color)
                    self.file_table.setItem(row, 2, item2)
                    
                    item3 = QTableWidgetItem(f"{prob:.2%}")
                    item3.setForeground(text_color)
                    self.file_table.setItem(row, 3, item3)
                    
                    item4 = QTableWidgetItem(format_str)
                    item4.setForeground(text_color)
                    self.file_table.setItem(row, 4, item4)

                if self.recording_type == "audio":
                    control_widget = QWidget()
                    control_layout = QHBoxLayout(control_widget)
                    control_layout.setContentsMargins(2, 2, 2, 2)
                    control_layout.setSpacing(6)

                    play_btn = QPushButton("▶")
                    play_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    play_btn.setFixedSize(35, 30)

                    if is_compressed:
                        play_btn.setStyleSheet("""
                            QPushButton {
                                background-color: #888888;
                                color: white;
                                border-radius: 4px;
                                font-weight: bold;
                            }
                            QPushButton:hover:enabled { background-color: #666666; }
                            QPushButton:disabled { background-color: #cccccc; color: #888888; }
                        """)
                        play_btn.setToolTip("Compressed OPUS file - may have compatibility issues")
                    else:
                        play_btn.setStyleSheet("""
                            QPushButton {
                                background-color: #0078d4;
                                color: white;
                                border-radius: 4px;
                                font-weight: bold;
                            }
                            QPushButton:hover:enabled { background-color: #005fa3; }
                            QPushButton:disabled { background-color: #cccccc; color: #888888; }
                        """)

                    stop_btn = QPushButton("⏹")
                    stop_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    stop_btn.setFixedSize(35, 30)
                    stop_btn.setEnabled(False)
                    stop_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #6c757d;
                            color: white;
                            border-radius: 4px;
                            font-weight: bold;
                        }
                        QPushButton:disabled { background-color: #b0b0b0; }
                        QPushButton:hover:enabled { background-color: #c82333; }
                    """)

                    play_btn.setProperty("row", row)
                    stop_btn.setProperty("row", row)

                    play_btn.clicked.connect(
                        lambda checked=False, u=url, fname=filename, pb=play_btn, sb=stop_btn, compressed=is_compressed: 
                        self.play_row_audio(u, fname, pb, sb, compressed)
                    )
                    stop_btn.clicked.connect(
                        lambda checked=False, pb=play_btn, sb=stop_btn: 
                        self.stop_row_audio(pb, sb)
                    )

                    control_layout.addWidget(play_btn)
                    control_layout.addWidget(stop_btn)

                    self.file_table.setCellWidget(row, 5, control_widget)

            if self.file_table.rowCount() == 0:
                self.file_table.insertRow(0)
                empty_item = QTableWidgetItem("No recordings found")
                empty_item.setForeground(QColor("#999"))
                self.file_table.setItem(0, 0, empty_item)
                self.file_table.setSpan(0, 0, 1, 6)

            self.status_label.setText(f"✓ Loaded {len(data)} recordings")

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                self.status_label.setText("⚠ Authentication required")
                QMessageBox.warning(self, "Authentication Error", 
                                "API requires authentication. Please check your credentials.")
            else:
                self.status_label.setText(f"⚠ HTTP Error {e.response.status_code}")
                QMessageBox.warning(self, "HTTP Error", 
                                f"Server returned error {e.response.status_code}:\n{str(e)}")
        except requests.exceptions.Timeout:
            self.status_label.setText("⚠ Request timeout")
            QMessageBox.warning(self, "Timeout", "Request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            self.status_label.setText("⚠ Connection error")
            QMessageBox.warning(self, "Connection Error", 
                            "Could not connect to server. Check your connection.")
        except Exception as e:
            self.status_label.setText("⚠ Error loading data")
            QMessageBox.warning(self, "Error", f"Failed to load recordings:\n{str(e)}")
                
    def play_row_audio(self, url, filename, play_btn, stop_btn, is_compressed=False):
        if not url:
            QMessageBox.warning(self, "No URL", "Audio file URL not available")
            return
        
        self.player.stop()
        self.waveform.stop_animation()
        
        try:
            if self._current_temp_file:
                if os.path.exists(self._current_temp_file):
                    os.remove(self._current_temp_file)
        except Exception:
            pass
        self._current_temp_file = None
        
        playback_url = url
        if url.startswith("http://localhost") or url.startswith("http://127.0.0.1"):
            parts = url.split("/", 3)
            if len(parts) > 3:
                path = parts[3]
                playback_url = f"http://minio-hot:9000/{path}"
        
        if is_compressed:
            reply = QMessageBox.question(
                self,
                "Compressed File",
                "This is a compressed OPUS file. Playback may not work properly.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        try:
            session = self.api.http if (self.api and getattr(self.api, "http", None)) else requests
            resp = session.get(playback_url, timeout=15)
            resp.raise_for_status()
            suffix = ".ogg" if is_compressed else ".wav"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(resp.content)
            tmp.flush()
            tmp_path = tmp.name
            tmp.close()
            self._current_temp_file = tmp_path
        except requests.exceptions.RequestException as e:
            self.status_label.setText("⚠ Unable to download file")
            QMessageBox.warning(self, "Download Error", f"Could not download audio file:\n{e}")
            return
        except Exception as e:
            self.status_label.setText("⚠ Error downloading file")
            QMessageBox.warning(self, "Error", f"Failed to download audio file:\n{e}")
            return
        
        try:
            self._reset_all_buttons()
            
            play_btn.setEnabled(False)
            play_btn.setStyleSheet("""
                QPushButton {
                    background-color: #888888;
                    color: white;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            
            stop_btn.setEnabled(True)
            stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #c82333; }
            """)
            
            self.player.setSource(QUrl.fromLocalFile(self._current_temp_file))
            self.player.play()
            self.waveform.start_animation()
            self.status_label.setText(f"Playing: {filename}")
            
            self._current_play_btn = play_btn
            self._current_stop_btn = stop_btn
            
        except Exception as e:
            self.status_label.setText("⚠ Playback error")
            QMessageBox.warning(self, "Playback Error", f"Playback failed:\n{e}")
            self._reset_all_buttons()

    def stop_row_audio(self, play_btn, stop_btn):
        self.player.stop()
        self.waveform.stop_animation()
        self.status_label.setText("⏹ Stopped")
        self._reset_button_pair(play_btn, stop_btn)

    def _reset_button_pair(self, play_btn, stop_btn):
        if play_btn.toolTip() and "Compressed" in play_btn.toolTip():
             play_btn.setStyleSheet("""
                QPushButton {
                    background-color: #888888;
                    color: white;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover:enabled { background-color: #666666; }
                QPushButton:disabled { background-color: #cccccc; color: #888888; }
            """)
        else:
            play_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0078d4;
                    color: white;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover:enabled { background-color: #005fa3; }
                QPushButton:disabled { background-color: #cccccc; color: #888888; }
            """)
        play_btn.setEnabled(True)
        
        stop_btn.setEnabled(False)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:disabled { background-color: #b0b0b0; }
            QPushButton:hover:enabled { background-color: #c82333; }
        """)

    def _reset_all_buttons(self):
        if self.recording_type != "audio":
            return
        
        actions_col = 5
        for row in range(self.file_table.rowCount()):
            widget = self.file_table.cellWidget(row, actions_col)
            if widget:
                layout = widget.layout()
                if layout and layout.count() >= 2:
                    play_btn = layout.itemAt(0).widget()
                    stop_btn = layout.itemAt(1).widget()
                    if play_btn and stop_btn and isinstance(play_btn, QPushButton):
                        self._reset_button_pair(play_btn, stop_btn)


# ==========================================================
# Sound Analytics View - NEW TAB from first document
# ==========================================================
class SoundAnalyticsView(QWidget):
    """Sound detection dashboard with filtering by time range and sound type"""
    
    SOUND_TYPES = [
        "non_predatory_animals",
        "predatory_animals",
        "birds",
        "fire",
        "footsteps",
        "insects",
        "screaming",
        "shotgun",
        "stormy_weather",
        "streaming_water",
        "vehicle"
    ]
    
    CYAN_PALETTE = [
        '#003366', '#004d99', '#0066cc', '#1a80e5',
        '#3399ff', '#53A0E5', '#66b3ff', '#80ccff',
        '#99e6ff', '#b3f0ff', '#ccf7ff'
    ]
    
    PRIMARY_CYAN = '#53A0E5'
    ACCENT_CYAN = '#3399ff'
    
    LIGHT_THEME = {
        'bg': '#f8f9fa',
        'card': '#ffffff',
        'text': '#333333',
        'border': '#e0e0e0',
        'primary': PRIMARY_CYAN,
        'accent': ACCENT_CYAN
    }
    
    DARK_THEME = {
        'bg': '#1e1e1e',
        'card': '#2d2d2d',
        'text': '#e0e0e0',
        'border': '#444444',
        'primary': '#64B5F6',
        'accent': ACCENT_CYAN
    }
    
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api

        # בדיקה ראשונית
        print(f"[INIT] API object: {self.api}", flush=True)
        print(f"[INIT] API has http: {hasattr(self.api, 'http')}", flush=True)
        
        # נסה לבדוק connection
        try:
            test_query = "SELECT 1 as test"
            result = self.api.run_query(test_query)
            print(f"[INIT] DB test result: {result}", flush=True)
        except Exception as e:
            print(f"[INIT] DB connection error: {e}", flush=True)

        self.current_time_range = 'day'
        self.current_sound_types = []
        self.is_dark_theme = False
        self.current_theme = self.LIGHT_THEME.copy()
        
        self.setWindowTitle("Sound Detection Analytics")
        self.setMinimumSize(QSize(1350, 1000))

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        content_frame = QFrame()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)

        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        filter_frame.setMaximumHeight(450)
        filter_layout = QVBoxLayout()
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(15)

        time_row = QHBoxLayout()
        time_label = QLabel("Time Range:")
        time_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        time_row.addWidget(time_label)
        self.time_filter = QComboBox()
        self.time_filter.addItems(['1 Day', '1 Week', '1 Month'])
        self.time_filter.setCurrentText('1 Day')
        self.time_filter.currentTextChanged.connect(self._on_filter_changed)
        self.time_filter.setMinimumWidth(140)
        time_row.addWidget(self.time_filter)
        time_row.addStretch()
        filter_layout.addLayout(time_row)

        sound_header_row = QHBoxLayout()
        sound_label = QLabel("Sound Types (select multiple):")
        sound_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        sound_header_row.addWidget(sound_label)

        self.selection_label = QLabel("All sounds selected")
        self.selection_label.setStyleSheet(f"color: {self.PRIMARY_CYAN}; font-weight: bold;")
        sound_header_row.addWidget(self.selection_label)
        sound_header_row.addStretch()

        clear_btn = QPushButton("Clear All")
        clear_btn.setMaximumWidth(100)
        clear_btn.clicked.connect(self._clear_sound_selection)
        sound_header_row.addWidget(clear_btn)

        apply_btn = QPushButton("Apply Filter")
        apply_btn.setMaximumWidth(100)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.PRIMARY_CYAN};
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.CYAN_PALETTE[2]};
            }}
        """)
        apply_btn.clicked.connect(self._refresh_data)
        sound_header_row.addWidget(apply_btn)
        filter_layout.addLayout(sound_header_row)

        checkbox_container = QFrame()
        checkbox_container.setObjectName("checkboxContainer")
        checkbox_container.setStyleSheet(f"""
            QFrame#checkboxContainer {{
                background-color: white;
                border: 2px solid {self.PRIMARY_CYAN};
                border-radius: 6px;
                max-height: 350px;
            }}
        """)
        checkbox_layout = QGridLayout()
        checkbox_layout.setSpacing(5)
        checkbox_layout.setContentsMargins(10, 10, 10, 10)

        self.sound_checkboxes = {}
        for idx, sound_name in enumerate(self.SOUND_TYPES):
            checkbox = QCheckBox(sound_name)
            checkbox.stateChanged.connect(self._on_sound_checkbox_changed)
            self.sound_checkboxes[sound_name] = checkbox
            row = idx // 3
            col = idx % 3
            checkbox_layout.addWidget(checkbox, row, col)

        checkbox_container.setLayout(checkbox_layout)
        filter_layout.addWidget(checkbox_container)
        filter_frame.setLayout(filter_layout)
        content_layout.addWidget(filter_frame)

        calendar_frame = self._create_activity_calendar()
        content_layout.addWidget(calendar_frame)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def make_chart_frame(title, canvas):
            frame = self._create_chart_frame(title, canvas)
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            frame.setMinimumHeight(320)
            frame.setMaximumHeight(320)
            return frame

        self.dist_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Sound Distribution (Count)", self.dist_canvas), 0, 0)

        self.timeline_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Detection Timeline", self.timeline_canvas), 0, 1)

        self.heatmap_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Sound Heatmap - Activity Patterns", self.heatmap_canvas), 1, 0)

        self.correlation_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Correlation Explorer", self.correlation_canvas), 1, 1)

        self.confidence_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Model Health Monitor", self.confidence_canvas), 2, 0)

        stats_frame = self._create_stats_frame()
        stats_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        stats_frame.setMinimumHeight(320)
        stats_frame.setMaximumHeight(320)
        grid.addWidget(stats_frame, 2, 1)

        content_layout.addLayout(grid, stretch=10)
        content_frame.setLayout(content_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(content_frame)

        main_layout.addWidget(scroll_area)
        self.setLayout(main_layout)

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(30000)

        self._refresh_data()
    
    def _create_activity_calendar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        frame.setMaximumHeight(120)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        title = QLabel("Activity Calendar (Last 30 Days)")
        title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(title)
        
        calendar_grid = QHBoxLayout()
        calendar_grid.setSpacing(2)
        
        today = datetime.now().date()
        for i in range(30):
            date = today - timedelta(days=29-i)
            day_box = QFrame()
            day_box.setMinimumSize(QSize(20, 20))
            day_box.setMaximumSize(QSize(20, 20))
            
            intensity = np.random.rand()
            color = self._get_intensity_color(intensity)
            
            day_box.setStyleSheet(f"""
                QFrame {{
                    background-color: {color};
                    border: 1px solid #ddd;
                    border-radius: 2px;
                }}
            """)
            
            day_label = QLabel(str(date.day))
            day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_label.setFont(QFont("Arial", 6))
            day_layout = QVBoxLayout()
            day_layout.setContentsMargins(0, 0, 0, 0)
            day_layout.addWidget(day_label)
            day_box.setLayout(day_layout)
            
            calendar_grid.addWidget(day_box)
        
        calendar_grid.addStretch()
        layout.addLayout(calendar_grid)
        frame.setLayout(layout)
        return frame
    
    def _get_intensity_color(self, intensity: float) -> str:
        if intensity < 0.2:
            return self.CYAN_PALETTE[0]
        elif intensity < 0.4:
            return self.CYAN_PALETTE[2]
        elif intensity < 0.6:
            return self.CYAN_PALETTE[4]
        elif intensity < 0.8:
            return self.CYAN_PALETTE[7]
        else:
            return self.CYAN_PALETTE[10]
    
    def _create_canvas(self, figsize=(5.5, 4.5)):
        canvas = FigureCanvas(Figure(figsize=figsize, dpi=90))
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return canvas
    
    def _create_chart_frame(self, title: str, widget: QWidget) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {self.PRIMARY_CYAN}; margin-bottom: 4px;")
        layout.addWidget(title_label)
        
        layout.addWidget(widget, 1)
        frame.setLayout(layout)
        return frame
    
    def _create_stats_frame(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        title_label = QLabel("Statistics")
        title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {self.PRIMARY_CYAN}; margin-bottom: 6px;")
        layout.addWidget(title_label)
        
        stats_grid = QGridLayout()
        stats_grid.setSpacing(10)
        stats_grid.setRowStretch(0, 1)
        stats_grid.setRowStretch(1, 1)
        stats_grid.setColumnStretch(0, 1)
        stats_grid.setColumnStretch(1, 1)
        
        self.stat_boxes = {}
        
        stat_names = [
            ("Total Files", "total_files"),
            ("Unknown Type", "unknown_count"),
            ("Avg Confidence", "avg_confidence"),
            ("Avg Processing", "avg_processing_ms")
        ]
        
        for idx, (label, key) in enumerate(stat_names):
            row = idx // 2
            col = idx % 2
            box = self._create_stat_box(label)
            self.stat_boxes[key] = box
            stats_grid.addWidget(box, row, col)
        
        layout.addLayout(stats_grid, 1)
        frame.setLayout(layout)
        return frame
    
    def _create_stat_box(self, label: str) -> QFrame:
        box = QFrame()
        box.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 2px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        label_widget = QLabel(label)
        label_widget.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        label_widget.setStyleSheet("color: #666;")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label_widget)
        
        value_widget = QLabel("--")
        value_widget.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        value_widget.setStyleSheet(f"color: {self.PRIMARY_CYAN};")
        value_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_widget)
        
        box.setLayout(layout)
        box._label = label_widget
        box._value = value_widget
        return box
    
    def _on_sound_checkbox_changed(self):
        selected = []
        for sound_name, checkbox in self.sound_checkboxes.items():
            if checkbox.isChecked():
                selected.append(sound_name)
        
        self.current_sound_types = selected
        
        if not selected:
            self.selection_label.setText("All sounds selected")
        elif len(selected) == 1:
            self.selection_label.setText(f"1 sound type selected: {selected[0]}")
        else:
            self.selection_label.setText(f"{len(selected)} sound types selected")
    
    def _clear_sound_selection(self):
        for checkbox in self.sound_checkboxes.values():
            checkbox.setChecked(False)
        
        self.current_sound_types = []
        self.selection_label.setText("All sounds selected")
        self.time_filter.setCurrentText('1 Day')
        self.current_time_range = 'day'
        self._refresh_data()
    
    def _on_filter_changed(self):
        time_map = {'1 Day': 'day', '1 Week': 'week', '1 Month': 'month'}
        self.current_time_range = time_map.get(self.time_filter.currentText(), 'day')
        self._refresh_data()
    
    def _refresh_data(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            
            self._clear_canvas(self.dist_canvas)
            self._clear_canvas(self.timeline_canvas)
            self._clear_canvas(self.confidence_canvas)
            
            self._update_distribution_chart()
            self._update_timeline_chart()
            self._update_heatmap_chart()
            self._update_correlation_chart()
            self._update_confidence_chart()
            self._update_stats_boxes()
        except Exception as e:
            print(f"[SoundAnalyticsView] Refresh error: {e}", flush=True)
    
    def _update_distribution_chart(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_distribution(
                self.current_time_range, 
                limit=15, 
                sound_types=sound_filter
            )
            
            print(f"[DEBUG] Distribution data: {len(data) if data else 0} items", flush=True)
            
            if not data:
                self._show_no_data(self.dist_canvas)
                return
            
            labels = [d['head_pred_label'] for d in data]
            counts = [d['count'] for d in data]
            
            # נקה את הקנבס
            self.dist_canvas.figure.clear()
            ax = self.dist_canvas.figure.add_subplot(111)
            
            colors = [self.CYAN_PALETTE[i % len(self.CYAN_PALETTE)] for i in range(len(labels))]
            bars = ax.bar(range(len(labels)), counts, color=colors, edgecolor='black', linewidth=0.5)
            
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
            ax.set_ylabel('Count', fontsize=9, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', axis='y')
            
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontsize=8, fontweight='bold')
            
            self.dist_canvas.figure.tight_layout()
            self.dist_canvas.draw()
            print("[DEBUG] Distribution chart drawn successfully", flush=True)
            
        except Exception as e:
            print(f"[ERROR] Distribution chart error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._show_no_data(self.dist_canvas)

    def _update_timeline_chart(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_timeline(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            print(f"[DEBUG] Timeline data: {len(data) if data else 0} items", flush=True)
            
            if not data:
                self._show_no_data(self.timeline_canvas)
                return
            
            timeline_dict = {}
            for row in data:
                time_bucket = row['time_bucket']
                count = row['count']
                if time_bucket not in timeline_dict:
                    timeline_dict[time_bucket] = 0
                timeline_dict[time_bucket] += count
            
            sorted_times = sorted(timeline_dict.keys())
            times = [str(t)[:16] for t in sorted_times]
            counts = [timeline_dict[t] for t in sorted_times]
            
            # נקה את הקנבס
            self.timeline_canvas.figure.clear()
            ax = self.timeline_canvas.figure.add_subplot(111)
            
            ax.plot(times, counts, marker='o', linewidth=2, markersize=5, color=self.ACCENT_CYAN)
            ax.fill_between(range(len(times)), counts, alpha=0.2, color=self.PRIMARY_CYAN)
            ax.set_xlabel('Time', fontsize=9, fontweight='bold')
            ax.set_ylabel('Detections', fontsize=9, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.tick_params(labelsize=8)
            
            self.timeline_canvas.figure.autofmt_xdate(rotation=45, ha='right')
            self.timeline_canvas.figure.tight_layout()
            self.timeline_canvas.draw()
            print("[DEBUG] Timeline chart drawn successfully", flush=True)
            
        except Exception as e:
            print(f"[ERROR] Timeline chart error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._show_no_data(self.timeline_canvas)

    def _update_confidence_chart(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_model_health_metrics(
                self.current_time_range,
                sound_types=sound_filter
            )

            if not data:
                self._show_no_data(self.confidence_canvas)
                return

            times = [str(d["time_bucket"])[:16] for d in data]
            avg_conf = [d["avg_confidence"] * 100 for d in data]
            avg_proc = [d["avg_processing_ms"] for d in data]

            fig = self.confidence_canvas.figure
            fig.clear()

            ax1 = fig.add_subplot(111)
            ax1.set_title("Model Performance Trends", fontsize=10, fontweight="bold", color=self.PRIMARY_CYAN) 
            ax1.plot(times, avg_conf, color=self.ACCENT_CYAN, marker="o", linewidth=2, label="Avg Confidence %")
            ax1.fill_between(range(len(avg_conf)), avg_conf, alpha=0.15, color=self.PRIMARY_CYAN)
            ax1.set_ylabel("Confidence (%)", fontsize=9, fontweight="bold")
            ax1.set_ylim(0, 100)
            ax1.tick_params(axis='x', rotation=45, labelsize=8)
            ax1.grid(True, alpha=0.3, linestyle="--")

            ax2 = ax1.twinx()
            proc_color = self.CYAN_PALETTE[7] 
            ax2.plot(times, avg_proc, color=proc_color, marker="^", linestyle="--", linewidth=2, label="Avg Processing (ms)")
            ax2.set_ylabel("Processing Time (ms)", fontsize=9, fontweight="bold", color=proc_color)
            ax2.tick_params(axis='y', labelcolor=proc_color)

            lines, labels = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=8)

            fig.tight_layout()
            self.confidence_canvas.draw()

        except Exception as e:
            print(f"[SoundAnalyticsView] Model Health Monitor chart error: {e}", flush=True)
            self._show_no_data(self.confidence_canvas)

    def _update_stats_boxes(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            stats = self.api.get_audio_stats(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            if stats:
                total = stats.get('total_files', 0) or 0
                self.stat_boxes['total_files']._value.setText(str(total))
                
                unknown = stats.get('unknown_count', 0) or 0
                self.stat_boxes['unknown_count']._value.setText(str(unknown))
                
                avg_conf = stats.get('avg_confidence')
                if avg_conf is not None and avg_conf > 0:
                    self.stat_boxes['avg_confidence']._value.setText(f"{avg_conf:.1%}")
                else:
                    self.stat_boxes['avg_confidence']._value.setText("--")
                
                avg_proc = stats.get('avg_processing_ms')
                if avg_proc is not None and avg_proc > 0:
                    self.stat_boxes['avg_processing_ms']._value.setText(f"{avg_proc:.0f}ms")
                else:
                    self.stat_boxes['avg_processing_ms']._value.setText("--")
            else:
                for key in self.stat_boxes:
                    self.stat_boxes[key]._value.setText("--")
        except Exception as e:
            print(f"[SoundAnalyticsView] Stats update error: {e}", flush=True)
    
    def _clear_canvas(self, canvas):
        canvas.figure.clear()
    
    def _show_no_data(self, canvas):
        ax = canvas.figure.add_subplot(111)
        ax.text(0.5, 0.5, 'No Data Available', 
               ha='center', va='center', fontsize=14, fontweight='bold',
               transform=ax.transAxes, color='#999')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        canvas.draw()
    
    def closeEvent(self, event):
        self.refresh_timer.stop()
        super().closeEvent(event)

    def _update_heatmap_chart(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_heatmap(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            print(f"[DEBUG] Heatmap data: {len(data) if data else 0} items", flush=True)
            
            if not data:
                self._show_no_data(self.heatmap_canvas)
                return
            
            heatmap_data = np.zeros((24, 7))
            
            for row in data:
                hour = int(row['hour_of_day'])
                day = int(row['day_of_week'])
                count = row['count']
                heatmap_data[hour, day] += count
            
            self.heatmap_canvas.figure.clear()
            ax = self.heatmap_canvas.figure.add_subplot(111)
            
            im = ax.imshow(heatmap_data, cmap='GnBu', aspect='auto', interpolation='nearest')
            
            ax.set_xticks(range(7))
            ax.set_xticklabels(['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], fontsize=8)
            ax.set_yticks(range(0, 24, 2))
            ax.set_yticklabels([f'{h:02d}:00' for h in range(0, 24, 2)], fontsize=7)
            
            ax.set_xlabel('Day of Week', fontsize=9, fontweight='bold')
            ax.set_ylabel('Hour of Day', fontsize=9, fontweight='bold')
            
            cbar = self.heatmap_canvas.figure.colorbar(im, ax=ax, pad=0.02)
            cbar.set_label('Detections', fontsize=8)
            cbar.ax.tick_params(labelsize=7)
            
            for i in range(24):
                for j in range(7):
                    if heatmap_data[i, j] > 0:
                        text_color = 'white' if heatmap_data[i, j] > heatmap_data.max() * 0.5 else 'black'
                        ax.text(j, i, int(heatmap_data[i, j]),
                            ha="center", va="center", color=text_color, fontsize=6, fontweight='bold')
            
            self.heatmap_canvas.figure.tight_layout()
            self.heatmap_canvas.draw()
            print("[DEBUG] Heatmap chart drawn successfully", flush=True)
            
        except Exception as e:
            print(f"[ERROR] Heatmap chart error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._show_no_data(self.heatmap_canvas)

    def _update_correlation_chart(self):
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_correlations(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            print(f"[DEBUG] Correlation data: {len(data) if data else 0} items", flush=True)
            
            if not data or len(data) < 1:
                self._show_no_data(self.correlation_canvas)
                return
            
            time_buckets = sorted(list(set(row['time_bucket'] for row in data)))
            sound_types = sorted(list(set(row['sound_type'] for row in data)))
            
            if len(time_buckets) < 2 or len(sound_types) < 2:
                self._show_no_data(self.correlation_canvas)
                return
            
            n_times = len(time_buckets)
            n_sounds = len(sound_types)
            data_matrix = np.zeros((n_times, n_sounds))
            
            time_idx = {t: i for i, t in enumerate(time_buckets)}
            sound_idx = {s: i for i, s in enumerate(sound_types)}
            
            for row in data:
                t_idx = time_idx[row['time_bucket']]
                s_idx = sound_idx[row['sound_type']]
                data_matrix[t_idx, s_idx] = row['detection_count']
            
            corr_matrix = np.corrcoef(data_matrix.T)
            corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
            
            self.correlation_canvas.figure.clear()
            ax = self.correlation_canvas.figure.add_subplot(111)
            
            im = ax.imshow(corr_matrix, cmap='Blues', aspect='auto', vmin=-1, vmax=1)
            
            ax.set_xticks(range(len(sound_types)))
            ax.set_yticks(range(len(sound_types)))
            ax.set_xticklabels(sound_types, rotation=45, ha='right', fontsize=7)
            ax.set_yticklabels(sound_types, fontsize=7)
            
            for i in range(len(sound_types)):
                for j in range(len(sound_types)):
                    value = corr_matrix[i, j]
                    text_color = 'white' if value > 0.5 else 'black'
                    ax.text(j, i, f'{value:.2f}',
                        ha='center', va='center',
                        color=text_color, fontsize=6, fontweight='bold')
            
            cbar = self.correlation_canvas.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Correlation Strength', rotation=270, labelpad=15, fontsize=8)
            
            ax.set_title('Sound Type Correlations\nDarker = Stronger Co-occurrence', 
                        fontsize=9, fontweight='bold', pad=10)
            
            self.correlation_canvas.figure.tight_layout()
            self.correlation_canvas.draw() 
            print("[DEBUG] Correlation chart drawn successfully", flush=True)
            
        except Exception as e:
            print(f"[ERROR] Correlation chart error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._show_no_data(self.correlation_canvas)
    
# ==========================================================
# Sound2 View - Displays Grafana dashboard
# ==========================================================
class Sound2View(QWidget):
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()

        title = QLabel("🌿 Ultrasonic Plant Predictions Dashboard")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            padding: 10px;
            color: #2C3E50;
        """)
        header.addWidget(title)

        header.addStretch()

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_dashboard)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        self.web_view = QWebEngineView()

        grafana_url = (
            "http://grafana:3000/d/ultrasonic-predictions/"
            "ultrasonic-plant-predictions"
            "?orgId=1&refresh=5s&kiosk=tv&theme=light"
        )

        self.web_view.setUrl(QUrl(grafana_url))
        layout.addWidget(self.web_view)

        self.status_label = QLabel("📊 Loading dashboard...")
        self.status_label.setStyleSheet("""
            height: 24px;
            padding: 5px;
            color: #7F8C8D;
            font-size: 12px;
        """)
        layout.addWidget(self.status_label)

        self.web_view.loadFinished.connect(self.on_load_finished)

    def refresh_dashboard(self):
        self.status_label.setText("🔄 Refreshing dashboard...")
        self.web_view.reload()

    def on_load_finished(self, success: bool):
        if success:
            self.status_label.setText("✓ Dashboard loaded successfully | Refreshes every 5s")
        else:
            self.status_label.setText(
                "⚠ Failed to load dashboard. Please check Grafana server."
            )


# ==========================================================
#                 Main Sound View with Tabs
# ==========================================================
class SoundView(QWidget):
    def __init__(self, api=None, parent=None):
        super().__init__(parent)
        self.api = api

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #d1d5da;
                border-radius: 10px;
                background: white;
            }
            QTabBar::tab {
                background: #f6f8fa;
                padding: 12px 24px;
                border-radius: 8px 8px 0 0;
                margin-right: 4px;
                font-size: 14px;
                font-weight: 500;
                color: #586069;
            }
            QTabBar::tab:selected {
                background-color: #4A90E2;
                color: white;
            }
            QTabBar::tab:hover { background: #e1e4e8; }
        """)

        self.map_tab = ImageMapView(api=self.api)
        self.env_tab = RecordingsTab(recording_type="audio", api=self.api)
        self.plant_tab = RecordingsTab(recording_type="ultrasound", api=self.api)
        self.dashboard_tab = Sound2View(api=self.api)
        self.analytics_tab = SoundAnalyticsView(api=self.api)
        
        self.tabs.addTab(self.map_tab, "🗺️ Interactive Map")
        self.tabs.addTab(self.env_tab, "🎵 Environment Sounds")
        self.tabs.addTab(self.plant_tab, "🌿 Plant Ultrasounds")
        self.tabs.addTab(self.dashboard_tab, "📊 Ultrasonic Dashboard")
        self.tabs.addTab(self.analytics_tab, "📈 Sound Analytics")

        layout.addWidget(self.tabs)
