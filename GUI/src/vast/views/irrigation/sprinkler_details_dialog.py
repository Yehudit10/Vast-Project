# from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
# from PyQt6.QtCore import Qt

# class SprinklerDetailsDialog(QDialog):
#     def __init__(self, parent, device_id, details):
#         super().__init__(parent)
#         self.setWindowTitle(f"Sprinkler {device_id} Details")
#         self.setModal(True)
#         layout = QVBoxLayout(self)
#         self.label = QLabel(f"Details for {device_id}")
#         layout.addWidget(self.label)
#         self.details_label = QLabel(str(details))
#         layout.addWidget(self.details_label)
#         self.show_history_btn = QPushButton("Show History")
#         layout.addWidget(self.show_history_btn)
#         self.show_history_btn.clicked.connect(self.on_show_history)
#         self.history_callback = None

#     def on_show_history(self):
#         if self.history_callback:
#             self.history_callback()
