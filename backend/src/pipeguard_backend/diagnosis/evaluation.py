"""Generate a confusion-matrix evaluation report on simulated fault data."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pipeguard_backend.config import Config, load_config
from pipeguard_backend.db.repository import Repository, create_database
from pipeguard_backend.detection.detector import Detector
from pipeguard_backend.diagnosis.classifier import DiagnosisEngine
from pipeguard_backend.ingest.service import IngestService
from pipeguard_backend.schemas import Cause, FeatureMessage, Severity

CAUSES = [
    Cause.NORMAL,
    Cause.CAVITATION,
    Cause.RESONANCE,
    Cause.WATER_HAMMER,
    Cause.LOOSE_SUPPORT,
    Cause.LEAK,
    Cause.IMBALANCE,
]


def _build_simulator(cause: Cause, config: Config) -> Any:
    """Create a simulator whose fault starts after a normal warm-up period."""
    from pipeguard_sim.scenario import (
        FaultWindow,
        PipelineSimulator,
        SimulatorConfig,
        build_schedule,
    )

    fault_map = {
        Cause.NORMAL: "normal",
        Cause.CAVITATION: "cavitation",
        Cause.RESONANCE: "resonance",
        Cause.WATER_HAMMER: "water_hammer",
        Cause.LOOSE_SUPPORT: "loose_support",
        Cause.LEAK: "leak",
        Cause.IMBALANCE: "imbalance",
    }
    schedule = build_schedule(fault_map[cause])
    if cause is not Cause.NORMAL:
        schedule = (
            FaultWindow(0.0),
            *[FaultWindow(w.start_s + 3.0, w.fault, w.severity) for w in schedule[1:]],
        )
    return PipelineSimulator(
        SimulatorConfig(
            duration_s=16.0,
            window_seconds=0.5,
            schedule=schedule,
            signing_key=config.system.device_keys["node-03"],
        )
    )


async def _run_cause(cause: Cause, config: Config) -> tuple[list[Cause], list[Cause]]:
    """Run one scenario and return (expected, predicted) cause lists."""
    engine, factory = create_database("sqlite://")
    repository = Repository(factory)
    ingest = IngestService(repository, config)
    detector = Detector(repository, config, clock=lambda: len(repository.recent_features("node-03")) * 0.5)
    classifier = DiagnosisEngine(config)
    simulator = _build_simulator(cause, config)

    expected: list[Cause] = []
    predicted: list[Cause] = []
    try:
        for step in simulator.run():
            message: FeatureMessage | None = await ingest.handle_topic(
                "pipeguard/gulf-north/seg-12/node-03/features",
                json.dumps(step.message).encode("utf-8"),
            )
            if message is None:
                continue
            detection = detector.evaluate(message)
            if detection.severity is not Severity.NORMAL:
                diagnosis = classifier.diagnose(
                    message,
                    detection,
                    list(repository.recent_features(message.node_id, 40)),
                    detector.baselines.get(message.node_id, detection.state_key),
                )
                if step.fault.value != "normal":
                    expected.append(Cause(step.fault.value))
                    predicted.append(diagnosis.cause)
        return expected, predicted
    finally:
        engine.dispose()


def evaluate(output_dir: Path, config: Config | None = None) -> dict[str, Any]:
    """Run all scenarios and write the evaluation report."""
    cfg = config or load_config()
    matrix: dict[str, dict[str, int]] = {
        expected.value: {actual.value: 0 for actual in CAUSES} for expected in CAUSES
    }
    for cause in CAUSES:
        expected, predicted = asyncio.run(_run_cause(cause, cfg))
        for truth, guess in zip(expected, predicted):
            matrix[truth.value][guess.value] = matrix[truth.value].get(guess.value, 0) + 1

    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[cause.value][cause.value] for cause in CAUSES)
    report = {
        "matrix": matrix,
        "cases": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "diagnosis-evaluation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    header = "| actual \\ predicted | " + " | ".join(c.value for c in CAUSES) + " |"
    lines = [
        "# Diagnosis evaluation (simulated data)",
        "",
        f"Cases: {total} — accuracy: {report['accuracy']:.1%}",
        "",
        header,
        "|" + "---|" * (len(CAUSES) + 1),
    ]
    for cause in CAUSES:
        row = matrix[cause.value]
        lines.append(f"| {cause.value} | " + " | ".join(str(row[c.value]) for c in CAUSES) + " |")
    (output_dir / "diagnosis-evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
