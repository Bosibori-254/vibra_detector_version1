"""End-to-end test of the in-process telemetry-to-actuation pipeline."""

from __future__ import annotations

import json

from pipeguard_sim.scenario import FaultWindow, PipelineSimulator, SimulatorConfig
from pipeguard_sim.signals import FaultType

from pipeguard_backend.actuation.adapters import DeviceRegistry
from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.pipeline import Pipeline
from pipeguard_backend.schemas import ActionResult, Cause


async def test_cavitation_triggers_bounded_auto_action(repository: Repository, config: Config) -> None:
    """Signed telemetry flows through detection, diagnosis and bounded actuation."""
    config.system.auto_segments = ["seg-12"]
    policy = config.policies.policies[Cause.CAVITATION]
    policy.auto_segments = ["seg-12"]
    policy.action.protocol = "simulated"
    policy.verification.timeout_s = 0

    pipeline = Pipeline(config, repository=repository, registry=DeviceRegistry())
    simulator = PipelineSimulator(
        SimulatorConfig(
            duration_s=10.0,
            window_seconds=0.5,
            schedule=(FaultWindow(0.0), FaultWindow(2.0, FaultType.CAVITATION, 0.9)),
            signing_key=config.system.device_keys["node-03"],
        )
    )
    results = []
    for step in simulator.run():
        results.append(
            await pipeline.handle_message(
                "pipeguard/gulf-north/seg-12/node-03/features",
                json.dumps(step.message).encode("utf-8"),
            )
        )

    diagnoses = [r for r in results if r and r.get("type") == "diagnosis"]
    assert any(d["diagnosis"]["cause"] == Cause.CAVITATION.value for d in diagnoses)
    actions = repository.list_actions()
    assert any(action.result is ActionResult.EXECUTED for action in actions)
    assert all(action.after is None or 1200 <= action.after <= 3600 for action in actions)
