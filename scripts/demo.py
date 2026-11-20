#!/usr/bin/env python3
"""End-to-end PipeGuard demo: normal -> cavitation -> advisory -> AUTO -> recovery.

Runs fully in-process (simulator + backend + simulated PLC), so it needs no
hardware and no Docker. Docker Compose is used for the full-stack demo.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for package in ("simulator", "backend", "plc_sim"):
    sys.path.insert(0, str(ROOT / package / "src"))

from pipeguard_backend.actuation.adapters import DeviceRegistry, SimulatedAdapter
from pipeguard_backend.config import load_config
from pipeguard_backend.db.repository import Repository, create_database
from pipeguard_backend.pipeline import Pipeline
from pipeguard_backend.schemas import Cause, Severity
from pipeguard_sim.messages import sign_message
from pipeguard_sim.scenario import FaultWindow, PipelineSimulator, SimulatorConfig
from pipeguard_sim.signals import FaultType
from plc_sim.device import SimulatedPLC


async def run() -> int:
    """Execute the scenario; return 0 on success."""
    config = load_config()
    policy = config.policies.policies[Cause.CAVITATION]
    policy.verification.timeout_s = 2
    policy.verification.min_improvement_pct = 8.0
    config.system.auto_segments = []
    policy.auto_segments = []
    # The in-process demo has no OPC UA server; use the simulated device adapter.
    policy.action.protocol = "simulated"

    plc = SimulatedPLC()
    adapter = SimulatedAdapter(plc)
    engine, factory = create_database("sqlite://")
    repository = Repository(factory)
    pipeline = Pipeline(
        config,
        repository=repository,
        registry=DeviceRegistry(simulated=adapter),
        report_dir=ROOT / "docs" / "reports" / "incidents",
    )
    key = config.system.device_keys["node-03"]
    simulator = PipelineSimulator(
        SimulatorConfig(
            duration_s=22.0,
            window_seconds=0.5,
            schedule=(FaultWindow(0.0), FaultWindow(4.0, FaultType.CAVITATION, 0.85)),
            signing_key=key,
        )
    )

    print("PHASE 1: normal operation")
    fault_announced = False
    advisory_count = 0
    auto_enabled = False
    action_executed = False
    action_latency_ms = 0.0
    cavitation_index = 1.0
    latest_features: dict[str, Any] = {}

    for step in simulator.run():
        if step.fault is FaultType.CAVITATION and not fault_announced:
            fault_announced = True
            plc.set_fault("cavitation", 0.85)
            cavitation_index = plc.vibration_index()
            print(f"PHASE 2: cavitation injected (vibration index {cavitation_index:.3f})")

        # Mirror the simulated PLC response into the telemetry amplitudes so the
        # backend can verify that its bounded action improved the vibration.
        factor = (
            plc.vibration_index() / cavitation_index
            if fault_announced and cavitation_index > 0
            else 1.0
        )
        message = dict(step.message)
        features = dict(message["features"])
        features["accel_rms_mps2"] = {
            axis: value * factor
            for axis, value in dict(features["accel_rms_mps2"]).items()
        }
        features["velocity_rms_mm_s"] = float(features["velocity_rms_mm_s"]) * factor
        features["peak_mps2"] = float(features["peak_mps2"]) * factor
        features["fft_peaks"] = [
            {**peak, "amplitude_mps2": peak["amplitude_mps2"] * factor}
            for peak in features["fft_peaks"]
        ]
        message["features"] = features
        message = sign_message(message, key)
        latest_features = features

        started = time.perf_counter()
        result = await pipeline.handle_message(
            "pipeguard/gulf-north/seg-12/node-03/features",
            json.dumps(message).encode("utf-8"),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not result or result.get("type") != "diagnosis":
            continue
        diagnosis = result["diagnosis"]
        if diagnosis["cause"] != Cause.CAVITATION.value:
            continue
        audit = result["action"]
        print(
            f"  t+{step.message['timestamp']}: {diagnosis['cause']} "
            f"(confidence {diagnosis['confidence']:.2f}), mode={result['decision_mode']}, "
            f"action={audit['result']}, latency={elapsed_ms:.1f} ms"
        )
        if result["decision_mode"] == "advisory":
            advisory_count += 1
            if advisory_count == 2 and not auto_enabled:
                auto_enabled = True
                config.system.auto_segments = ["seg-12"]
                policy.auto_segments = ["seg-12"]
                print("PHASE 3: AUTO explicitly enabled for seg-12 / cavitation")
        if audit["result"] == "executed" and not action_executed:
            action_executed = True
            action_latency_ms = elapsed_ms
            print(
                f"PHASE 4: VFD {audit['before']:.0f} -> {audit['after']:.0f} rpm "
                "(bounded, audited)"
            )
            print("PHASE 5: verifying effect and waiting for recovery")

    await asyncio.sleep(policy.verification.timeout_s + 1.0)
    actions = [a.result.value for a in repository.list_actions()]
    print(f"  action outcomes: {actions}")
    report = pipeline.reporter.generate(
        config.system.site,
        config.system.segment,
        Cause.CAVITATION,
        Severity.WARNING,
        spectrum_snapshot=latest_features,
    )
    report_path = ROOT / "docs" / "reports" / "incidents" / f"incident-{report.incident_id[:8]}.md"
    print(f"PHASE 6: incident report {report_path.name} — outcome: {report.outcome}")
    print(f"Detection-to-action latency: {action_latency_ms:.1f} ms (target < 2000 ms)")
    engine.dispose()
    return 0 if action_executed and action_latency_ms < 2000 else 1


def main() -> None:
    """Run the demo."""
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
