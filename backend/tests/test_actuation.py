"""Tests for bounded actuation, verification and rollback."""

from __future__ import annotations

import asyncio
from typing import Any

from conftest import action_command, diagnosis
from plc_sim.device import SimulatedPLC

from pipeguard_backend.actuation.adapters import DeviceRegistry, SimulatedAdapter
from pipeguard_backend.actuation.controller import ActuationController
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.rules.engine import Decision
from pipeguard_backend.schemas import ActionMode, ActionResult, GateResult


def decision(command: Any) -> Decision:
    """Return an allowed decision containing the supplied command."""
    return Decision(
        diagnosis=diagnosis(),
        mode=ActionMode.AUTO,
        recommendation="",
        gates=[GateResult(gate="test", allowed=True)],
        command=command,
    )


async def test_execute_writes_bounded_value_and_audits(repository: Repository) -> None:
    """An allowed command writes the device and appends an audit record."""
    plc = SimulatedPLC()
    registry = DeviceRegistry(simulated=SimulatedAdapter(plc))
    events: list[dict[str, Any]] = []
    controller = ActuationController(
        repository, registry, on_event=lambda event: _collect(events, event)
    )
    result = await controller.execute(decision(action_command()))
    assert result.result is ActionResult.EXECUTED
    assert plc.values["vfd_speed_rpm"] == 2830.0
    assert repository.list_actions()[0].action_id == result.action_id
    assert events and events[0]["type"] == "action"


async def _collect(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    """Capture an emitted event."""
    events.append(event)


async def test_verification_records_improvement(repository: Repository) -> None:
    """Improved vibration produces a VERIFIED audit record."""
    plc = SimulatedPLC()
    registry = DeviceRegistry(simulated=SimulatedAdapter(plc))
    controller = ActuationController(
        repository,
        registry,
        get_velocity=lambda _node: 7.0,
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    command = action_command(timeout_s=1, min_improvement_pct=10.0, baseline=8.0)
    await controller.execute(decision(command))
    await asyncio.sleep(0.01)
    results = [audit.result for audit in repository.list_actions()]
    assert ActionResult.VERIFIED in results


async def test_no_improvement_triggers_rollback(repository: Repository) -> None:
    """A failed verification restores the previous setpoint and escalates."""
    plc = SimulatedPLC()
    registry = DeviceRegistry(simulated=SimulatedAdapter(plc))
    events: list[dict[str, Any]] = []
    controller = ActuationController(
        repository,
        registry,
        on_event=lambda event: _collect(events, event),
        get_velocity=lambda _node: 8.0,
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    command = action_command(timeout_s=1, min_improvement_pct=10.0, baseline=8.0)
    await controller.execute(decision(command))
    await asyncio.sleep(0.01)
    results = [audit.result for audit in repository.list_actions()]
    assert ActionResult.ROLLED_BACK in results
    assert plc.values["vfd_speed_rpm"] == 2950.0
    assert any(event.get("escalate") for event in events)
