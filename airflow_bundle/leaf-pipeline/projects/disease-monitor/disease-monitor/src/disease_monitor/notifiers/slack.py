from __future__ import annotations
import os
import json
import requests
from typing import Dict, Any
from .base import Notifier, render_text

class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, alert: Dict[str, Any]) -> None:
        text = render_text(alert)
        payload = {"text": text}
        requests.post(self.webhook_url, data=json.dumps(payload), timeout=10)
