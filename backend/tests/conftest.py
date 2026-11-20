"""Shared fixtures and message helpers for backend tests."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
for package in ("simulator", "plc_sim"):
    sys.path.insert(0, str(ROOT / package / "src"))

from pipeguard_sim.dsp import FeatureConfig, Features, extract_features
from pipeguard_sim.messages import NodeHealth, make_feature_message, sign_message
from pipeguard_sim.signals import (
    FaultType,
    OperatingState,
    SignalParams,
    generate_signal,
)

from pipeguard_backend.config import Config, load_config
from pipeguard_backend.db.repository import Repository, create_database
from pipeguard_backend.schemas import (
    ActionAudit,
    ActionCommand,
    ActionMode,
    ActionResult,
    Cause,
    Diagnosis,
    FeatureMessage,
    GateResult,
    Severity,
)

KEY = "device-secret"


@pytest.fixture
def config() -> Config:
    """Return a fresh copy of the demo configuration."""
    return load_config()


@pytest.fixture
def repository() -> Iterator[Repository]:
    """Return a repository backed by an isolated in-memory database."""
    engine, factory = create_database("sqlite://")
    try:
        yield Repository(factory)
    finally:
        engine.dispose()


def signed_message(
    sequence: int = 0,
    *,
    fault: FaultType = FaultType.NORMAL,
    severity: float = 0.0,
    pressure_kpa: float = 3450.0,
    velocity_rms_mm_s: float | None = None,
    band_energies: dict[str, float] | None = None,
    sampling_ok: bool = True,
    drift_ppm: float = 3.1,
    key: str = KEY,
) -> dict[str, Any]:
    """Build one signed feature message, optionally overriding feature values."""
    signal = generate_signal(
        duration_s=0.5,
        sample_rate_hz=2000,
        operating_state=OperatingState(pressure_kpa=pressure_kpa),
        params=SignalParams(fault=fault, severity=severity, seed=42),
    )
    base = extract_features(signal.accel_mps2, FeatureConfig())
    features = base.as_dict()
    if velocity_rms_mm_s is not None:
        features["velocity_rms_mm_s"] = velocity_rms_mm_s
    if band_energies is not None:
        features["band_energies"] = {**features["band_energies"], **band_energies}
    typed_features = Features(
        sample_rate_hz=base.sample_rate_hz,
        window_seconds=base.window_seconds,
        accel_rms_mps2=features["accel_rms_mps2"],  # type: ignore[arg-type]
        velocity_rms_mm_s=features["velocity_rms_mm_s"],  # type: ignore[arg-type]
        peak_mps2=features["peak_mps2"],  # type: ignore[arg-type]
        crest_factor=features["crest_factor"],  # type: ignore[arg-type]
        kurtosis=features["kurtosis"],  # type: ignore[arg-type]
        band_energies=features["band_energies"],  # type: ignore[arg-type]
        fft_peaks=base.fft_peaks,
    )
    payload = make_feature_message(
        site="gulf-north",
        segment="seg-12",
        node_id="node-03",
        sequence=sequence,
        features=typed_features,
        operating_state=OperatingState(pressure_kpa=pressure_kpa),
        timestamp="2026-01-01T00:00:00Z",
        health=NodeHealth(sampling_ok=sampling_ok, drift_ppm=drift_ppm),
        signing_key=key,
    )
    return sign_message(payload, key)


def feature_message(**kwargs: Any) -> FeatureMessage:
    """Validate a signed message into the backend schema."""
    return FeatureMessage.model_validate(signed_message(**kwargs))


def diagnosis(
    cause: Cause = Cause.CAVITATION,
    *,
    confidence: float = 0.85,
    severity: Severity = Severity.WARNING,
) -> Diagnosis:
    """Return a diagnosis object for rule/actuation tests."""
    return Diagnosis(
        node_id="node-03",
        segment="seg-12",
        site="gulf-north",
        timestamp="2026-01-01T00:00:00Z",
        cause=cause,
        confidence=confidence,
        severity=severity,
        recommended_action="test recommendation",
    )


def action_command(
    *,
    target: str = "vfd_speed_rpm",
    value: float = 2830.0,
    previous_value: float = 2950.0,
    protocol: str = "simulated",
    timeout_s: int = 0,
    min_improvement_pct: float = 0.0,
    baseline: float = 8.0,
) -> ActionCommand:
    """Return a bounded command object for actuation tests."""
    return ActionCommand(
        cause=Cause.CAVITATION,
        mode=ActionMode.AUTO,
        action_type="setpoint",
        target=target,
        value=value,
        previous_value=previous_value,
        segment="seg-12",
        node_id="node-03",
        reason="test command",
        gates=[GateResult(gate="test", allowed=True)],
        verification_timeout_s=timeout_s,
        min_improvement_pct=min_improvement_pct,
        baseline_velocity_mm_s=baseline,
        protocol=protocol,
    )


def audit(result: ActionResult = ActionResult.EXECUTED, **kwargs: Any) -> ActionAudit:
    """Return an audit record for repository/report tests."""
    return ActionAudit(
        action_id=kwargs.get("action_id", "action-1"),
        timestamp=kwargs.get("timestamp", "2026-01-01T00:00:00Z"),
        node_id="node-03",
        segment="seg-12",
        cause=kwargs.get("cause", Cause.CAVITATION),
        mode=kwargs.get("mode", ActionMode.AUTO),
        action_type="setpoint",
        target=kwargs.get("target", "vfd_speed_rpm"),
        before=2950.0,
        after=2830.0,
        result=result,
        reason=kwargs.get("reason", "test"),
    )
