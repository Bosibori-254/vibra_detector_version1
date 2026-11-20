"""Map diagnoses to bounded action policies, defaulting to ADVISORY."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from pipeguard_backend.config import Config, Policy
from pipeguard_backend.rules.safety import SafetyContext, SafetyGate
from pipeguard_backend.schemas import (
    ActionCommand,
    ActionMode,
    Diagnosis,
    FeatureMessage,
    GateResult,
)


@dataclass(frozen=True)
class Decision:
    """The outcome of applying a policy to a diagnosis."""

    diagnosis: Diagnosis
    mode: ActionMode
    recommendation: str
    gates: list[GateResult]
    command: ActionCommand | None = None

    @property
    def allowed(self) -> bool:
        """Whether all safety gates allowed actuation."""
        return bool(self.command) and all(gate.allowed for gate in self.gates)


class RuleEngine:
    """Evaluate YAML policies and hard safety gates."""

    def __init__(self, config: Config, clock: Any = time.time) -> None:
        """Initialize the safety gate and action history."""
        self.config = config
        self.safety = SafetyGate(config)
        self.clock = clock
        self.recent_actions: dict[str, list[float]] = {}
        self.kill_switch: bool = False

    def set_kill_switch(self, active: bool) -> None:
        """Engage or release the operator kill switch instantly."""
        self.kill_switch = active

    def mode_for(self, policy: Policy, segment: str) -> ActionMode:
        """Return AUTO only when explicitly enabled for the segment and cause."""
        enabled = (
            segment in set(self.config.system.auto_segments)
            and segment in set(policy.auto_segments)
        )
        return ActionMode.AUTO if enabled else ActionMode.ADVISORY

    def evaluate(
        self,
        diagnosis: Diagnosis,
        message: FeatureMessage,
        current_value: float,
        sensor_healthy: bool = True,
        message_age_s: float = 0.0,
        authorized: bool = True,
        operator: str = "system",
    ) -> Decision:
        """Produce a decision for one diagnosis."""
        policy = self.config.policies.policies.get(diagnosis.cause)
        if policy is None:
            return Decision(diagnosis, ActionMode.ADVISORY, "investigate anomaly", [])
        mode = self.mode_for(policy, diagnosis.segment)
        spec = policy.action
        recommendation = spec.description or f"Review {diagnosis.cause.value} advisory"

        target = spec.target or diagnosis.cause.value
        value = current_value
        if spec.type == "setpoint" and mode is ActionMode.AUTO:
            value = self._target_value(spec, current_value, diagnosis.confidence)

        context = SafetyContext(
            cause=diagnosis.cause,
            mode=mode,
            action_type=spec.type,
            target=target,
            value=value,
            current_value=current_value,
            min_value=spec.min,
            max_value=spec.max,
            max_step=spec.max_step,
            rate_limit_per_min=spec.rate_limit_per_min,
            cooldown_s=spec.cooldown_s,
            operating_state=message.operating_state,
            envelope=spec.operating_envelope,
            segment=diagnosis.segment,
            node_id=diagnosis.node_id,
            message_age_s=message_age_s,
            sensor_healthy=sensor_healthy and diagnosis.cause.value != "sensor_fault",
            global_kill_switch=self.kill_switch,
            segment_auto_enabled=diagnosis.segment in set(self.config.system.auto_segments),
            recent_action_times=list(self.recent_actions.get(target, [])),
            now=float(self.clock()),
            operator=operator,
            authorized=authorized,
        )
        gates = self.safety.evaluate(context)
        command: ActionCommand | None = None
        if spec.type == "setpoint" and all(gate.allowed for gate in gates):
            command = ActionCommand(
                cause=diagnosis.cause,
                mode=mode,
                action_type=spec.type,
                target=target,
                value=round(value, 4),
                previous_value=round(current_value, 4),
                segment=diagnosis.segment,
                node_id=diagnosis.node_id,
                reason=f"{diagnosis.cause.value} confidence={diagnosis.confidence:.2f}",
                gates=gates,
                verification_timeout_s=policy.verification.timeout_s,
                min_improvement_pct=policy.verification.min_improvement_pct,
                baseline_velocity_mm_s=message.features.velocity_rms_mm_s,
                protocol=spec.protocol,
            )
        else:
            blocked = [g.reason for g in gates if not g.allowed]
            if blocked:
                recommendation = f"{recommendation} (blocked: {'; '.join(blocked)})"
        return Decision(diagnosis, mode, recommendation, gates, command)

    @staticmethod
    def _target_value(spec: Any, current: float, confidence: float) -> float:
        """Compute a bounded target from the configured direction and max step."""
        delta = float(min(spec.step_per_severity * confidence, spec.max_step))
        if spec.direction == "increase":
            return current + delta
        if spec.direction == "shift" and spec.skip_bands_hz:
            for low, high in spec.skip_bands_hz:
                if low <= current <= high:
                    return current + delta
        return current - delta

    def record_action(self, target: str) -> None:
        """Record that a command was issued for rate/cooldown checks."""
        self.recent_actions.setdefault(target, []).append(float(self.clock()))
