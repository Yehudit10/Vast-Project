
from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QTimer
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QAbstractSocket  # ✅ add this
import json


class AlertClient(QObject):
    """
    Connects to the alerts WebSocket gateway and emits signals
    when new alerts or snapshots arrive.
    """
    snapshotReceived = pyqtSignal(list)
    alertReceived = pyqtSignal(dict)
    connectionLost = pyqtSignal()

    def __init__(self, ws_url: str, parent=None):
        super().__init__(parent)
        self.url = QUrl(ws_url)
        self.socket = QWebSocket()
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.textMessageReceived.connect(self._on_message)
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self._try_reconnect)
        self.reconnect_interval_ms = 5000  # retry every 5s
        self._connect()

    def _connect(self):
        print(f"[AlertClient] Connecting to {self.url.toString()}")
        self.socket.open(self.url)

    def _try_reconnect(self):
        # ✅ Use QAbstractSocket.SocketState instead of QWebSocket.SocketState
        if self.socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self.reconnect_timer.stop()
            return
        print("[AlertClient] Attempting reconnect...")
        self._connect()


    def _on_connected(self):
        print("[AlertClient] Connected to alerts gateway.")
        self.reconnect_timer.stop()

    def _on_disconnected(self):
        print("[AlertClient] Disconnected from alerts gateway.")
        self.connectionLost.emit()
        self.reconnect_timer.start(self.reconnect_interval_ms)

    def _on_message(self, msg: str):
        try:
            print(msg)
            payload = json.loads(msg)
            if payload["type"] == "snapshot":
                self.snapshotReceived.emit(payload["items"])
            elif payload["type"] == "alert":
                self.alertReceived.emit(payload["data"])
        except Exception as e:
            print("[AlertClient] Invalid message:", e, msg)
