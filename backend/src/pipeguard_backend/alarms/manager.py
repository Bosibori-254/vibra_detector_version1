"""Alarm creation, acknowledgement, shelving, clearing and escalation."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.schemas import (
    AlarmPriority,
    AlarmRecord,
    AlarmState,
    Cause,
    Diagnosis,
    Severity,
)


def _now() -> str:
    """Return a UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class AlarmManager:
    """Manage alarm state transitions and escalation timers."""

    def __init__(
        self,
        repository: Repository,
        config: Config,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        """Store dependencies."""
        self.repository = repository
        self.config = config
        self.on_event = on_event
        self.alarms: dict[str, AlarmRecord] = {}

    @staticmethod
    def priority_for(severity: Severity, cause: Cause) -> AlarmPriority:
        """Map diagnosis severity to alarm priority."""
        if cause is Cause.LEAK or severity is Severity.CRITICAL:
            return AlarmPriority.CRITICAL
        if severity is Severity.WARNING:
            return AlarmPriority.WARNING
        return AlarmPriority.ADVISORY

    async def _emit(self, alarm: AlarmRecord, verb: str) -> None:
        """Emit an alarm event."""
        if self.on_event is not None:
            await self.on_event(
                {"type": "alarm", "verb": verb, "alarm": alarm.model_dump(mode="json")}
            )

    async def raise_alarm(self, diagnosis: Diagnosis) -> AlarmRecord:
        """Create or refresh an alarm for a diagnosis."""
        alarm_id = f"{diagnosis.segment}:{diagnosis.node_id}:{diagnosis.cause.value}"
        existing = self.alarms.get(alarm_id)
        now = _now()
        priority = self.priority_for(diagnosis.severity, diagnosis.cause)
        if existing and existing.state in {AlarmState.ACTIVE, AlarmState.ACKED}:
            existing.priority = priority
            existing.message = f"{diagnosis.cause.value}: {diagnosis.recommended_action}"
            existing.updated_at = now
            alarm = existing
        else:
            alarm = AlarmRecord(
                alarm_id=alarm_id or str(uuid.uuid4()),
                node_id=diagnosis.node_id,
                segment=diagnosis.segment,
                site=diagnosis.site,
                priority=priority,
                state=AlarmState.ACTIVE,
                cause=diagnosis.cause,
                message=f"{diagnosis.cause.value}: {diagnosis.recommended_action}",
                created_at=now,
                updated_at=now,
            )
            self.alarms[alarm_id] = alarm
        self.repository.upsert_alarm(alarm)
        await self._emit(alarm, "raised")
        return alarm

    async def acknowledge(self, alarm_id: str, operator: str) -> AlarmRecord | None:
        """Acknowledge an active alarm."""
        alarm = self.alarms.get(alarm_id) or self.repository.get_alarm(alarm_id)
        if alarm is None:
            return None
        alarm.state = AlarmState.ACKED
        alarm.acked_by = operator
        alarm.acked_at = _now()
        alarm.updated_at = alarm.acked_at
        self.repository.upsert_alarm(alarm)
        await self._emit(alarm, "acknowledged")
        return alarm

    async def shelve(self, alarm_id: str, seconds: int = 300) -> AlarmRecord | None:
        """Shelve an alarm for a limited time."""
        alarm = self.alarms.get(alarm_id) or self.repository.get_alarm(alarm_id)
        if alarm is None:
            return None
        alarm.state = AlarmState.SHELVED
        alarm.shelved_until = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        alarm.updated_at = _now()
        self.repository.upsert_alarm(alarm)
        await self._emit(alarm, "shelved")
        return alarm

    async def clear(self, alarm_id: str) -> AlarmRecord | None:
        """Clear an alarm when the condition has returned to normal."""
        alarm = self.alarms.get(alarm_id) or self.repository.get_alarm(alarm_id)
        if alarm is None:
            return None
        alarm.state = AlarmState.CLEARED
        alarm.cleared_at = _now()
        alarm.updated_at = alarm.cleared_at
        self.repository.upsert_alarm(alarm)
        await self._emit(alarm, "cleared")
        return alarm

    async def escalate(self, alarm_id: str, reason: str = "unacknowledged") -> AlarmRecord | None:
        """Escalate an alarm and re-notify operators."""
        alarm = self.alarms.get(alarm_id) or self.repository.get_alarm(alarm_id)
        if alarm is None:
            return None
        alarm.escalation_count += 1
        alarm.updated_at = _now()
        self.repository.upsert_alarm(alarm)
        await self._emit(alarm, "escalated")
        return alarm

    async def tick(self) -> None:
        """Check escalation timers for unacknowledged alarms."""
        unack = float(self.config.notifications.escalation.get("unack_seconds", 60))
        max_repeats = int(self.config.notifications.escalation.get("max_repeats", 3))
        now = datetime.now(timezone.utc)
        for alarm in list(self.alarms.values()):
            if alarm.state is not AlarmState.ACTIVE:
                continue
            created = datetime.fromisoformat(alarm.created_at.replace("Z", "+00:00"))
            elapsed = (now - created).total_seconds()
            if elapsed >= unack * (alarm.escalation_count + 1) and alarm.escalation_count < max_repeats:
                await self.escalate(alarm.alarm_id, "unacknowledged timer")

    async def run_escalation_loop(self) -> None:
        """Periodically run escalation checks."""
        while True:
            await asyncio.sleep(5.0)
            await self.tick()
