from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from .irrigation_dashboard import IrrigationDashboard
from dashboard_api import DashboardApi


class IrrigationView(QWidget):
    """Wrapper to integrate IrrigationDashboard into MainWindow"""
    
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        print("[DEBUG] IrrigationView.__init__ called")
        self.api = api
        
        print("[DEBUG] Creating layout...")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create the irrigation dashboard
        print("[DEBUG] Creating IrrigationDashboard...")
        try:
            self.dashboard = IrrigationDashboard()
            print("[DEBUG] IrrigationDashboard created successfully")
            print("[DEBUG] Adding dashboard to layout...")
            layout.addWidget(self.dashboard)
        except Exception as e:
            print(f"[ERROR] Failed to create IrrigationDashboard: {e}")
            import traceback
            traceback.print_exc()
            # Create error placeholder
            error_label = QLabel(f"Failed to load Irrigation Dashboard:\n{str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            layout.addWidget(error_label)
        
        print("[DEBUG] Setting stylesheet...")
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f0f9ff, stop:1 #e0f2fe);
            }
        """)
        print("[DEBUG] IrrigationView.__init__ completed")
