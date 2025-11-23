from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QLineEdit, QFormLayout, QScrollArea, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from io import BytesIO
try:
    from minio import Minio
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

# DB connection helper (same as in main app)
def get_db_connection():
    return psycopg2.connect(
        # host="postgres",
        host="postgres",
        port=5432,
        user="missions_user",
        password="pg123",
        dbname="missions_db",
        cursor_factory=RealDictCursor
    )

# MinIO connection helper
def get_minio_client():
    """Get MinIO client for accessing imagery bucket."""
    if not MINIO_AVAILABLE:
        print("[DEBUG] MinIO client not available (minio package not installed)")
        return None
    try:
        # Try multiple endpoints for flexibility
        endpoints = [
            "minio-hot:9000",      # Docker internal
            "localhost:9001",      # Desktop/host
            "127.0.0.1:9001",      # Loopback
        ]
        
        for endpoint in endpoints:
            try:
                client = Minio(
                    endpoint=endpoint,
                    access_key="minioadmin",
                    secret_key="minioadmin123",
                    secure=False
                )
                # Test connection
                client.list_buckets()
                print(f"[DEBUG] MinIO connected successfully at {endpoint}")
                return client
            except Exception as e:
                print(f"[DEBUG] MinIO endpoint {endpoint} failed: {type(e).__name__}")
                continue
        
        print("[DEBUG] MinIO: all endpoints failed")
        return None
    except Exception as e:
        print(f"[DEBUG] MinIO connection error: {e}")
        return None

def fetch_image_from_minio(image_path: str) -> bytes:
    """
    Fetch an image from MinIO 'imagery' bucket.
    
    Args:
        image_path: The key/path to the image in MinIO (e.g., 'folder/image.jpg')
    
    Returns:
        Image bytes, or None if fetch fails
    """
    if not MINIO_AVAILABLE:
        print("MinIO client not available")
        return None
    
    try:
        client = get_minio_client()
        if client is None:
            return None
        
        response = client.get_object("imagery", image_path)
        image_bytes = response.read()
        return image_bytes
    except Exception as e:
        print(f"Error fetching image from MinIO: {e}")
        return None

