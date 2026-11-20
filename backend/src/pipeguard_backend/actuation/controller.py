"""Actuation state machine: command, verify effect, roll back and escalate."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from pipeguard_backend.actuation.adapters import DeviceRegistry, WriteOutcome
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.rules.engine import Decision
from pipeguard_backend.schemas import ActionAudit, ActionCommand, ActionResult


def _now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ActuationController:
    """Execute bounded commands and verify their effect asynchronously."""

    def __init__(
        self,
        repository: Repository,
        registry: DeviceRegistry,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        get_velocity: Callable[[str], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Store dependencies and callbacks."""
        self.repository = repository
        self.registry = registry
        self.on_event = on_event
        self.get_velocity = get_velocity or (lambda node_id: 0.0)
        self.sleep = sleep
        self.pending: dict[str, tuple[ActionCommand, ActionAudit]] = {}

    async def _emit(self, event: dict[str, Any]) -> None:
        """Publish an event if a callback is configured."""
        if self.on_event is not None:
            await self.on_event(event)

    async def execute(self, decision: Decision) -> ActionAudit:
        """Execute an allowed command or record a recommendation."""
        diagnosis = decision.diagnosis
        command = decision.command
        if command is None:
            audit = ActionAudit(
                action_id=str(uuid.uuid4()),
                timestamp=_now(),
                node_id=diagnosis.node_id,
                segment=diagnosis.segment,
                cause=diagnosis.cause,
                mode=decision.mode,
                action_type="recommendation",
                target="",
                before=None,
                after=None,
                result=ActionResult.RECOMMENDED,
                reason=decision.recommendation,
                gate_results=decision.gates,
            )
            self.repository.insert_action(audit)
            await self._emit({"type": "action", "audit": audit.model_dump(mode="json")})
            return audit

        adapter = self.registry.get(command.protocol)
        before = await adapter.read(command.target)
        try:
            outcome: WriteOutcome = await adapter.write(command.target, command.value)
        except (RuntimeError, OSError, ValueError) as exc:
            audit = self._audit(command, before, before, ActionResult.FAILED, f"communication loss: {exc}")
            self.repository.insert_action(audit)
            await self._emit({"type": "action", "audit": audit.model_dump(mode="json"),
                              "alarm": "actuation_failed"})
            return audit

        after = await adapter.read(command.target)
        audit = self._audit(
            command,
            outcome.before,
            after,
            ActionResult.EXECUTED if outcome.accepted else ActionResult.FAILED,
            outcome.reason or command.reason,
        )
        self.repository.insert_action(audit)
        await self._emit({"type": "action", "audit": audit.model_dump(mode="json")})
        if outcome.accepted and command.verification_timeout_s > 0:
            self.pending[audit.action_id] = (command, audit)
            asyncio.create_task(self.verify(audit.action_id))
        return audit

    async def verify(self, audit_id: str) -> None:
        """Verify vibration improvement; roll back and escalate on failure."""
        entry = self.pending.pop(audit_id, None)
        if entry is None:
            return
        command, original_audit = entry
        await self.sleep(command.verification_timeout_s)
        current = float(self.get_velocity(command.node_id))
        baseline = command.baseline_velocity_mm_s
        improvement = (
            (baseline - current) / baseline * 100.0 if baseline > 1e-6 else 0.0
        )
        if improvement >= command.min_improvement_pct:
            audit = self._audit(
                command, original_audit.before, original_audit.after, ActionResult.VERIFIED,
                f"vibration improved {improvement:.1f}%",
            )
            self.repository.insert_action(audit)
            await self._emit({"type": "action", "audit": audit.model_dump(mode="json")})
            return
        adapter = self.registry.get(command.protocol)
        try:
            await adapter.write(command.target, command.previous_value)
            restored = await adapter.read(command.target)
            result = ActionResult.ROLLED_BACK
            reason = f"no improvement ({improvement:.1f}%); restored {restored}"
        except (RuntimeError, OSError, ValueError) as exc:  # pragma: no cover - fault path
            reason = f"rollback failed: {exc}"
            result = ActionResult.FAILED
        audit = self._audit(command, original_audit.before, restored if 'restored' in locals() else None,
                            result, reason, rollback_of=original_audit.action_id)
        self.repository.insert_action(audit)
        await self._emit({"type": "action", "audit": audit.model_dump(mode="json"),
                          "alarm": "actuation_rollback", "escalate": True})

    @staticmethod
    def _audit(
        command: ActionCommand,
        before: float | None,
        after: float | None,
        result: ActionResult,
        reason: str,
        rollback_of: str | None = None,
    ) -> ActionAudit:
        """Build an audit record."""
        return ActionAudit(
            action_id=str(uuid.uuid4()),
            timestamp=_now(),
            node_id=command.node_id,
            segment=command.segment,
            cause=command.cause,
            mode=command.mode,
            action_type=command.action_type,
            target=command.target,
            before=before,
            after=after,
            result=result,
            reason=reason,
            gate_results=command.gates,
            rollback_of=rollback_of,
        )
