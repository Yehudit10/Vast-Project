from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import random

@dataclass
class Kpis:
    sensors_total: int
    sensors_active: int
    sensors_inactive: int
    alerts_last_6h: int
    processing_jobs_running: int
    predictions_available: int

@dataclass
class SensorRow:
    sensor_id: str
    name: str
    state: str # "active" | "inactive" | "broken"
    last_seen: datetime


class DashboardApi:
    """
    Simulated API that returns KPIs and sensor lists.
    Replace with real HTTP calls in production.
    """

    def get_kpis(self) -> Kpis:
        total = 120
        active = random.randint(95, 110)
        inactive = total - active
        return Kpis(
            sensors_total=total,
            sensors_active=active,
            sensors_inactive=inactive,
            alerts_last_6h=random.randint(1, 20),
            processing_jobs_running=random.randint(0, 5),
            predictions_available=random.randint(0, 3),
        )


    def get_inactive_sensors(self, limit: int = 20) -> list[SensorRow]:
        rows: list[SensorRow] = []
        n = random.randint(5, 15)
        for i in range(min(n, limit)):
            last_seen = datetime.now() - timedelta(minutes=random.randint(10, 240))
            rows.append(
                SensorRow(
                    sensor_id=f"S{i:03d}",
                    name=f"Sensor-{i:03d}",
                    state=random.choice(["inactive", "broken"]),
                    last_seen=last_seen,
                )
            )
        return rows