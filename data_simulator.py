from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

from simulator import Simulator
from metrics import Metrics
from utils import positive_float, load_data


def build_parser() -> argparse.ArgumentParser:
    """
    Build the CLI parser for the simulator.
    """
    p = argparse.ArgumentParser(description="Replay telemetry at a fixed QPS to MQTT/Kafka (Dummy drivers)")
    p.add_argument("--qps", type=positive_float, help="Messages per second to send (>0)")
    p.add_argument("--duration", type=positive_float, help="Total run time in seconds (>0)")
    p.add_argument("--out", choices=["mqtt", "kafka", "both"], default="both",
                   help="Where to publish messages (default: both)")
    p.add_argument("--file", required=True, help="Path to .csv or .parquet file with telemetry data")

    p.add_argument("--mqtt-host", default="localhost", help="MQTT broker hostname (default: localhost)")
    p.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    p.add_argument("--mqtt-topic", default="telemetry", help="MQTT topic (default: telemetry)")

    p.add_argument("--kafka-bootstrap", default="localhost:9092",
                   help="Kafka bootstrap servers (default: localhost:9092)")
    p.add_argument("--kafka-topic", default="telemetry",
                   help="Kafka topic (default: telemetry)")

    p.add_argument("--window-sec", type=positive_float, default=5.0,
                   help="Rolling window (seconds) for instantaneous QPS (default: 5)")
    p.add_argument("--status-every", type=positive_float, default=1.0,
                   help="Print status every N seconds (default: 1)")

    p.add_argument("--loop", action="store_true",
                   help="Loop over the sample data until duration elapses")
    p.add_argument("--stability", action="store_true",
                   help="Shortcut: run 60s at 1k msgs/s and report KPI PASS/FAIL")
    p.add_argument("--perf", action="store_true",
                   help="Shortcut: run 15m at 10k msgs/s, Kafka recommended; report KPI PASS/FAIL")
    return p


def _apply_shortcuts(args: argparse.Namespace) -> None:
    """
    Apply --stability/--perf shortcuts by overriding qps/duration/out/loop defaults.
    """
    if args.stability:
        args.qps = 1000.0
        args.duration = 60.0
        # keep args.out as the user passed; default is 'both'
        if not args.loop:
            args.loop = True

    if args.perf:
        args.qps = 10000.0
        args.duration = 15 * 60.0
        if not args.loop:
            args.loop = True


def _kpi_verdict(args: argparse.Namespace, metrics: Metrics) -> Optional[bool]:
    """
    Return KPI PASS/FAIL if in test mode; None otherwise.
    KPI: loss_rate <= 0.5% for all selected transports.
    """
    if not (args.stability or args.perf):
        return None

    loss = metrics.loss_rates()
    targets = []
    if args.out in ("kafka", "both"):
        targets.append(loss["kafka_loss_pct"])
    if args.out in ("mqtt", "both"):
        targets.append(loss["mqtt_loss_pct"])

    ok = all(l <= 0.5 for l in targets)
    print("  KPI verdict:", "PASS" if ok else "FAIL (loss > 0.5%)")
    return ok


def main() -> None:
    """
    Entry point: parse args, apply profiles, run simulator, print KPI verdict when relevant.
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.stability and args.perf:
        parser.error("Choose only one profile: --stability OR --perf")

    # Require qps/duration unless a profile provides them.
    if not (args.stability or args.perf):
        if args.qps is None or args.duration is None:
            parser.error("--qps and --duration are required unless --stability or --perf is set")

    _apply_shortcuts(args)

    if args.out is None:
        args.out = "kafka" if args.perf else "both"

    print(f"[config] qps={args.qps} duration={args.duration}s out={args.out} loop={bool(args.loop)}")

    df = load_data(Path(args.file))
    print(f"[info] Loaded {len(df)} records from {args.file}")

    sim = Simulator(args, df)
    sim.run()

    verdict = _kpi_verdict(args, sim.metrics)

    # Exit non-zero on KPI fail when in a profile mode (useful for CI).
    if verdict is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
