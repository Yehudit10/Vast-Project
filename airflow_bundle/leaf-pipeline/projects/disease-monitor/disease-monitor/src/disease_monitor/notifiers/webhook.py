from __future__ import annotations
import json
import requests
from typing import Dict, Any
from .base import Notifier

class WebhookNotifier(Notifier):
    def __init__(self, url: str, headers: Dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = headers or {}

    def send(self, alert: Dict[str, Any]) -> None:
        requests.post(self.url, json=alert, headers=self.headers, timeout=10)
