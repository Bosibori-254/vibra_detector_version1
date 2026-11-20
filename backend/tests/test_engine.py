"""Tests for policy selection and default-ADVISORY rule evaluation."""

from __future__ import annotations

from conftest import diagnosis, feature_message

from pipeguard_backend.config import Config
from pipeguard_backend.rules.engine import RuleEngine
from pipeguard_backend.schemas import ActionMode, Cause


def test_default_is_advisory(config: Config) -> None:
    """Without explicit opt-in the rule is advisory and emits no command."""
    engine = RuleEngine(config)
    decision = engine.evaluate(
        diagnosis(), feature_message(sequence=0), current_value=2950.0, message_age_s=0.1
    )
    assert decision.mode is ActionMode.ADVISORY
    assert decision.command is None
    assert any(gate.gate == "G1_mode" and not gate.allowed for gate in decision.gates)


def test_explicit_auto_produces_bounded_command(config: Config) -> None:
    """AUTO for the segment and cause produces a bounded setpoint command."""
    config.system.auto_segments = ["seg-12"]
    config.policies.policies[Cause.CAVITATION].auto_segments = ["seg-12"]
    engine = RuleEngine(config)
    decision = engine.evaluate(
        diagnosis(confidence=0.9),
        feature_message(sequence=0, velocity_rms_mm_s=12.0),
        current_value=2950.0,
        message_age_s=0.1,
    )
    assert decision.mode is ActionMode.AUTO
    assert decision.command is not None
    assert decision.command.value == 2830.0
    assert decision.allowed


def test_kill_switch_blocks_auto(config: Config) -> None:
    """The operator kill switch overrides an enabled AUTO policy."""
    config.system.auto_segments = ["seg-12"]
    config.policies.policies[Cause.CAVITATION].auto_segments = ["seg-12"]
    engine = RuleEngine(config)
    engine.set_kill_switch(True)
    decision = engine.evaluate(
        diagnosis(), feature_message(sequence=0), current_value=2950.0, message_age_s=0.1
    )
    assert decision.command is None
    assert any(gate.gate == "G0_kill_switch" and not gate.allowed for gate in decision.gates)


def test_leak_never_auto_actuates(config: Config) -> None:
    """Leak policies require human confirmation even with AUTO enabled."""
    config.system.auto_segments = ["seg-12"]
    for policy in config.policies.policies.values():
        policy.auto_segments = ["seg-12"]
    decision = RuleEngine(config).evaluate(
        diagnosis(cause=Cause.LEAK),
        feature_message(sequence=0),
        current_value=2950.0,
        message_age_s=0.1,
    )
    assert decision.command is None
    assert any(gate.gate == "G1_mode" and not gate.allowed for gate in decision.gates)


def test_sensor_fault_blocks_actuation(config: Config) -> None:
    """A sensor-fault diagnosis fails safe."""
    config.system.auto_segments = ["seg-12"]
    decision = RuleEngine(config).evaluate(
        diagnosis(cause=Cause.SENSOR_FAULT),
        feature_message(sequence=0, sampling_ok=False),
        current_value=2950.0,
        message_age_s=0.1,
    )
    assert decision.command is None
