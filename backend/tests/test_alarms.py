"""Tests for the alarm lifecycle and escalation."""

from __future__ import annotations

from typing import Any

from conftest import diagnosis

from pipeguard_backend.alarms.manager import AlarmManager
from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.schemas import AlarmPriority, AlarmState, Cause, Severity


async def _emit(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    """Capture an alarm event."""
    events.append(event)


async def test_alarm_lifecycle(repository: Repository, config: Config) -> None:
    """Alarms move through raised, acknowledged and cleared states."""
    events: list[dict[str, Any]] = []
    manager = AlarmManager(repository, config, on_event=lambda e: _emit(events, e))
    alarm = await manager.raise_alarm(diagnosis())
    assert alarm.state is AlarmState.ACTIVE
    assert alarm.priority is AlarmPriority.WARNING
    assert repository.get_alarm(alarm.alarm_id) is not None

    acked = await manager.acknowledge(alarm.alarm_id, "operator")
    assert acked is not None and acked.state is AlarmState.ACKED
    assert acked.acked_by == "operator"

    cleared = await manager.clear(alarm.alarm_id)
    assert cleared is not None and cleared.state is AlarmState.CLEARED
    assert {event["verb"] for event in events} >= {"raised", "acknowledged", "cleared"}


async def test_leak_alarm_is_critical(repository: Repository, config: Config) -> None:
    """A leak alarm is always critical priority."""
    manager = AlarmManager(repository, config)
    alarm = await manager.raise_alarm(diagnosis(cause=Cause.LEAK, severity=Severity.WARNING))
    assert alarm.priority is AlarmPriority.CRITICAL


async def test_shelve_and_escalation(repository: Repository, config: Config) -> None:
    """Shelving and unacknowledged timers behave as configured."""
    manager = AlarmManager(repository, config)
    alarm = await manager.raise_alarm(diagnosis())
    shelved = await manager.shelve(alarm.alarm_id, seconds=300)
    assert shelved is not None and shelved.state is AlarmState.SHELVED

    alarm2 = await manager.raise_alarm(diagnosis(cause=Cause.RESONANCE))
    config.notifications.escalation["unack_seconds"] = 0
    config.notifications.escalation["max_repeats"] = 2
    await manager.tick()
    assert alarm2.escalation_count == 1
    await manager.tick()
    assert alarm2.escalation_count == 2
