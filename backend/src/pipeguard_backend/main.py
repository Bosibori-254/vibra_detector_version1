"""Backend entry point: API server, MQTT bridge and evaluation utility."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import uvicorn

from pipeguard_backend.api.app import create_app
from pipeguard_backend.config import load_config
from pipeguard_backend.diagnosis.evaluation import evaluate
from pipeguard_backend.ingest.service import MqttBridge
from pipeguard_backend.pipeline import Pipeline


def main() -> None:
    """Run the backend or the offline diagnosis evaluation."""
    parser = argparse.ArgumentParser(description="PipeGuard backend")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mqtt", action="store_true")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()

    config = load_config()
    if args.evaluate:
        report = evaluate(Path("docs/reports"), config)
        print(f"diagnosis accuracy: {report['accuracy']:.1%} over {report['cases']} cases")
        return

    pipeline = Pipeline(config)
    app = create_app(pipeline.services())
    app.state.pipeline = pipeline

    if args.mqtt or os.getenv("PIPEGUARD_MQTT") == "1":
        bridge = MqttBridge(pipeline.ingest, broker=args.broker)

        @app.on_event("startup")
        async def start_bridge() -> None:
            """Connect to MQTT and consume messages in the background."""
            bridge.start()
            asyncio.create_task(bridge.run())

        @app.on_event("shutdown")
        async def stop_bridge() -> None:
            """Disconnect the MQTT bridge."""
            bridge.stop()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
