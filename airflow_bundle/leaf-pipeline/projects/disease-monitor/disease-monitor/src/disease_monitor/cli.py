import argparse
import json
import logging
from typing import Dict, Any, List

import yaml
import pandas as pd

from .logging_utils import setup_logging
from .config import AppConfig
from . import io as io_mod
from .baseline import compute_baseline
from .rules import apply_rules
from .alerting import enforce_policies
from .notifiers.base import Notifier
from .notifiers.slack import SlackNotifier
from .notifiers.webhook import WebhookNotifier
from .notifiers.emailer import EmailNotifier
from .notifiers.kafka_notifier import KafkaNotifier
from .io import load_inputs_from_postgres , upsert_alerts_pg  , fetch_open_alerts_pg


LOGGER = logging.getLogger("disease_monitor")


def parse_args():
    parser = argparse.ArgumentParser(description="Offline disease anomaly detector")
    parser.add_argument("--config", required=True, help="Path to config file (YAML)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    AppConfig(**cfg)  # validation
    return cfg

def build_notifiers(cfg: Dict[str, Any]) -> List[Notifier]:
    ns: List[Notifier] = []
    d = cfg.get("delivery", {})

    kafka_cfg = d.get("kafka", {})
    if kafka_cfg.get("enabled"):
        brokers = kafka_cfg["brokers"]
        topic = kafka_cfg.get("topic", "alerts")
        ns.append(KafkaNotifier(brokers, topic))
        LOGGER.info("Using KafkaNotifier to send alerts.")
        return ns 
    
    slack = d.get("slack", {})
    if slack.get("enabled") and slack.get("webhook_url"):
        ns.append(SlackNotifier(slack["webhook_url"]))

    webhook = d.get("webhook", {})
    if webhook.get("enabled") and webhook.get("url"):
        ns.append(WebhookNotifier(webhook["url"], webhook.get("headers") or {}))

    email = d.get("email", {})
    if email.get("enabled") and email.get("to_addrs"):
        ns.append(EmailNotifier(email["smtp_host"], email["smtp_port"], email["username"],
                                email["password_env"], email["from_addr"], email["to_addrs"]))
    return ns

def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)
    cfg = load_config(args.config)

    tz = cfg["windows"]["timezone"]
    freq = cfg["windows"]["frequency"]

    # Load inputs
    det, reg = load_inputs_from_postgres(cfg["io"]["postgres_url"], tz, cfg)

    # Optional filters
    run_cfg = cfg["run"]
    if run_cfg.get("disease_filter"):
        det = det[det["disease_type"].isin(run_cfg["disease_filter"])]
    if run_cfg.get("limit_entities"):
        keep = det["entity_id"].drop_duplicates().head(run_cfg["limit_entities"]).tolist()
        det = det[det["entity_id"].isin(keep)]

    # Aggregation + baseline
    agg = io_mod.aggregate(det, freq=freq)
    agg_bl = compute_baseline(
        agg,
        method=cfg["baseline"]["method"],
        lookback=cfg["baseline"]["lookback_periods"],
        min_history=cfg["baseline"]["min_history"],
        seasonality=cfg["baseline"]["seasonality"],
    )

    # Rules
    candidates = apply_rules(agg_bl, cfg)
    LOGGER.info("Candidate alerts: %d", 0 if candidates is None else len(candidates))

    # Policies need knowledge of currently OPEN alerts from the chosen backend
    open_alerts = fetch_open_alerts_pg(cfg["io"]["postgres_url"])
    alerts = enforce_policies(candidates, open_alerts, cfg)
    LOGGER.info("Alerts after policies: %d", len(alerts))

    # Delivery
    notifiers = build_notifiers(cfg)
    dry_run = cfg["run"]["dry_run"]

    if not dry_run and alerts:
        io_mod.upsert_alerts_pg(cfg["io"]["postgres_url"], alerts)
        for a in alerts:
            for n in notifiers:
                try:
                    n.send(a)
                except Exception as ex:
                    LOGGER.error("Notifier failed: %s", ex)
    else:
        LOGGER.info("Dry-run or no alerts. Skipping DB write & delivery.")
        LOGGER.info("Preview alerts: %s", json.dumps(alerts, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
