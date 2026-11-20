"""Command-line entry point for the PipeGuard simulator."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pipeguard_sim.messages import feature_topic
from pipeguard_sim.scenario import PipelineSimulator, SimulatorConfig, build_schedule

SCENARIOS = (
    "normal",
    "cavitation",
    "resonance",
    "water_hammer",
    "loose_support",
    "leak",
    "imbalance",
    "sensor_failure",
    "mixed",
    "all",
)


def _parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="PipeGuard vibration fault simulator")
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--duration", type=float, default=30.0, help="simulation seconds")
    parser.add_argument("--sample-rate", type=int, default=2000)
    parser.add_argument("--window", type=float, default=0.5)
    parser.add_argument("--site", default="gulf-north")
    parser.add_argument("--segment", default="seg-12")
    parser.add_argument("--node", default="node-03")
    parser.add_argument("--key", default="", help="HMAC signing key")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None, help="write JSONL here instead of stdout")
    parser.add_argument("--mqtt", action="store_true", help="publish to MQTT instead of stdout")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--pace", action="store_true", help="pace publishing at real time")
    return parser


def _publish_mqtt(config: SimulatorConfig, args: argparse.Namespace) -> None:
    """Publish the scenario to an MQTT broker."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("paho-mqtt is required for --mqtt (pip install paho-mqtt)") from exc

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{config.node_id}")
    if args.key:
        client.username_pw_set(config.node_id, args.key)
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()
    simulator = PipelineSimulator(config)
    client.publish(feature_topic(config.site, config.segment, config.node_id, "status"),
                   json.dumps(simulator.status_message(True)), qos=1, retain=True)
    try:
        while not simulator.finished:
            step = simulator.step()
            topic = feature_topic(config.site, config.segment, config.node_id)
            client.publish(topic, json.dumps(step.message), qos=1)
            if args.pace:
                time.sleep(config.window_seconds)
    finally:
        client.publish(feature_topic(config.site, config.segment, config.node_id, "status"),
                       json.dumps(simulator.status_message(False, "simulation_end")),
                       qos=1, retain=True)
        client.loop_stop()
        client.disconnect()


def main(argv: list[str] | None = None) -> int:
    """Run the simulator CLI; return a process exit code."""
    args = _parser().parse_args(argv)
    config = SimulatorConfig(
        site=args.site,
        segment=args.segment,
        node_id=args.node,
        sample_rate_hz=args.sample_rate,
        window_seconds=args.window,
        duration_s=args.duration,
        schedule=build_schedule(args.scenario),
        signing_key=args.key or None,
        seed=args.seed,
    )
    if args.mqtt:
        _publish_mqtt(config, args)
        return 0

    simulator = PipelineSimulator(config)
    stream = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
    try:
        while not simulator.finished:
            step = simulator.step()
            stream.write(json.dumps(step.message) + "\n")
        stream.flush()
    finally:
        if args.out:
            stream.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
