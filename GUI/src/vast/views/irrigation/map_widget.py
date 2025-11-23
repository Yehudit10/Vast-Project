from pathlib import Path
from PyQt6.QtWidgets import QWidget, QPushButton, QLabel
from PyQt6.QtGui import QPixmap, QMovie, QColor
from PyQt6.QtCore import Qt, QSize

script_dir = Path(__file__).parent

class MapWidget(QWidget):
    def __init__(self, parent=None, map_path=None):
        super().__init__(parent)
        self.sprinklers = {}
        self.map_pixmap = QPixmap(map_path) if map_path else QPixmap()
        self.map_label = QLabel(self)
        self.map_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_label.setStyleSheet('background: transparent;')
        self.map_label.setPixmap(self.map_pixmap)
        self.map_aspect = self.map_pixmap.width() / self.map_pixmap.height() if not self.map_pixmap.isNull() else 16/9
        self.last_scaled_pixmap = self.map_pixmap
        self.resizeEvent(None)

    def resizeEvent(self, event):
        if self.map_pixmap.isNull():
            return
        available_w = max(100, self.width() - 40)
        scaled_h = int(available_w / self.map_aspect)
        scaled_pixmap = self.map_pixmap.scaled(available_w, scaled_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.last_scaled_pixmap = scaled_pixmap
        self.map_label.setPixmap(scaled_pixmap)
        self.map_label.setFixedHeight(scaled_pixmap.height())
        self.map_label.setGeometry(0, 0, available_w, scaled_h)
        for s in self.sprinklers.values():
            # Increased size: multiplied rel_size by 1.5 and increased minimum from 40 to 60
            new_size = max(int(s['rel_size'] * scaled_pixmap.width() * 1.5), 60)
            new_x = int(s['rel_x'] * scaled_pixmap.width() - new_size/2)
            new_y = int(s['rel_y'] * scaled_pixmap.height() - new_size/2)
            s['widget'].setGeometry(new_x, new_y, new_size, new_size)
            if s.get('movie') and isinstance(s['movie'], QMovie):
                s['movie'].setScaledSize(QSize(new_size, new_size))

    def add_sprinkler(self, device_id, rel_x, rel_y, rel_size=0.025, active=False, name=None):
        btn = QPushButton('', self)
        btn.setObjectName(f'spr_{device_id}')
        btn.setToolTip(name or device_id)
        btn.setFixedSize(120, 120)  
        btn.setStyleSheet(self.sprinkler_style(active))
        btn.installEventFilter(self)
        self.sprinklers[device_id] = {
            'widget': btn, 'movie': None, 'active': active,
            'rel_x': rel_x, 'rel_y': rel_y, 'rel_size': rel_size,
            'name': name or device_id
        }
        self.set_sprinkler_state(self.sprinklers[device_id], active)
        self.resizeEvent(None)
        return btn

    def eventFilter(self, obj, event):
        # Show tooltip on hover
        if event.type() == event.Type.Enter:
            for s in self.sprinklers.values():
                if s['widget'] is obj:
                    obj.setToolTip(s.get('name', ''))
        return super().eventFilter(obj, event)

    def set_sprinkler_state(self, s, active):
        btn = s['widget']
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
            btn.setStyleSheet(self.sprinkler_style(True))
            s['movie'] = movie
        else:
            pix = QPixmap(str(script_dir / 'sprinkler_off.png'))
            if pix.isNull():
                pix = QPixmap(btn.width(), btn.height()); pix.fill(QColor('#6b7280'))
            lbl.setPixmap(pix.scaled(btn.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            lbl.show()
            btn.setStyleSheet(self.sprinkler_style(False))
            s['movie'] = None
        s['active'] = active

    def sprinkler_style(self, active=False):
        base = f"""
        QPushButton {{
            width: 120px; height: 120px; border-radius: 60px; background: {'#10b981' if active else '#6b7280'};
            font-weight: bold;
            color: white;
        }}
        QPushButton:hover {{}}
        """
        return base

    def show_tooltip(self, device_id):
        s = self.sprinklers.get(device_id)
        if s:
            s['widget'].setToolTip(s.get('name', device_id))