class SprinklerDetailsDialogNew(QWidget):
    """Tabbed sprinkler details dialog with Details, History, Parameters, Last Image, and Close tabs."""
    
    history_requested = pyqtSignal(str)  # device_id
    parameters_saved = pyqtSignal(str, dict)  # device_id, params
    
    def __init__(self, parent, device_id, details):
        super().__init__(parent)
        print(f"[DEBUG] SprinklerDetailsDialogNew.__init__ called for device_id={device_id}")
        self.device_id = device_id
        self.details = details
        self.current_tab = 'Details'
        self.edited_params = {}
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        print(f"[DEBUG] Setting up window for {device_id}")
        
        # Main card
        self.card = QWidget(self)
        self.card.setStyleSheet("""
            background: white;
            border-radius: 14px;
        """)
        
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.card.setGraphicsEffect(shadow)
        
        # Main layout
        main_layout = QVBoxLayout(self.card)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)
        
        # Header section with title only
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        
        # Title
        title = QLabel(f"Sprinkler {device_id}")
        title.setFont(QFont('Segoe UI', 16, QFont.Weight.Bold))
        title.setStyleSheet("color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #0891b2);")
        header_layout.addWidget(title)
        
        main_layout.addLayout(header_layout)
        
        # Content area (will be replaced based on active tab)
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.content_area, stretch=1)
        
        # Buttons row at bottom
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()
        
        self.tab_buttons = {}
        self.create_tab_buttons(btn_row)
        
        main_layout.addLayout(btn_row)
        
        # Sizing and positioning
        w, h = int(parent.width() * 0.6), int(parent.height() * 0.65)
        self.setGeometry((parent.width() - w) // 2, (parent.height() - h) // 2, w, h)
        self.card.setGeometry(0, 0, w, h)
        
        # Fade-in animation
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(220)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.setWindowOpacity(0.0)
        self.opacity_anim.start()
        
        print(f"[DEBUG] Dialog initialized, showing Details tab")
        # Show Details tab initially
        self.show_tab('Details')
    
    def create_tab_buttons(self, layout):
        """Create all 5 tab buttons and add them to the layout."""
        tabs = ['Details', 'History', 'Parameters', 'Last Image', 'Close']
        for tab in tabs:
            btn = QPushButton(tab)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(100)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self.get_button_style(tab == self.current_tab))
            btn.clicked.connect(lambda checked, t=tab: self.switch_tab(t))
            self.tab_buttons[tab] = btn
            # Add all buttons to layout
            layout.addWidget(btn)
    
    def get_button_style(self, active=False):
        if active:
            return """
            QPushButton {
                background: #06b6d4;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 8px 16px;
            }
            """
        else:
            return """
            QPushButton {
                background: #e5e7eb;
                color: #374151;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #d1d5db;
            }
            """
    
    def switch_tab(self, tab_name):
        """Switch to a different tab."""
        print(f"[DEBUG] switch_tab() called: {tab_name}")
        if tab_name == 'Close':
            self.close()
            return
        
        self.current_tab = tab_name
        
        # Clear current content safely using takeAt and deleteLater
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Show selected tab
        self.show_tab(tab_name)
        
        # Update button styling
        self.update_button_styles()
        print(f"[DEBUG] Switched to {tab_name} tab")
    
    def update_button_styles(self):
        """Update button styles: active button highlighted, others normal."""
        for tab_name, btn in self.tab_buttons.items():
            btn.setStyleSheet(self.get_button_style(tab_name == self.current_tab))
    
    def show_tab(self, tab_name):
        """Display content for a tab."""
        if tab_name == 'Details':
            self.show_details_tab()
        elif tab_name == 'History':
            self.show_history_tab()
        elif tab_name == 'Parameters':
            self.show_parameters_tab()
        elif tab_name == 'Last Image':
            self.show_last_image_tab()
    
    def show_details_tab(self):
        """Display the details tab with improved layout and styling."""
        # Status section
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(10)
        
        status_dot = QLabel('●')
        status_dot.setFont(QFont('Arial', 14))
        status_color = '#10b981' if self.details.get('active') else '#9ca3af'
        status_dot.setStyleSheet(f"color: {status_color}")
        
        status_text = QLabel('Active' if self.details.get('active') else 'Inactive')
        status_text.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        status_text.setStyleSheet(f"color: {status_color}")
        
        status_layout.addWidget(status_dot)
        status_layout.addWidget(status_text)
        status_layout.addStretch()
        
        self.content_layout.addWidget(status_container)
        self.content_layout.addSpacing(12)
        
        # Soil Moisture section
        moisture_label = QLabel('Soil Moisture')
        moisture_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        moisture_label.setStyleSheet("color: #1f2937;")
        self.content_layout.addWidget(moisture_label)
        
        dry_ratio = self.details.get('dry_ratio', 0)
        moisture_percent = int(dry_ratio * 100)
        
        # Percentage label above bar
        moisture_value_label = QLabel(f"{moisture_percent}%")
        moisture_value_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        moisture_value_label.setStyleSheet("color: #06b6d4;")
        self.content_layout.addWidget(moisture_value_label)
        
        # Progress bar
        moisture_bar = QProgressBar()
        moisture_bar.setRange(0, 100)
        moisture_bar.setValue(moisture_percent)
        moisture_bar.setFixedHeight(12)
        moisture_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                background: #f3f4f6;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #06b6d4, stop:1 #0891b2);
                border-radius: 5px;
            }
        """)
        self.content_layout.addWidget(moisture_bar)
        self.content_layout.addSpacing(16)
        
        # Confidence section
        confidence_label = QLabel('Model Confidence')
        confidence_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        confidence_label.setStyleSheet("color: #1f2937;")
        self.content_layout.addWidget(confidence_label)
        
        conf = self.details.get('confidence', 0)
        conf_percent = int(conf * 100)
        
        # Determine color based on confidence
        if conf >= 0.75:
            conf_color = '#10b981'
        elif conf >= 0.4:
            conf_color = '#f59e0b'
        else:
            conf_color = '#ef4444'
        
        # Percentage label above bar
        conf_value_label = QLabel(f"{conf_percent}%")
        conf_value_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        conf_value_label.setStyleSheet(f"color: {conf_color};")
        self.content_layout.addWidget(conf_value_label)
        
        # Confidence progress bar
        conf_bar = QProgressBar()
        conf_bar.setRange(0, 100)
        conf_bar.setValue(conf_percent)
        conf_bar.setFixedHeight(12)
        conf_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                background: #f3f4f6;
            }}
            QProgressBar::chunk {{
                background: {conf_color};
                border-radius: 5px;
            }}
        """)
        self.content_layout.addWidget(conf_bar)
        self.content_layout.addSpacing(16)
        
        # Decision section
        decision = self.details.get('decision', 'noop')
        # Replace 'noop' with 'no operation'
        if decision == 'noop':
            decision = 'no operation'
        
        decision_label = QLabel('Decision')
        decision_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        decision_label.setStyleSheet("color: #1f2937;")
        self.content_layout.addWidget(decision_label)
        
        # Decision badge
        decision_badge = QLabel(decision.upper())
        decision_badge.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        decision_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        decision_badge.setFixedHeight(32)
        
        if decision == 'run':
            badge_color = '#10b981'
            bg_color = '#d1fae5'
        elif decision == 'stop':
            badge_color = '#ef4444'
            bg_color = '#fee2e2'
        else:  # no operation
            badge_color = '#f59e0b'
            bg_color = '#fef3c7'
        
        decision_badge.setStyleSheet(f"""
            background: {bg_color};
            color: {badge_color};
            border-radius: 6px;
            padding: 6px;
        """)
        self.content_layout.addWidget(decision_badge)
        
        self.content_layout.addStretch()
    
    def show_history_tab(self):
        """Display the history tab with a beautifully styled table inside the dialog."""
        records = []
        try:
            # Direct database query to avoid import issues
            query = """
                SELECT e.device_id, e.dry_ratio, e.decision, e.confidence, e.patch_count, e.ts
                FROM soil_moisture_events e
                WHERE e.device_id = %s
                ORDER BY e.ts DESC
                LIMIT 10
            """
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.device_id,))
                    records = cur.fetchall()
                    # Convert tuples to dicts if needed
                    if records and not isinstance(records[0], dict):
                        columns = ['device_id', 'dry_ratio', 'decision', 'confidence', 'patch_count', 'ts']
                        records = [dict(zip(columns, row)) for row in records]
        except Exception as e:
            print(f"Error fetching history: {e}")
            records = []
        
        # Add title label
        title = QLabel('Last 10 Events')
        title.setFont(QFont('Segoe UI', 9, QFont.Weight.Bold))
        title.setStyleSheet("color: #374151; margin-bottom: 8px;")
        self.content_layout.addWidget(title)
        
        # History table with better column layout
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(['Time', 'Soil %', 'Confidence %', 'Decision', 'Patches'])
        table.setAlternatingRowColors(True)
        table.setColumnWidth(0, 270)  # Time
        table.setColumnWidth(1, 70)  # Soil %
        table.setColumnWidth(2, 70)  # Confidence %
        table.setColumnWidth(3, 130)  # Decision (increased from 100 to 130)
        table.setColumnWidth(4, 70)  # Patches
        table.resizeRowsToContents()
        table.setWordWrap(True)
        # Set minimum row height for better visibility
        table.verticalHeader().setDefaultSectionSize(32)
        
        # Professional styling with better padding
        table.setStyleSheet("""
            QTableWidget {
                background: white;
                alternate-background-color: #f9fafb;
                gridline-color: #e5e7eb;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
            QHeaderView::section {
                background: #f3f4f6;
                padding: 12px;
                border: none;
                font-weight: bold;
                color: #374151;
                border-right: 1px solid #d1d5db;
            }
            QTableWidget::item {
                padding: 12px;
                border-bottom: 1px solid #e5e7eb;
            }
        """)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Populate rows
        for row in records:
            r = table.rowCount()
            table.insertRow(r)
            
            # Column 0: Timestamp
            ts_item = QTableWidgetItem(str(row['ts']))
            ts_item.setFont(QFont('Courier', 9))
            ts_item.setForeground(QColor('#6b7280'))
            table.setItem(r, 0, ts_item)
            
            # Column 1: Soil Moisture % (dry_ratio as %)
            dry_percent = int(row['dry_ratio'] * 100)
            moisture_item = QTableWidgetItem(f"{dry_percent}%")
            moisture_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            moisture_item.setFont(QFont('Courier', 9))
            table.setItem(r, 1, moisture_item)
            
            # Column 2: Confidence % 
            conf_percent = int(row['confidence'] * 100)
            conf_item = QTableWidgetItem(f"{conf_percent}%")
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_item.setFont(QFont('Courier', 9))
            table.setItem(r, 2, conf_item)
            
            # Column 3: Decision with color coding
            decision = row['decision']
            if decision == 'noop':
                decision = 'no operation'
            
            # Use shorter display text for better fit in cell
            decision_text = {
                'run': 'RUN',
                'stop': 'STOP',
                'no operation': 'NO OPERATION'
            }.get(decision, decision.upper())
            
            dec_item = QTableWidgetItem(decision_text)
            dec_item.setFont(QFont('Segoe UI', 9, QFont.Weight.Bold))
            dec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Set background and text colors with proper contrast
            if decision == 'run':
                dec_item.setBackground(QColor("#dde9e5"))
                dec_item.setForeground(QColor("#58b7e4"))  # White text on green
            elif decision == 'stop':
                dec_item.setBackground(QColor('#fee2e2'))  # Light red background
                dec_item.setForeground(QColor('#dc2626'))  # Dark red text
            else:  # no operation
                dec_item.setBackground(QColor('#f59e0b'))
                dec_item.setForeground(QColor('#1f2937'))  # Dark text for better contrast on orange
            
            table.setItem(r, 3, dec_item)
            
            # Column 4: Patches (patch count)
            patch_item = QTableWidgetItem(f"{row.get('patch_count', 0)}")
            patch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            patch_item.setFont(QFont('Courier', 9))
            table.setItem(r, 4, patch_item)
        
        self.content_layout.addWidget(table, stretch=1)
    
    def show_parameters_tab(self):
        """Display the parameters tab with editable fields."""
        try:
            params = self.fetch_parameters()
        except Exception:
            params = {}
        
        # Form for parameters
        form = QFormLayout()
        form.setSpacing(16)
        form.setContentsMargins(0, 0, 0, 0)
        
        # Define input styling
        input_style = """
            QLineEdit {
                border: 2px solid #e5e7eb;
                border-radius: 8px;
                padding: 6px;
                background: #f9fafb;
                color: #1f2937;
                font-size: 11pt;
                font-weight: 500;
            }
            QLineEdit:focus {
                border: 2px solid #06b6d4;
                background: #ffffff;
            }
            QLineEdit:hover {
                border: 2px solid #d1d5db;
            }
        """
        
        # Define label styling
        label_style = """
            color: #374151;
            font-weight: bold;
            font-size: 11pt;
        """
        
        self.param_inputs = {}
        
        # Dry Ratio High
        dry_high_label = QLabel('Dry Ratio High:')
        dry_high_label.setStyleSheet(label_style)
        dry_high_input = QLineEdit()
        dry_high_input.setText(str(params.get('dry_ratio_high', 0.7)))
        dry_high_input.setStyleSheet(input_style)
        dry_high_input.setMinimumHeight(40)
        self.param_inputs['dry_ratio_high'] = dry_high_input
        form.addRow(dry_high_label, dry_high_input)
        
        # Dry Ratio Low
        dry_low_label = QLabel('Dry Ratio Low:')
        dry_low_label.setStyleSheet(label_style)
        dry_low_input = QLineEdit()
        dry_low_input.setText(str(params.get('dry_ratio_low', 0.4)))
        dry_low_input.setStyleSheet(input_style)
        dry_low_input.setMinimumHeight(40)
        self.param_inputs['dry_ratio_low'] = dry_low_input
        form.addRow(dry_low_label, dry_low_input)
        
        # Min Patches
        min_patches_label = QLabel('Min Patches:')
        min_patches_label.setStyleSheet(label_style)
        min_patches_input = QLineEdit()
        min_patches_input.setText(str(params.get('min_patches', 1)))
        min_patches_input.setStyleSheet(input_style)
        min_patches_input.setMinimumHeight(40)
        self.param_inputs['min_patches'] = min_patches_input
        form.addRow(min_patches_label, min_patches_input)
        
        # Duration (minutes)
        # duration_label = QLabel('Duration (min):')
        # duration_label.setStyleSheet(label_style)
        # duration_input = QLineEdit()
        # duration_input.setText(str(params.get('duration_min', 30)))
        # duration_input.setStyleSheet(input_style)
        # duration_input.setMinimumHeight(40)
        # self.param_inputs['duration_min'] = duration_input
        # form.addRow(duration_label, duration_input)
        
        # Save button
        save_btn = QPushButton('Save Parameters')
        save_btn.setStyleSheet("""
            QPushButton {
                background: #10b981;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 16px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: #059669;
            }
            QPushButton:pressed {
                background: #047857;
            }
        """)
        save_btn.setMinimumHeight(44)
        save_btn.clicked.connect(self.save_parameters)
        
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_widget.setLayout(form)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.content_layout.addWidget(scroll)
        self.content_layout.addSpacing(12)
        self.content_layout.addWidget(save_btn)
    
    def fetch_parameters(self):
        """Fetch parameters from irrigation_policies table."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT dry_ratio_high, dry_ratio_low, min_patches, duration_min 
                        FROM irrigation_policies 
                        WHERE device_id = %s
                    """
                    cur.execute(query, (self.device_id,))
                    row = cur.fetchone()
                    
                    if row:
                        # Handle both tuple and dict-like responses
                        if isinstance(row, (tuple, list)):
                            return {
                                'dry_ratio_high': float(row[0]) if row[0] is not None else 0.7,
                                'dry_ratio_low': float(row[1]) if row[1] is not None else 0.4,
                                'min_patches': int(row[2]) if row[2] is not None else 1,
                                'duration_min': int(row[3]) if row[3] is not None else 30
                            }
                        else:
                            # Dictionary-like response
                            return {
                                'dry_ratio_high': float(row.get('dry_ratio_high', 0.7)),
                                'dry_ratio_low': float(row.get('dry_ratio_low', 0.4)),
                                'min_patches': int(row.get('min_patches', 1)),
                                'duration_min': int(row.get('duration_min', 30))
                            }
        except Exception as e:
            print(f"Error fetching parameters: {type(e).__name__}: {str(e)}")
        return {}
    
    def save_parameters(self):
        """Save parameters to irrigation_policies table."""
        try:
            # Validate and convert inputs
            dry_ratio_high = float(self.param_inputs['dry_ratio_high'].text())
            dry_ratio_low = float(self.param_inputs['dry_ratio_low'].text())
            min_patches = int(self.param_inputs['min_patches'].text())
            duration_min = 10 #int(self.param_inputs['duration_min'].text())
            
            # Basic validation
            if not (0 <= dry_ratio_high <= 1):
                raise ValueError("Dry Ratio High must be between 0 and 1")
            if not (0 <= dry_ratio_low <= 1):
                raise ValueError("Dry Ratio Low must be between 0 and 1")
            if min_patches < 0:
                raise ValueError("Min Patches must be positive")
            if duration_min < 0:
                raise ValueError("Duration must be positive")
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        INSERT INTO irrigation_policies 
                        (device_id, dry_ratio_high, dry_ratio_low, min_patches, duration_min)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                        dry_ratio_high = EXCLUDED.dry_ratio_high,
                        dry_ratio_low = EXCLUDED.dry_ratio_low,
                        min_patches = EXCLUDED.min_patches,
                        duration_min = EXCLUDED.duration_min
                    """
                    cur.execute(query, (self.device_id, dry_ratio_high, dry_ratio_low, min_patches, duration_min))
                conn.commit()
            
            # Show success message
            msg_label = QLabel("✓ Parameters saved successfully!")
            msg_label.setStyleSheet("color: #10b981; font-weight: bold; padding: 8px;")
            self.content_layout.addWidget(msg_label)
            print(f"Parameters saved for device {self.device_id}")
            
        except ValueError as ve:
            print(f"Validation error: {ve}")
            msg_label = QLabel(f"✗ Validation error: {ve}")
            msg_label.setStyleSheet("color: #ef4444; font-weight: bold; padding: 8px;")
            self.content_layout.addWidget(msg_label)
        except Exception as e:
            print(f"Error saving parameters: {type(e).__name__}: {str(e)}")
            msg_label = QLabel(f"✗ Error: {type(e).__name__}")
            msg_label.setStyleSheet("color: #ef4444; font-weight: bold; padding: 8px;")
            self.content_layout.addWidget(msg_label)
    
    def show_last_image_tab(self):
        """Display the last image tab with image from MinIO."""
        print(f"[DEBUG] show_last_image_tab() called for {self.device_id}")
        try:
            # Query database for the most recent image path
            query = """
                SELECT extra->>'image_path' as image_path, ts
                FROM soil_moisture_events
                WHERE device_id = %s AND extra->>'image_path' IS NOT NULL
                ORDER BY ts DESC
                LIMIT 1
            """
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.device_id,))
                    row = cur.fetchone()
                    print(f"[DEBUG] Query result: {row}")
                    
                    if row and row.get('image_path'):
                        image_path = row['image_path']
                        ts = row.get('ts', 'Unknown')
                        print(f"[DEBUG] Found image path: {image_path}, ts: {ts}")
                        
                        # Fetch image from MinIO
                        image_bytes = fetch_image_from_minio(image_path)
                        
                        if image_bytes:
                            print(f"[DEBUG] Successfully fetched image, size: {len(image_bytes)} bytes")
                            # Display the image
                            pixmap = QPixmap()
                            pixmap.loadFromData(image_bytes)
                            
                            if not pixmap.isNull():
                                # Create container for image display
                                image_container = QWidget()
                                image_layout = QVBoxLayout(image_container)
                                image_layout.setContentsMargins(0, 0, 0, 0)
                                image_layout.setSpacing(12)
                                
                                # Timestamp label
                                ts_label = QLabel(f"Timestamp: {ts}")
                                ts_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
                                ts_label.setStyleSheet("color: #6b7280;")
                                image_layout.addWidget(ts_label)
                                
                                # Image path label
                                path_label = QLabel(f"Path: {image_path}")
                                path_label.setFont(QFont('Courier', 9))
                                path_label.setStyleSheet("color: #9ca3af; word-wrap: true;")
                                path_label.setWordWrap(True)
                                image_layout.addWidget(path_label)
                                
                                # Scale image to fit in dialog
                                max_width = int(self.card.width() * 0.8)
                                max_height = 400
                                scaled_pixmap = pixmap.scaledToWidth(
                                    max_width,
                                    Qt.TransformationMode.SmoothTransformation
                                )
                                if scaled_pixmap.height() > max_height:
                                    scaled_pixmap = scaled_pixmap.scaledToHeight(
                                        max_height,
                                        Qt.TransformationMode.SmoothTransformation
                                    )
                                
                                # Image label
                                img_label = QLabel()
                                img_label.setPixmap(scaled_pixmap)
                                img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                                img_label.setStyleSheet("border: 1px solid #e5e7eb; border-radius: 6px;")
                                image_layout.addWidget(img_label, stretch=1)
                                
                                self.content_layout.addWidget(image_container, stretch=1)
                                print(f"[DEBUG] Image displayed successfully")
                                return
                            else:
                                error_msg = "Failed to load image from bytes"
                                print(f"[DEBUG] {error_msg}")
                                self.show_image_error(error_msg)
                                return
                        else:
                            error_msg = f"Could not fetch image from MinIO: {image_path}"
                            print(f"[DEBUG] {error_msg}")
                            self.show_image_error(error_msg)
                            return
                    else:
                        # No image path found in recent events
                        error_msg = "No image data available for this device"
                        print(f"[DEBUG] {error_msg}")
                        self.show_image_error(error_msg)
                        return
        except Exception as e:
            error_msg = f"Error fetching image: {str(e)}"
            print(f"[DEBUG] {error_msg}")
            import traceback
            traceback.print_exc()
            self.show_image_error(error_msg)
    
    def show_image_error(self, error_message: str):
        """Display error message in the image tab."""
        error_container = QWidget()
        error_layout = QVBoxLayout(error_container)
        error_layout.setContentsMargins(0, 0, 0, 0)
        error_layout.addStretch()
        
        error_label = QLabel(error_message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setFont(QFont('Segoe UI', 12))
        error_label.setStyleSheet("color: #f59e0b; padding: 20px;")
        error_label.setWordWrap(True)
        error_layout.addWidget(error_label)
        
        error_layout.addStretch()
        self.content_layout.addWidget(error_container, stretch=1)
