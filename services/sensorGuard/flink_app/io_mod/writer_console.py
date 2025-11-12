from core.types import Alert

class ConsoleWriter:
    def write(self, alert: Alert) -> None:
        end = alert.end_ts.isoformat() if alert.end_ts else "-"
        print(
            f"[ALERT] type={alert.issue_type} dev={alert.device_id} "
            f"sensor={alert.sensor_type} value={alert.details.get('value')} "
            f"range=[{alert.details.get('min')},{alert.details.get('max')}] "
            f"ts={alert.start_ts.isoformat()} sev={alert.severity}"
        )
