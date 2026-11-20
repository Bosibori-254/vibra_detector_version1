"""Hard safety constraints enforced before any field device write."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeguard_backend.config import Config
from pipeguard_backend.schemas import ActionMode, Cause, GateResult, OperatingState


@dataclass
class SafetyContext:
    """Everything the safety gates need to evaluate one proposed command."""

    cause: Cause
    mode: ActionMode
    action_type: str
    target: str
    value: float
    current_value: float
    min_value: float
    max_value: float
    max_step: float
    rate_limit_per_min: int
    cooldown_s: int
    operating_state: OperatingState
    envelope: dict[str, list[float]] = field(default_factory=dict)
    segment: str = "seg-12"
    node_id: str = "node-03"
    message_age_s: float = 0.0
    sensor_healthy: bool = True
    global_kill_switch: bool = False
    segment_auto_enabled: bool = False
    recent_action_times: list[float] = field(default_factory=list)
    now: float = 0.0
    operator: str = "system"
    authorized: bool = True

    @property
    def is_setpoint(self) -> bool:
        """Whether this action writes a numeric setpoint."""
        return self.action_type == "setpoint"


class SafetyGate:
    """Evaluate all hard rules; a single denial blocks actuation."""

    def __init__(self, config: Config) -> None:
        """Store the configuration."""
        self.config = config

    def evaluate(self, context: SafetyContext) -> list[GateResult]:
        """Run gates G0..G6 in order and return every result."""
        return [
            self._g0_kill_switch(context),
            self._g1_mode(context),
            self._g2_input_validity(context),
            self._g3_envelope(context),
            self._g4_bounds(context),
            self._g5_step_rate_cooldown(context),
            self._g6_authorization(context),
        ]

    @staticmethod
    def allowed(gate: str) -> GateResult:
        """Return an allowing gate result."""
        return GateResult(gate=gate, allowed=True)

    @staticmethod
    def denied(gate: str, reason: str) -> GateResult:
        """Return a denying gate result with a reason."""
        return GateResult(gate=gate, allowed=False, reason=reason)

    def _g0_kill_switch(self, ctx: SafetyContext) -> GateResult:
        """G0: global or segment kill switch disables all automation."""
        if ctx.global_kill_switch or self.config.system.global_kill_switch:
            return self.denied("G0_kill_switch", "automation kill switch is active")
        return self.allowed("G0_kill_switch")

    def _g1_mode(self, ctx: SafetyContext) -> GateResult:
        """G1: AUTO must be explicitly enabled for this segment and cause."""
        if ctx.mode is not ActionMode.AUTO:
            return self.denied("G1_mode", "rule is in ADVISORY mode; recommendation only")
        if not ctx.segment_auto_enabled:
            return self.denied("G1_mode", f"AUTO not enabled for segment {ctx.segment}")
        if ctx.action_type in {"recommend_isolation", "work_order", "none"}:
            return self.denied("G1_mode", "human confirmation required; never automatic")
        if ctx.cause is Cause.LEAK:
            return self.denied("G1_mode", "leak isolation requires human confirmation")
        return self.allowed("G1_mode")

    def _g2_input_validity(self, ctx: SafetyContext) -> GateResult:
        """G2: telemetry must be fresh and sensors healthy."""
        if ctx.message_age_s > self.config.system.max_message_age_s:
            return self.denied("G2_input_validity", "telemetry is stale")
        if not ctx.sensor_healthy:
            return self.denied("G2_input_validity", "sensor fault active; fail-safe")
        return self.allowed("G2_input_validity")

    def _g3_envelope(self, ctx: SafetyContext) -> GateResult:
        """G3: process conditions must be inside the operating envelope."""
        values = ctx.operating_state.model_dump()
        for name, bounds in ctx.envelope.items():
            if name not in values or len(bounds) != 2:
                continue
            observed = float(values[name])
            if observed < bounds[0] or observed > bounds[1]:
                return self.denied("G3_envelope", f"{name}={observed} outside [{bounds[0]}, {bounds[1]}]")
        return self.allowed("G3_envelope")

    def _g4_bounds(self, ctx: SafetyContext) -> GateResult:
        """G4: hard min/max bounds on the target setpoint."""
        if not ctx.is_setpoint:
            return self.allowed("G4_bounds")
        if ctx.value < ctx.min_value or ctx.value > ctx.max_value:
            return self.denied(
                "G4_bounds", f"target {ctx.value} outside [{ctx.min_value}, {ctx.max_value}]"
            )
        if any(denied in ctx.target.lower() for denied in self.config.policies.deny_tags):
            return self.denied("G4_bounds", "target is in SIS/ESD deny-list")
        return self.allowed("G4_bounds")

    def _g5_step_rate_cooldown(self, ctx: SafetyContext) -> GateResult:
        """G5: max step size, rate limit and cooldown between commands."""
        if not ctx.is_setpoint:
            return self.allowed("G5_step_rate_cooldown")
        if abs(ctx.value - ctx.current_value) > ctx.max_step + 1e-9:
            return self.denied(
                "G5_step_rate_cooldown",
                f"step {abs(ctx.value - ctx.current_value):.2f} exceeds {ctx.max_step}",
            )
        window = [t for t in ctx.recent_action_times if ctx.now - t <= 60.0]
        if len(window) >= ctx.rate_limit_per_min:
            return self.denied("G5_step_rate_cooldown", "rate limit exceeded")
        if window and ctx.now - max(window) < ctx.cooldown_s:
            return self.denied("G5_step_rate_cooldown", "cooldown active")
        return self.allowed("G5_step_rate_cooldown")

    def _g6_authorization(self, ctx: SafetyContext) -> GateResult:
        """G6: authorization and immutable audit readiness."""
        if not ctx.authorized:
            return self.denied("G6_authorization", "operator is not authorized")
        if any(denied in ctx.target.lower() for denied in self.config.policies.deny_tags):
            return self.denied("G6_authorization", "SIS/ESD targets are never writable")
        return self.allowed("G6_authorization")
