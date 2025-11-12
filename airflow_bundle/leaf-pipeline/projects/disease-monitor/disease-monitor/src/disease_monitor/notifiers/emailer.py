from __future__ import annotations
import os
import smtplib
from email.mime.text import MIMEText
from typing import Dict, Any, List
from .base import Notifier, render_text

class EmailNotifier(Notifier):
    def __init__(self, host: str, port: int, username: str, password_env: str,
                 from_addr: str, to_addrs: List[str]) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password_env = password_env
        self.from_addr = from_addr
        self.to_addrs = to_addrs

    def send(self, alert: Dict[str, Any]) -> None:
        password = os.getenv(self.password_env, "")
        msg = MIMEText(render_text(alert))
        msg["Subject"] = f"Alert: {alert['rule']} {alert['entity_id']}"
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        with smtplib.SMTP(self.host, self.port, timeout=10) as s:
            s.starttls()
            if self.username and password:
                s.login(self.username, password)
            s.sendmail(self.from_addr, self.to_addrs, msg.as_string())
