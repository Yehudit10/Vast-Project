from __future__ import annotations
from typing import Dict, Any, List

class Notifier:
    def send(self, alert: Dict[str, Any]) -> None:
        raise NotImplementedError

def render_text(alert: Dict[str, Any]) -> str:
    return (
        f"[{alert['status']}] {alert['rule']} for {alert['entity_id']} "
        f"{alert['window_start']}..{alert['window_end']} "
        f"score={alert['score']:.2f} reasons={alert['meta'].get('reasons')}"
    )
