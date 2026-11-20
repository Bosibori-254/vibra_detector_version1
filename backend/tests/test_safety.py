"""Safety-gate tests: every hard rule must deny independently."""

from __future__ import annotations

from pipeguard_backend.config import Config
from pipeguard_backend.rules.safety import SafetyContext, SafetyGate
from pipeguard_backend.schemas import ActionMode, Cause, GateResult, OperatingState


def context(config: Config, **overrides: object) -> SafetyContext:
    """Return a fully-allowed baseline safety context with optional overrides."""
    values: dict[str, object] = {
        "cause": Cause.CAVITATION,
        "mode": ActionMode.AUTO,
        "action_type": "setpoint",
        "target": "vfd_speed_rpm",
        "value": 2830.0,
        "current_value": 2950.0,
        "min_value": 1200.0,
        "max_value": 3600.0,
        "max_step": 120.0,
        "rate_limit_per_min": 2,
        "cooldown_s": 45,
        "operating_state": OperatingState(),
        "envelope": {"pressure_kpa": [1800.0, 4200.0]},
        "segment": "seg-12",
        "node_id": "node-03",
        "message_age_s": 0.1,
        "sensor_healthy": True,
        "global_kill_switch": False,
        "segment_auto_enabled": True,
        "recent_action_times": [],
        "now": 100.0,
        "operator": "operator",
        "authorized": True,
    }
    values.update(overrides)
    return SafetyContext(**values)  # type: ignore[arg-type]


def denied(results: list[GateResult], gate: str) -> bool:
    """Whether a particular gate denied the command."""
    return any(result.gate == gate and not result.allowed for result in results)


def test_all_gates_allow_baseline_command(config: Config) -> None:
    """A bounded, fresh, authorized command passes every gate."""
    results = SafetyGate(config).evaluate(context(config))
    assert len(results) == 7
    assert all(result.allowed for result in results)


def test_global_kill_switch_denies(config: Config) -> None:
    """The global kill switch blocks all automation."""
    results = SafetyGate(config).evaluate(context(config, global_kill_switch=True))
    assert denied(results, "G0_kill_switch")


def test_configured_kill_switch_denies(config: Config) -> None:
    """A kill switch set in config also blocks all automation."""
    config.system.global_kill_switch = True
    results = SafetyGate(config).evaluate(context(config))
    assert denied(results, "G0_kill_switch")


def test_advisory_mode_denies(config: Config) -> None:
    """ADVISORY is recommendation-only."""
    results = SafetyGate(config).evaluate(context(config, mode=ActionMode.ADVISORY))
    assert denied(results, "G1_mode")


def test_segment_auto_opt_in_denies(config: Config) -> None:
    """AUTO must be explicitly enabled for the segment."""
    results = SafetyGate(config).evaluate(context(config, segment_auto_enabled=False))
    assert denied(results, "G1_mode")


def test_leak_and_human_actions_denied(config: Config) -> None:
    """Leaks and work orders never actuate automatically."""
    leak = SafetyGate(config).evaluate(context(config, cause=Cause.LEAK))
    assert denied(leak, "G1_mode")
    work_order = SafetyGate(config).evaluate(context(config, action_type="work_order"))
    assert denied(work_order, "G1_mode")


def test_stale_telemetry_denies(config: Config) -> None:
    """Stale telemetry fails the input-validity gate."""
    results = SafetyGate(config).evaluate(context(config, message_age_s=99.0))
    assert denied(results, "G2_input_validity")


def test_unhealthy_sensor_denies(config: Config) -> None:
    """A sensor fault fails safe."""
    results = SafetyGate(config).evaluate(context(config, sensor_healthy=False))
    assert denied(results, "G2_input_validity")


def test_operating_envelope_denies(config: Config) -> None:
    """Out-of-envelope process conditions block actuation."""
    results = SafetyGate(config).evaluate(
        context(config, operating_state=OperatingState(pressure_kpa=1000.0))
    )
    assert denied(results, "G3_envelope")


def test_hard_bounds_denies(config: Config) -> None:
    """Setpoints outside configured min/max are blocked."""
    results = SafetyGate(config).evaluate(context(config, value=100.0))
    assert denied(results, "G4_bounds")


def test_sis_esd_targets_always_denied(config: Config) -> None:
    """SIS/ESD targets are denied by bounds and authorization gates."""
    results = SafetyGate(config).evaluate(context(config, target="sis_emergency_shutdown"))
    assert denied(results, "G4_bounds")
    assert denied(results, "G6_authorization")


def test_step_rate_and_cooldown_denies(config: Config) -> None:
    """Step size, rate limit and cooldown are independently enforced."""
    gate = SafetyGate(config)
    assert denied(gate.evaluate(context(config, value=2500.0)), "G5_step_rate_cooldown")
    assert denied(
        gate.evaluate(context(config, recent_action_times=[99.0, 99.5])),
        "G5_step_rate_cooldown",
    )
    assert denied(
        gate.evaluate(context(config, recent_action_times=[99.5])),
        "G5_step_rate_cooldown",
    )


def test_authorization_denies(config: Config) -> None:
    """Unauthorized operators cannot actuate."""
    results = SafetyGate(config).evaluate(context(config, authorized=False))
    assert denied(results, "G6_authorization")
