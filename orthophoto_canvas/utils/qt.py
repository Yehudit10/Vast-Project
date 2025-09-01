from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QPen, QBrush, QColor, QFont
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsEllipseItem, QGraphicsSimpleTextItem

def add_round_marker(scene: QGraphicsScene, pos: QPointF, radius: float = 4.0,
                     color: QColor = QColor(220, 30, 30)) -> QGraphicsEllipseItem:
    """
    Add a simple circle marker to the scene.
    TODO: expose pen/brush via params if needed.
    """
    r = radius
    item = QGraphicsEllipseItem(pos.x() - r, pos.y() - r, 2 * r, 2 * r)
    item.setPen(QPen(color))
    item.setBrush(QBrush(color.lighter(140)))
    scene.addItem(item)
    return item

def add_label(scene: QGraphicsScene, pos: QPointF, text: str,
              color: QColor = QColor(20, 20, 20)) -> QGraphicsSimpleTextItem:
    """
    Add a small text label near a point.
    """
    t = QGraphicsSimpleTextItem(text)
    t.setBrush(QBrush(color))
    font = QFont()
    font.setPointSize(8)
    t.setFont(font)
    t.setPos(pos.x() + 6, pos.y() - 6)
    scene.addItem(t)
    return t
