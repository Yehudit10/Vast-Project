from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QLineEdit, QDateEdit, 
    QFrame, QMessageBox, QTabWidget, QTableWidget, 
    QTableWidgetItem, QDialog, QHeaderView, QAbstractItemView,
    QStackedWidget
)
from PyQt6.QtCore import Qt, QDate, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QCursor, QPainter, QPen
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
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
            (QColor(102, 126, 234), QColor(118, 75, 162)),  # Purple-Blue
            (QColor(67, 233, 123), QColor(56, 249, 215)),   # Cyan-Green
            (QColor(251, 200, 212), QColor(151, 149, 240)), # Pink-Purple
            (QColor(250, 208, 196), QColor(255, 209, 255))  # Peach-Pink
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
#                 Microphone Button Widget (Updated)
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

        icon = "" if mic_type == "audio" else ""
        self.setText(f"{icon}\n{mic_id.upper()}")
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

        # Selection state
        self.selected_mics = []
        self.selected_type = None  # 'audio' or 'ultrasound'
        self.mic_buttons = {}

        # Create stacked widget to switch between map and recordings
        self.stacked_widget = QStackedWidget()
        
        # Map view page
        self.map_page = QWidget()
        layout = QVBoxLayout(self.map_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # Control panel for selection
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
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #666;
            padding: 5px;
        """)

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
        
        # Zoom buttons (+ / -)
        self.zoom_in_btn = QPushButton("+", self.map_container)
        self.zoom_out_btn = QPushButton("−", self.map_container)

        for btn in (self.zoom_in_btn, self.zoom_out_btn):
            btn.setFixedSize(40, 40)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 120, 212, 0.8);
                    color: white;
                    border-radius: 20px;
                    font-size: 18px;
                    font-weight: bold;
                    border: 1px solid white;
                }
                QPushButton:hover {
                    background-color: rgba(0, 95, 163, 0.9);
                }
            """)

        self.zoom_in_btn.move(740, 20)
        self.zoom_out_btn.move(740, 70)

        self.zoom_in_btn.clicked.connect(lambda: self.adjust_zoom(1.1))
        self.zoom_out_btn.clicked.connect(lambda: self.adjust_zoom(0.9))

        possible_paths = [
            "map_background.png",
            "./map_background.png",
            "../map_background.png",
            os.path.join(os.getcwd(), "map_background.png"),
            os.path.join(os.path.dirname(__file__), "map_background.png")
        ]
        
        image_loaded = False
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    pixmap = QPixmap(path)
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            800, 600,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self.background_label.setPixmap(scaled_pixmap)
                        image_loaded = True
                        print(f"[SUCCESS] Map image loaded from: {path}")
                        break
                    self.setup_zoom_and_pan()

            except Exception as e:
                print(f"[ERROR] Failed to load from {path}: {e}")
                continue
        
        if not image_loaded:
            print(f"[WARNING] Map image not found in any of these locations:")
            for p in possible_paths:
                print(f"  - {p}")
            print(f"[INFO] Current directory: {os.getcwd()}")
            
            self.background_label.setStyleSheet("""
                font-size: 16px;
                color: #888;
                background-color: #d0e8f2;
            """)
            self.background_label.setText(
                "Sensor Locations\n\n"
                "(Map image not found)\n"
                f"Looking for: map_background.png\n"
                f"In: {os.getcwd()}"
            )

        self.microphones = [
            {"id": "mic1", "name": "Microphone #1", "type": "audio", "position": (200, 150),
             "api_url": "http://db_api_service:8001/api/files/"},
            {"id": "mic2", "name": "Microphone #2", "type": "ultrasound", "position": (500, 300),
             "api_url": "http://db_api_service:8001/api/files/"},
            {"id": "mic3", "name": "Microphone #3", "type": "audio", "position": (350, 450),
             "api_url": "http://localhost:5000/files/environment"}
        ]

        for mic in self.microphones:
            btn = MicrophoneButton(mic["id"], mic["name"], mic["type"], self.map_container)
            btn.move(mic["position"][0], mic["position"][1])
            btn.clicked.connect(lambda checked, m=mic, b=btn: self.on_microphone_clicked(m, b))
            self.mic_buttons[mic["id"]] = btn

        legend = QLabel("circle = Audio Sensor  •  square = Ultrasound Sensor")
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

        # Add map page to stacked widget
        self.stacked_widget.addWidget(self.map_page)
        
        # Recordings page will be added dynamically
        self.recordings_page = None
        
        self.main_layout.addWidget(self.stacked_widget)

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
            self.selection_label.setText(f"Selected {count} {type_text} microphone(s): {', '.join([m.upper() for m in self.selected_mics])}")
            self.view_button.setEnabled(True)
            self.clear_button.setEnabled(True)
    
    def view_selected_recordings(self):
        if not self.selected_mics:
            return
        
        selected_mic_data = []
        for mic in self.microphones:
            if mic["id"] in self.selected_mics:
                selected_mic_data.append(mic)
        
        if self.recordings_page:
            self.stacked_widget.removeWidget(self.recordings_page)
            self.recordings_page.deleteLater()
        
        self.recordings_page = QWidget()
        recordings_layout = QVBoxLayout(self.recordings_page)
        recordings_layout.setContentsMargins(0, 0, 0, 0)
        recordings_layout.setSpacing(0)
        
        # Header with back button
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
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        back_button.clicked.connect(self.show_map)
        
        mic_names = ", ".join([m["name"] for m in selected_mic_data])
        header = QLabel(f"Recordings: {mic_names}")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: white;
        """)
        
        header_layout.addWidget(back_button)
        header_layout.addWidget(header, 1)
        header_layout.addStretch()

        type_text = "AUDIO" if self.selected_type == "audio" else "ULTRASOUND"
        mic_ids = ", ".join([m["id"].upper() for m in selected_mic_data])
        subtitle = QLabel(f"Type: {type_text}  •  Microphones: {mic_ids}")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("""
            font-size: 13px;
            color: white;
            padding: 5px;
            background-color: rgba(0, 0, 0, 0.2);
        """)

        recordings_layout.addWidget(header_container)
        recordings_layout.addWidget(subtitle)

        mic_ids_list = [m["id"] for m in selected_mic_data]
        sound_tab = SoundTab(
            selected_mic_data[0]["api_url"],
            "Recordings",
            mic_ids=mic_ids_list,
            recording_type=self.selected_type,
            parent=self
        )
        recordings_layout.addWidget(sound_tab)
        
        self.stacked_widget.addWidget(self.recordings_page)
        self.stacked_widget.setCurrentWidget(self.recordings_page)
    
    def show_map(self):
        self.stacked_widget.setCurrentWidget(self.map_page)
    
    def adjust_zoom(self, factor: float):
        """Zooms in/out on the map image."""
        pixmap = self.background_label.pixmap()
        if not pixmap:
            return

        current_width = self.background_label.width()
        current_height = self.background_label.height()

        new_width = int(current_width * factor)
        new_height = int(current_height * factor)

        scaled_pixmap = pixmap.scaled(
            new_width, new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.background_label.setPixmap(scaled_pixmap)

    # ======================================================
    #                Zoom and Pan Feature
    # ======================================================
    def setup_zoom_and_pan(self):
        """Initialize variables for zooming and panning."""
        self.zoom_factor = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 3.0
        self.dragging = False
        self.drag_start_pos = None

        self.original_pixmap = self.background_label.pixmap()

    def wheelEvent(self, event):
        """Zoom in/out with mouse wheel."""
        if not self.original_pixmap:
            return

        old_factor = self.zoom_factor
        delta = event.angleDelta().y() / 120  # גלילת עכבר
        if delta > 0:
            self.zoom_factor *= 1.1
        else:
            self.zoom_factor /= 1.1

        # הגבלת זום
        self.zoom_factor = max(self.min_zoom, min(self.max_zoom, self.zoom_factor))

        # עדכון תצוגת תמונה
        self.update_background_zoom()

        # עדכון מיקום המיקרופונים
        scale_ratio = self.zoom_factor / old_factor
        for mic in self.microphones:
            btn = self.mic_buttons[mic["id"]]
            x, y = mic["position"]
            btn.move(int(x * self.zoom_factor), int(y * self.zoom_factor))

    def mousePressEvent(self, event):
        """Start panning the map."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.pos()
            self.map_origin = self.map_container.pos()

    def mouseMoveEvent(self, event):
        """Handle dragging the map."""
        if self.dragging:
            delta = event.pos() - self.drag_start_pos
            new_x = self.map_origin.x() + delta.x()
            new_y = self.map_origin.y() + delta.y()
            self.map_container.move(new_x, new_y)

    def mouseReleaseEvent(self, event):
        """Stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def update_background_zoom(self):
        """Rescale background image smoothly."""
        if not self.original_pixmap:
            return

        scaled = self.original_pixmap.scaled(
            int(800 * self.zoom_factor),
            int(600 * self.zoom_factor),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.background_label.setPixmap(scaled)
        self.background_label.resize(scaled.size())

# ==========================================================
#                      Generic Sound Tab
# ==========================================================

class SoundTab(QWidget):
    def __init__(self, api_url: str, title: str, mic_id: str = None, mic_ids: list = None, recording_type: str = "audio", parent=None):
        super().__init__(parent)
        self.api_url = api_url
        self.title = title
        self.mic_ids = mic_ids if mic_ids else ([mic_id] if mic_id else [])
        self.recording_type = recording_type

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Filters Frame
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 2px solid #e1e4e8;
                border-radius: 12px;
                padding: 15px;
            }
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
            QComboBox {
                padding: 8px;
                border: 2px solid #d1d5da;
                border-radius: 6px;
                background: white;
                min-width: 150px;
            }
            QComboBox:hover {
                border: 2px solid #4A90E2;
            }
        """)

        if recording_type == "ultrasound" or "Plant" in title:
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
            QDateEdit {
                padding: 8px;
                border: 2px solid #d1d5da;
                border-radius: 6px;
                background: white;
            }
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
            QLineEdit {
                padding: 8px;
                border: 2px solid #d1d5da;
                border-radius: 6px;
                background: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #4A90E2;
            }
        """)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
        """)

        row2.addWidget(sort_label)
        row2.addWidget(self.sort_by)
        row2.addWidget(self.search_box, 2)
        row2.addWidget(self.refresh_button)

        filters_layout.addLayout(row1)
        filters_layout.addLayout(row2)

        list_label = QLabel("Available Recordings")
        list_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #333;
            padding: 5px;
        """)

        # Setup table based on recording type
        self.file_table = QTableWidget()

        if recording_type == "ultrasound":
            self.file_table.setColumnCount(6)
            self.file_table.setHorizontalHeaderLabels([
                "File",
                "Device", 
                "Predicted Class",
                "Confidence",
                "Watering Status",
                "Actions"
            ])
        else:  # audio
            self.file_table.setColumnCount(6)
            self.file_table.setHorizontalHeaderLabels([
                "Filename",
                "Device", 
                "Predicted Label",
                "Probability",
                "Aggregation Mode",
                "Actions"
            ])

        # Set column widths
        header = self.file_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        for i in range(self.file_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        self.file_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.file_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.file_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.file_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.file_table.setToolTipDuration(3000)
        for row in range(self.file_table.rowCount()):
            for col in range(self.file_table.columnCount()):
                item = self.file_table.item(row, col)
                if item:
                    item.setToolTip(item.text())

        self.file_table.setStyleSheet("""
            QTableWidget {
                background: #ffffff;
                border: 2px solid #d1d5da;
                border-radius: 10px;
                gridline-color: #e1e4e8;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:hover {
                background-color: #f6f8fa;
            }
            QTableWidget::item:selected {
                background-color: #d6eaff;
                color: #0366d6;
            }
            QHeaderView::section {
                background-color: #f6f8fa;
                padding: 10px;
                border: 1px solid #d1d5da;
                font-weight: bold;
                color: #24292e;
            }
        """)

        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.verticalHeader().setVisible(False)

        # Audio Waveform Visualizer
        waveform_container = QFrame()
        waveform_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 2px solid #4A90E2;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        waveform_layout = QVBoxLayout(waveform_container)
        waveform_layout.setSpacing(5)
        
        waveform_label = QLabel("🎵 Audio Visualizer")
        waveform_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #4A90E2;
            padding: 5px;
        """)
        waveform_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.waveform = AudioWaveform()
        self.waveform.setMinimumHeight(150)
        
        waveform_layout.addWidget(waveform_label)
        waveform_layout.addWidget(self.waveform)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 13px;
            color: #666;
            padding: 8px;
            background-color: #f6f8fa;
            border-radius: 6px;
            border: 1px solid #d1d5da;
        """)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self.player.playbackStateChanged.connect(self.on_playback_state_changed)

        layout.addWidget(filter_frame)
        layout.addWidget(list_label)
        layout.addWidget(self.file_table, 1) 
        layout.addWidget(waveform_container)
        layout.addWidget(self.status_label)

        # Connections
        self.refresh_button.clicked.connect(self.update_list)

        self.update_list()

    # def stop_playback(self):
    #     self.player.stop()
    #     self.waveform.stop_animation()
    #     self.status_label.setText("Stopped")
    #     self.stop_button.setEnabled(False)
    
    def on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.waveform.start_animation()
            self.stop_button.setEnabled(True)
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self.waveform.stop_animation()
            self.stop_button.setEnabled(False)
            if self.status_label.text().startswith("Playing:"):
                self.status_label.setText("Finished")

    def update_list(self):
        self.file_table.setRowCount(0)
        self.file_table.verticalHeader().setDefaultSectionSize(60)
        self.status_label.setText("Loading...")

        params = {
            "type": self.noise_filter.currentText(),
            "date_from": self.date_from.date().toString("yyyy-MM-dd"),
            "date_to": self.date_to.date().toString("yyyy-MM-dd"),
            "search": self.search_box.text().strip(),
            "sort_by": self.sort_by.currentText()
        }
        
        if self.mic_ids:
            params["device_ids"] = ",".join(self.mic_ids)
        
        try:
            response = requests.get(self.api_url, params=params)
            response.raise_for_status()
            data = response.json()

            print(f"[DEBUG] fetched {len(data)} aggregates from {self.api_url}")

            # Populate table
            for f in data:
                row = self.file_table.rowCount()
                self.file_table.insertRow(row)
                self.file_table.setRowHeight(row, 60)

                if self.recording_type == "ultrasound":
                    # ultrasonic_plant_predictions table
                    filename = f.get("file", "")
                    device_id = f.get("device_id", "N/A")
                    pred_class = f.get("predicted_class", "Unknown")
                    confidence = f.get("confidence", 0)
                    watering_status = f.get("watering_status", "N/A")
                    url = f.get("url", "")

                    self.file_table.setItem(row, 0, QTableWidgetItem(filename))
                    self.file_table.setItem(row, 1, QTableWidgetItem(device_id))
                    self.file_table.setItem(row, 2, QTableWidgetItem(pred_class))
                    self.file_table.setItem(row, 3, QTableWidgetItem(f"{confidence:.2f}"))
                    self.file_table.setItem(row, 4, QTableWidgetItem(watering_status))
                else:
                    # agcloud_audio.file_aggregates + files + devices
                    filename = f.get("filename", "")
                    device_id = f.get("device_id", "N/A")
                    label = f.get("predicted_label", "Unknown")
                    prob = f.get("probability", 0)
                    agg_mode = f.get("agg_mode", "")
                    url = f.get("url", "")

                    self.file_table.setItem(row, 0, QTableWidgetItem(filename))
                    self.file_table.setItem(row, 1, QTableWidgetItem(device_id))
                    self.file_table.setItem(row, 2, QTableWidgetItem(label))
                    self.file_table.setItem(row, 3, QTableWidgetItem(f"{prob:.2f}"))
                    self.file_table.setItem(row, 4, QTableWidgetItem(agg_mode))

                # Actions column
                control_widget = QWidget()
                control_layout = QHBoxLayout(control_widget)
                control_layout.setContentsMargins(2, 2, 2, 2)
                control_layout.setSpacing(6)

                play_btn = QPushButton("▶")
                play_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                play_btn.setFixedSize(35, 30)
                play_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #0078d4;
                        color: white;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #005fa3;
                    }
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
                    QPushButton:disabled {
                        background-color: #b0b0b0;
                    }
                    QPushButton:hover:enabled {
                        background-color: #c82333;
                    }
                """)

                play_btn.clicked.connect(lambda checked=False, u=url, p=play_btn, s=stop_btn: self.play_row_audio(u, p, s))
                stop_btn.clicked.connect(lambda checked=False, p=play_btn, s=stop_btn: self.stop_row_audio(p, s))

                control_layout.addWidget(play_btn)
                control_layout.addWidget(stop_btn)
                self.file_table.setCellWidget(row, 6, control_widget)

            if self.file_table.rowCount() == 0:
                self.file_table.insertRow(0)
                empty_item = QTableWidgetItem("No aggregates found")
                empty_item.setForeground(QColor("#999"))
                self.file_table.setItem(0, 0, empty_item)
                self.file_table.setSpan(0, 0, 1, 6)

            self.status_label.setText(f"Loaded {len(data)} aggregates")

        except Exception as e:
            self.status_label.setText("Error loading aggregates")
            QMessageBox.warning(self, "Error", f"Failed to load aggregates:\n{e}")
            
    def play_file(self, file_data):
        try:
            file_name = file_data.get("filename", "")
            file_url = f"{self.api_url}/{file_name}"

            self.player.setSource(QUrl(file_url))
            self.player.play()
            self.status_label.setText(f"Playing: {file_name}")

        except Exception as e:
            self.status_label.setText("Playback failed")
            QMessageBox.warning(self, "Playback Error", f"Failed to play sound:\n{e}")

    def play_row_audio(self, url, play_btn, stop_btn):
        self.player.stop()
        self.waveform.start_animation()
        self.status_label.setText(f"Playing: {url}")

        play_btn.setEnabled(False)
        stop_btn.setEnabled(True)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)

        try:
            self.player.setSource(QUrl(url))
            self.player.play()
        except Exception as e:
            QMessageBox.warning(self, "Playback Error", f"Failed to play:\n{e}")

    def stop_row_audio(self, play_btn, stop_btn):
        self.player.stop()
        self.waveform.stop_animation()
        self.status_label.setText("Stopped")

        play_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #b0b0b0;
            }
            QPushButton:hover:enabled {
                background-color: #c82333;
            }
        """)


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
            QTabBar::tab:hover {
                background: #e1e4e8;
            }
        """)

        audio_url = "http://db_api_service:8001/api/files/"
        plants_url = "http://db_api_service:8001/api/plant-predictions/"

        self.map_tab = ImageMapView()
        self.env_tab = SoundTab(audio_url, "Environment Sounds", recording_type="audio")
        self.plant_tab = SoundTab(plants_url, "Plant Ultrasounds", recording_type="ultrasound")

        self.tabs.addTab(self.map_tab, "Interactive Map")
        self.tabs.addTab(self.env_tab, "Environment Sounds")
        self.tabs.addTab(self.plant_tab, "Plant Ultrasounds")

        layout.addWidget(self.tabs)

    def switch_to_recordings_tab(self, mic_data):
        if mic_data['type'] == 'audio':
            self.tabs.setCurrentWidget(self.env_tab)
        else:
            self.tabs.setCurrentWidget(self.plant_tab)