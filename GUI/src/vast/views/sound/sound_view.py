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
            border-radius: 12px;
            border: 3px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #667eea, stop:1 #764ba2);
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
        else:  # ultrasound
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
    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.selected_mics = []
        self.selected_type = None
        self.mic_buttons = {}

        self.stacked_widget = QStackedWidget()
        
        # Map view page
        self.map_page = QWidget()
        layout = QVBoxLayout(self.map_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # Control panel
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
        
        # Load map image
        self._load_map_image()

        # Microphone definitions
        # Map to actual device_ids from docker-compose:
        # MIC-01 = environment sounds (sounds/)
        # MIC-02 = ultrasound plants (plants/)
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
        """Load the map background image"""
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
        
        # Header
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
            parent=self
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

        
        # API endpoints
        if recording_type == "ultrasound":
            self.api_url = "http://db_api_service:8001/api/files/plant-predictions/"
        else:
            self.api_url = "http://db_api_service:8001/api/files/audio-aggregates/"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Filters Frame
        filter_frame = self._create_filter_frame()
        
        list_label = QLabel("Available Recordings")
        list_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; padding: 5px;")

        # Table setup
        self.file_table = self._create_table()
        
        # Waveform
        waveform_container = self._create_waveform_container()

        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 13px; color: #666; padding: 8px;
            background-color: #f6f8fa; border-radius: 6px; border: 1px solid #d1d5da;
        """)

        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)

        layout.addWidget(filter_frame)
        layout.addWidget(list_label)
        layout.addWidget(self.file_table, 1)
        layout.addWidget(waveform_container)
        layout.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.update_list)
        self.update_list()

    def _create_filter_frame(self):
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame { background-color: #ffffff; border: 2px solid #e1e4e8;
                     border-radius: 12px; padding: 15px; }
        """)
        filters_layout = QVBoxLayout(filter_frame)
        filters_layout.setSpacing(12)

        # Row 1
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        type_label = QLabel("Filter by Type:")
        type_label.setStyleSheet("font-weight: bold; color: #333;")

        self.noise_filter = QComboBox()
        self.noise_filter.setStyleSheet("""
            QComboBox { padding: 8px; border: 2px solid #d1d5da; border-radius: 6px;
                       background: white; min-width: 150px; }
            QComboBox:hover { border: 2px solid #4A90E2; }
        """)

        if self.recording_type == "ultrasound":
            self.noise_filter.addItems([
                "All signals", "Empty Pot", "Greenhouse Noises",
                "Tobacco Cut", "Tobacco Dry", "Tomato Cut", "Tomato Dry"
            ])
        else:
            self.noise_filter.addItems([
                "All types", "predatory_animals", "non_predatory_animals",
                "birds", "fire", "footsteps", "insects",
                "screaming", "shotgun", "stormy_weather",
                "streaming_water", "vehicle", "Other"
            ])

        date_label = QLabel("Date Range:")
        date_label.setStyleSheet("font-weight: bold; color: #333;")

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-7))
        self.date_from.setStyleSheet("""
            QDateEdit { padding: 8px; border: 2px solid #d1d5da;
                       border-radius: 6px; background: white; }
        """)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setStyleSheet(self.date_from.styleSheet())

        row1.addWidget(type_label)
        row1.addWidget(self.noise_filter)
        row1.addWidget(date_label)
        row1.addWidget(self.date_from)
        row1.addWidget(QLabel("→"))
        row1.addWidget(self.date_to)

        # Row 2
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        sort_label = QLabel("Sort by:")
        sort_label.setStyleSheet("font-weight: bold; color: #333;")

        self.sort_by = QComboBox()
        self.sort_by.addItems(["Date (Newest)", "Date (Oldest)", "Length", "Device"])
        self.sort_by.setStyleSheet(self.noise_filter.styleSheet())

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by filename...")
        self.search_box.setStyleSheet("""
            QLineEdit { padding: 8px; border: 2px solid #d1d5da; border-radius: 6px;
                       background: white; font-size: 14px; }
            QLineEdit:focus { border: 2px solid #4A90E2; }
        """)

        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.refresh_button.setStyleSheet("""
            QPushButton { background-color: #4A90E2; color: white; border-radius: 8px;
                         padding: 10px 20px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #357ABD; }
        """)

        row2.addWidget(sort_label)
        row2.addWidget(self.sort_by)
        row2.addWidget(self.search_box, 2)
        row2.addWidget(self.refresh_button)

        filters_layout.addLayout(row1)
        filters_layout.addLayout(row2)
        
        return filter_frame

    def _create_table(self):
        table = QTableWidget()

        if self.recording_type == "ultrasound":
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels([
                "File", "Device", "Predicted Class", "Confidence", "Watering Status", "Actions"
            ])
        else:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels([
                "Filename", "Device", "Predicted Label", "Probability", "Format", "Actions"
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
            QFrame { background-color: #ffffff; border: 2px solid #4A90E2;
                    border-radius: 10px; padding: 10px; }
        """)
        waveform_layout = QVBoxLayout(waveform_container)
        waveform_layout.setSpacing(5)
        
        waveform_label = QLabel("🎵 Audio Visualizer")
        waveform_label.setStyleSheet("""
            font-size: 16px; font-weight: bold; color: #4A90E2; padding: 5px;
        """)
        waveform_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.waveform = AudioWaveform()
        self.waveform.setMinimumHeight(150)
        
        waveform_layout.addWidget(waveform_label)
        waveform_layout.addWidget(self.waveform)
        
        return waveform_container
    
    def on_playback_state_changed(self, state):
        print("[DEBUG] Playback state:", state)
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.waveform.start_animation()
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self.waveform.stop_animation()
            if self.status_label.text().startswith("Playing:"):
                self.status_label.setText("Finished")

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
        
        # Add type filter
        filter_value = self.noise_filter.currentText()
        if self.recording_type == "ultrasound":
            if filter_value not in ("All signals", "All types"):
                params["predicted_class"] = filter_value
        else:
            if filter_value not in ("All types", "All signals"):
                params["type"] = filter_value
        
        # Add device IDs if provided
        if self.mic_ids:
            params["device_ids"] = ",".join(self.mic_ids)
        
        try:
            # response = requests.get(self.api_url, params=params, timeout=10)
            response = self.api.http.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            print(f"[DEBUG] Fetched {len(data)} records from {self.api_url}")

            # Populate table
            for f in data:
                row = self.file_table.rowCount()
                self.file_table.insertRow(row)
                self.file_table.setRowHeight(row, 60)

                # Check if compressed
                is_compressed = f.get("is_compressed", False)
                
                # Set text color based on compression
                text_color = QColor("#888888") if is_compressed else QColor("#000000")

                if self.recording_type == "ultrasound":
                    # Ultrasonic plant predictions
                    filename = f.get("file", "N/A")
                    device_id = f.get("device_id", "N/A")
                    pred_class = f.get("predicted_class", "Unknown")
                    confidence = f.get("confidence", 0)
                    watering_status = f.get("watering_status", "N/A")
                    url = f.get("url", "")

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
                else:
                    # Audio aggregates
                    filename = f.get("filename", "N/A")
                    device_id = f.get("device_id", "N/A")
                    label = f.get("predicted_label", "Unknown")
                    prob = f.get("probability", 0)
                    url = f.get("url", "")
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

                # Actions column with Play/Stop buttons
                control_widget = QWidget()
                control_layout = QHBoxLayout(control_widget)
                control_layout.setContentsMargins(2, 2, 2, 2)
                control_layout.setSpacing(6)

                play_btn = QPushButton("▶")
                play_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                play_btn.setFixedSize(35, 30)

                # Adjust button style for compressed files
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

                # Store current row buttons for state management
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

                # Set correct column index for Actions (column 5 for both types now)
                self.file_table.setCellWidget(row, 5, control_widget)

            if self.file_table.rowCount() == 0:
                self.file_table.insertRow(0)
                empty_item = QTableWidgetItem("No recordings found")
                empty_item.setForeground(QColor("#999"))
                self.file_table.setItem(0, 0, empty_item)
                self.file_table.setSpan(0, 0, 1, 6)

            self.status_label.setText(f"✓ Loaded {len(data)} recordings")

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
        """Play audio from MinIO URL"""
        if not url:
            QMessageBox.warning(self, "No URL", "Audio file URL not available")
            return

        # Stop any currently playing audio first
        self.player.stop()
        
        print(f"[DEBUG] Attempting to play: {url}")
        
        # Warn about compressed files
        if is_compressed:
            reply = QMessageBox.question(
                self, 
                "Compressed File", 
                "This is a compressed OPUS file. Playback may not work properly.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Test MinIO connectivity
        try:
            print(f"[DEBUG] Testing URL accessibility: {url}")
            check = requests.head(url, timeout=3)
            print(f"[DEBUG] MinIO response: {check.status_code}")
            
            if check.status_code == 403:
                QMessageBox.warning(self, "Access Denied",
                    f"MinIO returned 403 Forbidden.\n\nThe bucket may not be public.\n\nURL: {url}")
                return
            elif check.status_code == 404:
                QMessageBox.warning(self, "File Not Found",
                    f"MinIO returned 404 Not Found.\n\nThe file may have been deleted.\n\nURL: {url}")
                return
            elif check.status_code != 200:
                QMessageBox.warning(self, "MinIO Error",
                    f"MinIO returned status {check.status_code}\n\nURL: {url}")
                return
                
        except requests.exceptions.ConnectionError as e:
            QMessageBox.warning(self, "Connection Error",
                f"Cannot connect to MinIO server.\n\nMake sure MinIO is running.\n\nError: {str(e)[:200]}")
            return
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "Timeout",
                "MinIO request timed out.\n\nThe server may be slow or unreachable.")
            return
        except Exception as e:
            QMessageBox.warning(self, "Network Error",
                f"Failed to reach MinIO:\n\n{str(e)[:200]}")
            return

        # Update UI
        self.waveform.start_animation()
        status_text = f"▶ Playing: {filename}"
        if is_compressed:
            status_text += " (Compressed)"
        self.status_label.setText(status_text)

        # Disable all play buttons, enable this stop button
        self._disable_all_play_buttons()
        play_btn.setEnabled(False)
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

        try:
            # Set audio source and play
            qurl = QUrl(url)
            print(f"[DEBUG] QUrl created: {qurl.toString()}")
            self.player.setSource(qurl)
            self.player.play()
            print(f"[DEBUG] Player state after play(): {self.player.playbackState()}")
            
        except Exception as e:
            print(f"[ERROR] Playback failed: {e}")
            self.waveform.stop_animation()
            self.status_label.setText("⚠ Playback failed")
            QMessageBox.warning(self, "Playback Error", f"Failed to play audio:\n{str(e)}")
            self._enable_all_play_buttons()
            stop_btn.setEnabled(False)

    def stop_row_audio(self, play_btn, stop_btn):
        """Stop currently playing audio"""
        self.player.stop()
        self.waveform.stop_animation()
        self.status_label.setText("⏹ Stopped")

        # Re-enable all play buttons
        self._enable_all_play_buttons()

    def _disable_all_play_buttons(self):
        """Disable all play buttons in the table"""
        for row in range(self.file_table.rowCount()):
            widget = self.file_table.cellWidget(row, 6)
            if widget:
                layout = widget.layout()
                if layout and layout.count() >= 1:
                    play_btn = layout.itemAt(0).widget()
                    if play_btn:
                        play_btn.setEnabled(False)

    def _enable_all_play_buttons(self):
        """Enable all play buttons and disable all stop buttons"""
        for row in range(self.file_table.rowCount()):
            widget = self.file_table.cellWidget(row, 5)
            if widget:
                layout = widget.layout()
                if layout and layout.count() >= 2:
                    play_btn = layout.itemAt(0).widget()
                    stop_btn = layout.itemAt(1).widget()
                    if play_btn:
                        play_btn.setEnabled(True)
                    if stop_btn:
                        stop_btn.setEnabled(False)
                        stop_btn.setStyleSheet("""
                            QPushButton {
                                background-color: #6c757d;
                                color: white;
                                border-radius: 4px;
                                font-weight: bold;
                            }
                            QPushButton:disabled { background-color: #b0b0b0; }
                        """)

# ==========================================================
#                 Analytics Dashboard Tab
# ==========================================================
class AnalyticsDashboard(QWidget):
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
    
    # 11 shades of green palette
    GREEN_PALETTE = [
        '#004d00',  # Dark green
        '#006600',
        '#008000',  # Green
        '#1a9900',
        '#33b300',
        '#4dcc00',
        '#66e600',
        '#80ff00',
        '#99ff33',
        '#b3ff66',
        '#ccff99'   # Light green
    ]
    
    LIGHT_THEME = {
        'bg': '#f8f9fa',
        'card': '#ffffff',
        'text': '#333333',
        'border': '#e0e0e0',
        'primary': '#1976D2',
        'accent': '#4dcc00'
    }
    
    DARK_THEME = {
        'bg': '#1e1e1e',
        'card': '#2d2d2d',
        'text': '#e0e0e0',
        'border': '#444444',
        'primary': '#64B5F6',
        'accent': '#66e600'
    }
    
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api
        self.current_time_range = 'day'
        self.current_sound_types = []  # Multi-select list
        self.is_dark_theme = False
        self.current_theme = self.LIGHT_THEME.copy()
        
        self.setMinimumSize(QSize(1350, 1000))

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_control_panel()
        main_layout.addWidget(toolbar)

        # Content frame
        content_frame = QFrame()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)

        # Filter frame
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

        # Time range row
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

        # Sound types header
        sound_header_row = QHBoxLayout()
        sound_label = QLabel("Sound Types (select multiple):")
        sound_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        sound_header_row.addWidget(sound_label)

        self.selection_label = QLabel("All sounds selected")
        self.selection_label.setStyleSheet("color: #1976D2; font-weight: bold;")
        sound_header_row.addWidget(self.selection_label)
        sound_header_row.addStretch()

        clear_btn = QPushButton("Clear All")
        clear_btn.setMaximumWidth(100)
        clear_btn.clicked.connect(self._clear_sound_selection)
        sound_header_row.addWidget(clear_btn)

        apply_btn = QPushButton("Apply Filter")
        apply_btn.setMaximumWidth(100)
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
        """)
        apply_btn.clicked.connect(self._refresh_data)
        sound_header_row.addWidget(apply_btn)
        filter_layout.addLayout(sound_header_row)

        # Checkbox container
        checkbox_container = QFrame()
        checkbox_container.setObjectName("checkboxContainer")
        checkbox_container.setStyleSheet("""
            QFrame#checkboxContainer {
                background-color: white;
                border: 2px solid #1976D2;
                border-radius: 6px;
                max-height: 350px;
            }
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

        # Activity calendar
        calendar_frame = self._create_activity_calendar()
        content_layout.addWidget(calendar_frame)

        # Chart grid
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Helper function for uniform frames
        def make_chart_frame(title, canvas):
            frame = self._create_chart_frame(title, canvas)
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            frame.setMinimumHeight(320)
            frame.setMaximumHeight(320)
            return frame

        # Row 1
        self.dist_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Sound Distribution (Count)", self.dist_canvas), 0, 0)

        self.timeline_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Detection Timeline", self.timeline_canvas), 0, 1)

        # Row 2
        self.heatmap_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Sound Heatmap - Activity Patterns", self.heatmap_canvas), 1, 0)

        self.correlation_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Correlation Explorer", self.correlation_canvas), 1, 1)

        # Row 3
        self.confidence_canvas = self._create_canvas(figsize=(6, 5))
        grid.addWidget(make_chart_frame("Model Health Monitor", self.confidence_canvas), 2, 0)

        stats_frame = self._create_stats_frame()
        stats_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        stats_frame.setMinimumHeight(320)
        stats_frame.setMaximumHeight(320)
        grid.addWidget(stats_frame, 2, 1)

        # Add grid to content
        content_layout.addLayout(grid, stretch=10)
        content_frame.setLayout(content_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(content_frame)

        main_layout.addWidget(scroll_area)
        self.setLayout(main_layout)

        # Timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(30000)  # 30 seconds

        # Initial load
        self._refresh_data()
    
    def _create_control_panel(self) -> QToolBar:
        """Create toolbar with control buttons: Refresh, Export CSV, Toggle Theme"""
        toolbar = QToolBar("Control Panel")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f0f0f0;
                border-bottom: 1px solid #ddd;
                spacing: 10px;
                padding: 8px;
            }
            QToolButton {
                padding: 6px 12px;
                font-weight: bold;
            }
        """)
        
        toolbar.addAction("🔄 Refresh", self._refresh_data)
        toolbar.addSeparator()
        toolbar.addAction("💾 Export CSV", self._export_csv)
        toolbar.addSeparator()
        toolbar.addAction("🌓 Toggle Theme", self._toggle_theme)
        
        return toolbar
    
    def _create_activity_calendar(self) -> QFrame:
        """Create a calendar showing detection activity per day"""
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
        
        # Create grid for calendar
        calendar_grid = QHBoxLayout()
        calendar_grid.setSpacing(2)
        
        today = datetime.now().date()
        for i in range(30):
            date = today - timedelta(days=29-i)
            day_box = QFrame()
            day_box.setMinimumSize(QSize(20, 20))
            day_box.setMaximumSize(QSize(20, 20))
            
            # Random intensity for demo (replace with real data from API)
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
        """Map intensity (0-1) to green color from palette"""
        if intensity < 0.2:
            return self.GREEN_PALETTE[0]
        elif intensity < 0.4:
            return self.GREEN_PALETTE[2]
        elif intensity < 0.6:
            return self.GREEN_PALETTE[4]
        elif intensity < 0.8:
            return self.GREEN_PALETTE[7]
        else:
            return self.GREEN_PALETTE[10]
    
    def _toggle_theme(self):
        """Toggle between light and dark theme"""
        self.is_dark_theme = not self.is_dark_theme
        self.current_theme = self.DARK_THEME.copy() if self.is_dark_theme else self.LIGHT_THEME.copy()
        self._apply_theme()
        self._refresh_data()
    
    def _apply_theme(self):
        """Apply current theme to all widgets"""
        theme = self.current_theme
        
        self.setStyleSheet(f"""
            AnalyticsDashboard {{
                background-color: {theme['bg']};
            }}
            QComboBox {{
                padding: 8px 12px;
                border: 2px solid {theme['border']};
                border-radius: 6px;
                background-color: {theme['card']};
                color: {theme['text']};
                min-width: 200px;
                font-size: 10pt;
                font-weight: 500;
            }}
            QComboBox:hover {{
                border: 2px solid {theme['primary']};
            }}
            QCheckBox {{
                padding: 6px 12px;
                font-size: 10pt;
                color: {theme['text']};
            }}
            QCheckBox:hover {{
                background-color: {theme['primary']};
            }}
            QLabel {{
                color: {theme['text']};
            }}
            QPushButton {{
                padding: 6px 12px;
                background-color: {theme['card']};
                border: 1px solid {theme['border']};
                border-radius: 4px;
                font-weight: bold;
                color: {theme['text']};
            }}
            QPushButton:hover {{
                background-color: {theme['primary']};
                color: white;
            }}
            QFrame {{
                background-color: {theme['card']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
            }}
            QToolBar {{
                background-color: {theme['card']};
                border-bottom: 1px solid {theme['border']};
            }}
        """)
    
    def _export_csv(self):
        """Export current data to CSV"""
        try:
            import csv
            
            filename = f"sound_detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_distribution(
                self.current_time_range,
                limit=100,
                sound_types=sound_filter
            )
            
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['sound_type', 'count'])
                writer.writeheader()
                for row in data:
                    writer.writerow({
                        'sound_type': row.get('head_pred_label'),
                        'count': row.get('count')
                    })
            
            QMessageBox.information(self, "Success", f"Data exported to {filename}")
            print(f"[AnalyticsDashboard] Data exported to {filename}", flush=True)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Export failed: {str(e)}")
            print(f"[AnalyticsDashboard] Export error: {e}", flush=True)
    
    def _create_canvas(self, figsize=(5.5, 4.5)):
        """Create matplotlib canvas for chart"""
        canvas = FigureCanvas(Figure(figsize=figsize, dpi=90))
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return canvas
    
    def _create_chart_frame(self, title: str, widget: QWidget) -> QFrame:
        """Create a framed chart container"""
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
        title_label.setStyleSheet("color: #1976D2; margin-bottom: 4px;")
        layout.addWidget(title_label)
        
        layout.addWidget(widget, 1)
        frame.setLayout(layout)
        return frame
    
    def _create_stats_frame(self) -> QFrame:
        """Create frame with 4 stat boxes in 2x2 grid"""
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
        title_label.setStyleSheet("color: #1976D2; margin-bottom: 6px;")
        layout.addWidget(title_label)
        
        stats_grid = QGridLayout()
        stats_grid.setSpacing(10)
        stats_grid.setRowStretch(0, 1)
        stats_grid.setRowStretch(1, 1)
        stats_grid.setColumnStretch(0, 1)
        stats_grid.setColumnStretch(1, 1)
        
        # Store references for updating
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
        """Create a single statistic box"""
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
        value_widget.setStyleSheet("color: #1976D2;")
        value_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_widget)
        
        box.setLayout(layout)
        box._label = label_widget
        box._value = value_widget
        return box
    
    def _on_sound_checkbox_changed(self):
        """Update selection label when checkboxes change"""
        selected = []
        for sound_name, checkbox in self.sound_checkboxes.items():
            if checkbox.isChecked():
                selected.append(sound_name)
        
        self.current_sound_types = selected
        
        # Update label
        if not selected:
            self.selection_label.setText("All sounds selected")
        elif len(selected) == 1:
            self.selection_label.setText(f"1 sound type selected: {selected[0]}")
        else:
            self.selection_label.setText(f"{len(selected)} sound types selected")
        
        print(f"[AnalyticsDashboard] Selection changed: {self.current_sound_types or 'All'}", flush=True)
    
    def _clear_sound_selection(self):
        """Clear all sound type selections"""
        for checkbox in self.sound_checkboxes.values():
            checkbox.setChecked(False)
        
        self.current_sound_types = []
        self.selection_label.setText("All sounds selected")
        self.time_filter.setCurrentText('1 Day')
        self.current_time_range = 'day'
        
        print(f"[AnalyticsDashboard] Filters cleared", flush=True)
        self._refresh_data()
    
    def _on_filter_changed(self):
        """Handle time filter changes"""
        time_map = {'1 Day': 'day', '1 Week': 'week', '1 Month': 'month'}
        self.current_time_range = time_map.get(self.time_filter.currentText(), 'day')
        
        print(f"[AnalyticsDashboard] Time range changed to: {self.current_time_range}", flush=True)
        self._refresh_data()
    
    def _refresh_data(self):
        """Refresh all charts with current filters"""
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            print(f"[AnalyticsDashboard] Refreshing - Time: {self.current_time_range}, Sounds: {sound_filter or 'All'}", flush=True)
            
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
            print(f"[AnalyticsDashboard] Refresh error: {e}", flush=True)
            import traceback
            traceback.print_exc()
    
    def _update_distribution_chart(self):
        """Update bar chart - distribution of sound types by COUNT"""
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_distribution(
                self.current_time_range, 
                limit=15, 
                sound_types=sound_filter
            )
            
            if not data:
                self._show_no_data(self.dist_canvas)
                return
            
            labels = [d['head_pred_label'] for d in data]
            counts = [d['count'] for d in data]
            
            ax = self.dist_canvas.figure.add_subplot(111)
            
            # Use green palette
            colors = [self.GREEN_PALETTE[i % len(self.GREEN_PALETTE)] for i in range(len(labels))]
            bars = ax.bar(range(len(labels)), counts, color=colors, edgecolor='black', linewidth=0.5)
            
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
            ax.set_ylabel('Count', fontsize=9, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', axis='y')
            
            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom', fontsize=8, fontweight='bold')
            
            self.dist_canvas.figure.tight_layout()
            self.dist_canvas.draw()
        except Exception as e:
            print(f"[AnalyticsDashboard] Distribution chart error: {e}", flush=True)
            self._show_no_data(self.dist_canvas)
    
    def _update_timeline_chart(self):
        """Update line chart - timeline of detections"""
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_timeline(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            if not data:
                self._show_no_data(self.timeline_canvas)
                return
            
            # Group by time_bucket and sum counts
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
            
            ax = self.timeline_canvas.figure.add_subplot(111)
            
            ax.plot(times, counts, marker='o', linewidth=2, markersize=5, color='#1a9900')
            ax.fill_between(range(len(times)), counts, alpha=0.2, color='#4dcc00')
            ax.set_xlabel('Time', fontsize=9, fontweight='bold')
            ax.set_ylabel('Detections', fontsize=9, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.tick_params(labelsize=8)
            
            self.timeline_canvas.figure.autofmt_xdate(rotation=45, ha='right')
            self.timeline_canvas.figure.tight_layout()
            self.timeline_canvas.draw()
        except Exception as e:
            print(f"[AnalyticsDashboard] Timeline chart error: {e}", flush=True)
            self._show_no_data(self.timeline_canvas)
    
    def _update_confidence_chart(self):
        """Update Model Health Monitor chart - Avg Confidence % & Processing Time"""
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
            ax1.set_title("Model Performance Trends", fontsize=10, fontweight="bold", color="#1976D2")
            ax1.plot(times, avg_conf, color="#33b300", marker="o", linewidth=2, label="Avg Confidence %")
            ax1.fill_between(range(len(avg_conf)), avg_conf, alpha=0.15, color="#66e600")
            ax1.set_ylabel("Confidence (%)", fontsize=9, fontweight="bold")
            ax1.set_ylim(0, 100)
            ax1.tick_params(axis='x', rotation=45, labelsize=8)
            ax1.grid(True, alpha=0.3, linestyle="--")

            # Processing time on secondary y-axis
            ax2 = ax1.twinx()
            ax2.plot(times, avg_proc, color="#99ff33", marker="^", linestyle="--", linewidth=2, label="Avg Processing (ms)")
            ax2.set_ylabel("Processing Time (ms)", fontsize=9, fontweight="bold", color="#66e600")
            ax2.tick_params(axis='y', labelcolor="#66e600")

            # Combined legend
            lines, labels = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=8)

            fig.tight_layout()
            self.confidence_canvas.draw()

        except Exception as e:
            print(f"[AnalyticsDashboard] Model Health Monitor chart error: {e}", flush=True)
            self._show_no_data(self.confidence_canvas)

    def _update_stats_boxes(self):
        """Update statistics boxes"""
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            stats = self.api.get_audio_stats(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            print(f"[AnalyticsDashboard] Stats received: {stats}", flush=True)
            
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
            print(f"[AnalyticsDashboard] Stats update error: {e}", flush=True)
            import traceback
            traceback.print_exc()
    
    def _clear_canvas(self, canvas):
        """Clear a matplotlib canvas completely"""
        canvas.figure.clear()
    
    def _show_no_data(self, canvas):
        """Show 'No Data Available' message on canvas"""
        ax = canvas.figure.add_subplot(111)
        ax.text(0.5, 0.5, 'No Data Available', 
               ha='center', va='center', fontsize=14, fontweight='bold',
               transform=ax.transAxes, color='#999')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        canvas.draw()
    
    def closeEvent(self, event):
        """Clean up timer when closing"""
        self.refresh_timer.stop()
        super().closeEvent(event)

    def _update_heatmap_chart(self):
        """Update heatmap chart - activity by hour of day and day of week"""
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_heatmap(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            if not data:
                self._show_no_data(self.heatmap_canvas)
                return
            
            # Create 24 hours x 7 days matrix
            heatmap_data = np.zeros((24, 7))
            
            # Fill matrix with counts
            for row in data:
                hour = int(row['hour_of_day'])
                day = int(row['day_of_week'])
                count = row['count']
                heatmap_data[hour, day] += count
            
            ax = self.heatmap_canvas.figure.add_subplot(111)
            
            # Create heatmap using imshow with green colormap
            im = ax.imshow(heatmap_data, cmap='Greens', aspect='auto', interpolation='nearest')
            
            # Set ticks
            ax.set_xticks(range(7))
            ax.set_xticklabels(['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], fontsize=8)
            ax.set_yticks(range(0, 24, 2))
            ax.set_yticklabels([f'{h:02d}:00' for h in range(0, 24, 2)], fontsize=7)
            
            ax.set_xlabel('Day of Week', fontsize=9, fontweight='bold')
            ax.set_ylabel('Hour of Day', fontsize=9, fontweight='bold')
            
            # Add colorbar
            cbar = self.heatmap_canvas.figure.colorbar(im, ax=ax, pad=0.02)
            cbar.set_label('Detections', fontsize=8)
            cbar.ax.tick_params(labelsize=7)
            
            # Add text annotations for non-zero values
            for i in range(24):
                for j in range(7):
                    if heatmap_data[i, j] > 0:
                        text_color = 'white' if heatmap_data[i, j] > heatmap_data.max() * 0.5 else 'black'
                        ax.text(j, i, int(heatmap_data[i, j]),
                               ha="center", va="center", color=text_color, fontsize=6, fontweight='bold')
            
            self.heatmap_canvas.figure.tight_layout()
            self.heatmap_canvas.draw()
        except Exception as e:
            print(f"[AnalyticsDashboard] Heatmap chart error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._show_no_data(self.heatmap_canvas)

    def _update_correlation_chart(self):
        """Update correlation heatmap - shows relationships between sound types"""
        try:
            sound_filter = self.current_sound_types if self.current_sound_types else None
            data = self.api.get_audio_correlations(
                self.current_time_range,
                sound_types=sound_filter
            )
            
            print(f"[AnalyticsDashboard] Correlation data received: {len(data) if data else 0} rows", flush=True)
            if data and len(data) > 0:
                print(f"[AnalyticsDashboard] Sample data: {data[:3]}", flush=True)
            
            if not data or len(data) < 1:
                print("[AnalyticsDashboard] No correlation data - showing 'No Data'", flush=True)
                self._show_no_data(self.correlation_canvas)
                return
            
            # Build data structure without pandas
            # Find all time buckets and sound types
            time_buckets = sorted(list(set(row['time_bucket'] for row in data)))
            sound_types = sorted(list(set(row['sound_type'] for row in data)))
            
            print(f"[AnalyticsDashboard] Found {len(time_buckets)} time buckets, {len(sound_types)} sound types", flush=True)
            print(f"[AnalyticsDashboard] Sound types: {sound_types}", flush=True)
            
            if len(time_buckets) < 2 or len(sound_types) < 2:
                print(f"[AnalyticsDashboard] Not enough data for correlation: {len(time_buckets)} buckets, {len(sound_types)} types", flush=True)
                self._show_no_data(self.correlation_canvas)
                return
            
            # Create matrix: rows=time_buckets, cols=sound_types
            n_times = len(time_buckets)
            n_sounds = len(sound_types)
            data_matrix = np.zeros((n_times, n_sounds))
            
            # Fill the matrix
            time_idx = {t: i for i, t in enumerate(time_buckets)}
            sound_idx = {s: i for i, s in enumerate(sound_types)}
            
            for row in data:
                t_idx = time_idx[row['time_bucket']]
                s_idx = sound_idx[row['sound_type']]
                data_matrix[t_idx, s_idx] = row['detection_count']
            
            print(f"[AnalyticsDashboard] Data matrix shape: {data_matrix.shape}", flush=True)
            
            # Calculate correlation matrix using numpy
            corr_matrix = np.corrcoef(data_matrix.T)
            
            # Handle NaN values (if columns have zero standard deviation)
            corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
            
            print(f"[AnalyticsDashboard] Correlation matrix shape: {corr_matrix.shape}", flush=True)
            
            # Create the plot
            ax = self.correlation_canvas.figure.add_subplot(111)
            
            # Create heatmap with green colormap only
            im = ax.imshow(corr_matrix, cmap='Greens', aspect='auto', vmin=-1, vmax=1)
            
            # Set labels
            ax.set_xticks(range(len(sound_types)))
            ax.set_yticks(range(len(sound_types)))
            ax.set_xticklabels(sound_types, rotation=45, ha='right', fontsize=7)
            ax.set_yticklabels(sound_types, fontsize=7)
            
            # Add correlation values inside cells
            for i in range(len(sound_types)):
                for j in range(len(sound_types)):
                    value = corr_matrix[i, j]
                    # Use white text for dark backgrounds (high correlation)
                    text_color = 'white' if value > 0.5 else 'black'
                    ax.text(j, i, f'{value:.2f}',
                           ha='center', va='center',
                           color=text_color, fontsize=6, fontweight='bold')
            
            # Add colorbar
            cbar = self.correlation_canvas.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Correlation Strength', rotation=270, labelpad=15, fontsize=8)
            
            ax.set_title('Sound Type Correlations\nDarker = Stronger Co-occurrence', 
                        fontsize=9, fontweight='bold', pad=10)
            
            self.correlation_canvas.figure.tight_layout()
            self.correlation_canvas.draw()
            
            print("[AnalyticsDashboard] Correlation chart updated successfully", flush=True)
            
        except Exception as e:
            print(f"[AnalyticsDashboard] Correlation chart error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._show_no_data(self.correlation_canvas)


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

        self.map_tab = ImageMapView()
        self.env_tab = RecordingsTab(recording_type="audio", api=self.api)
        self.plant_tab = RecordingsTab(recording_type="ultrasound", api=self.api)

        
        # Add Analytics Dashboard tab if API is provided
        if self.api:
            self.analytics_tab = AnalyticsDashboard(self.api)
            self.tabs.addTab(self.analytics_tab, "📊 Analytics Dashboard")

        self.tabs.addTab(self.map_tab, "🗺️ Interactive Map")
        self.tabs.addTab(self.env_tab, "🎵 Environment Sounds")
        self.tabs.addTab(self.plant_tab, "🌿 Plant Ultrasounds")

        layout.addWidget(self.tabs)