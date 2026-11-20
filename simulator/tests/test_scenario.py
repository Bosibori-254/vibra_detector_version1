"""Unit tests for message builders and the scenario runner."""

from __future__ import annotations

import json

import pytest

from pipeguard_sim.dsp import FeatureConfig, extract_features
from pipeguard_sim.messages import (
    canonical_json,
    make_feature_message,
    make_raw_message,
    make_status_message,
    sign_message,
    verify_signature,
)
from pipeguard_sim.scenario import (
    FaultWindow,
    PipelineSimulator,
    SimulatorConfig,
    build_schedule,
)
from pipeguard_sim.signals import FaultType, OperatingState, generate_signal

KEY = "device-secret"


def sample_message() -> dict[str, object]:
    """Return a minimal signed feature message."""
    signal = generate_signal(0.5, 2000, OperatingState())
    features = extract_features(signal.accel_mps2, FeatureConfig())
    return make_feature_message(
        site="gulf-north",
        segment="seg-12",
        node_id="node-03",
        sequence=5,
        features=features,
        operating_state=OperatingState(),
        signing_key=KEY,
    )


def test_signature_roundtrip_and_tamper_detection() -> None:
    message = sample_message()
    assert verify_signature(message, KEY)
    tampered = json.loads(json.dumps(message))
    tampered["sequence"] = 99
    assert not verify_signature(tampered, KEY)
    assert not verify_signature(tampered, "wrong-key")


def test_canonical_json_is_key_sorted() -> None:
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == '{"a":{"c":3,"d":2},"b":1}'


def test_sign_message_preserves_payload() -> None:
    payload = {"x": 1, "y": "z"}
    signed = sign_message(payload, KEY)
    assert signed["x"] == 1
    assert str(signed["signature"]).startswith("hmac-sha256=")


def test_raw_and_status_messages_are_buildable() -> None:
    raw = make_raw_message(
        site="s", segment="g", node_id="n", sequence=1, t0="now",
        sample_rate_hz=2000, axis="z", samples=[1.0, 2.0], trigger_reason="test",
        signing_key=KEY,
    )
    status = make_status_message(site="s", segment="g", node_id="n", online=False, signing_key=KEY)
    assert verify_signature(raw, KEY)
    assert verify_signature(status, KEY)
    assert status["online"] is False


def test_scenario_steps_increment_and_switch_fault() -> None:
    config = SimulatorConfig(
        duration_s=8.0,
        window_seconds=0.5,
        schedule=(FaultWindow(0.0), FaultWindow(4.0, FaultType.CAVITATION, 0.7)),
        signing_key=KEY,
    )
    simulator = PipelineSimulator(config)
    steps = simulator.run()
    assert len(steps) == 16
    assert [step.message["sequence"] for step in steps] == list(range(16))
    assert all(step.fault is FaultType.NORMAL for step in steps[:8])
    assert all(step.fault is FaultType.CAVITATION for step in steps[8:])
    assert verify_signature(steps[-1].message, KEY)


def test_unknown_scenario_raises() -> None:
    with pytest.raises(ValueError):
        build_schedule("not-a-scenario")


def test_raw_message_from_step_uses_z_axis() -> None:
    simulator = PipelineSimulator(SimulatorConfig(duration_s=0.5, signing_key=KEY))
    step = simulator.step()
    raw = simulator.raw_message(step, "anomaly")
    assert raw["axis"] == "z"
    assert len(raw["samples_mg"]) == 1000  # type: ignore[arg-type]
