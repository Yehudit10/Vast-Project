from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any

# ------------------------------
# IO: Postgres-only
# ------------------------------
class IOConfig(BaseModel):
    postgres_url: str  # required: Postgres-only

    @model_validator(mode="after")
    def _ensure_pg_only(self):
        url = self.postgres_url
        if not isinstance(url, str) or not url.lower().startswith(
            ("postgresql://", "postgresql+psycopg2://")
        ):
            raise ValueError("io.postgres_url is required and must be a PostgreSQL URL.")
        return self


# ------------------------------
# Windows/Baseline/Rules/Alerting
# ------------------------------
class WindowsConfig(BaseModel):
    frequency: str = "D"
    timezone: str = "UTC"

class BaselineConfig(BaseModel):
    method: str = "median"
    lookback_periods: int = 28
    min_history: int = 7
    seasonality: Optional[int] = None

class CountAnomalyRule(BaseModel):
    enabled: bool = True
    method: str = "zscore"
    z_threshold: float = 3.0
    iqr_k: float = 1.5
    min_count: int = 3

class WorseningRule(BaseModel):
    enabled: bool = True
    method: str = "slope"
    slope_lookback: int = 7
    slope_min: float = 0.02
    min_periods: int = 5
    ewma_span: int = 7
    ewma_threshold: float = 0.6

class RulesConfig(BaseModel):
    count_anomaly: CountAnomalyRule = Field(default_factory=CountAnomalyRule)
    worsening: WorseningRule = Field(default_factory=WorseningRule)

class AlertingConfig(BaseModel):
    dedup_cooldown_windows: int = 3
    resolve_after_no_anomaly: int = 3
    rate_limit_per_run: int = 100
    group_by_window: bool = True


# ------------------------------
# Delivery: add Alertmanager section 
# ------------------------------
class SlackConfig(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = None

class WebhookConfig(BaseModel):
    enabled: bool = False
    url: Optional[str] = None
    headers: Dict[str, Any] = Field(default_factory=dict)

class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password_env: str = "SMTP_PASSWORD"
    from_addr: str = ""
    to_addrs: List[str] = Field(default_factory=list)

class AlertmanagerConfig(BaseModel):
    enabled: bool = False
    url: Optional[str] = None
    default_severity: str = "warning"
    extra_labels: Dict[str, str] = Field(default_factory=dict)
    auth: Dict[str, Any] = Field(default_factory=lambda: {"type": "none"})  # {"type":"none"} or {"type":"basic",...}

class DeliveryConfig(BaseModel):
    slack: SlackConfig = Field(default_factory=SlackConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    alertmanager: AlertmanagerConfig = Field(default_factory=AlertmanagerConfig)


# ------------------------------
# Run
# ------------------------------
class RunConfig(BaseModel):
    dry_run: bool = False
    limit_entities: Optional[int] = None
    disease_filter: Optional[List[str]] = None


# ------------------------------
# AppConfig
# ------------------------------
class AppConfig(BaseModel):
    io: IOConfig
    windows: WindowsConfig = Field(default_factory=WindowsConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    alerting: AlertingConfig = Field(default_factory=AlertingConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    run: RunConfig = Field(default_factory=RunConfig)
