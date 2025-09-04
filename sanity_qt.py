# sanity_qt.py
import sys
from PyQt5.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)
w = QWidget()
w.setWindowTitle("PyQt5 sanity")
w.resize(400, 300)
w.show()
app.exec()
