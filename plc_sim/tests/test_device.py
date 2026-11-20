"""Tests for the simulated PLC device model."""

from __future__ import annotations

from plc_sim.device import SimulatedPLC


def test_write_enforces_device_bounds() -> None:
    """Writes are clamped to physical device bounds and recorded."""
    plc = SimulatedPLC()
    result = plc.write("vfd_speed_rpm", 9999.0)
    assert result.accepted
    assert result.after == 3600.0
    assert plc.write_history[-1][0] == "vfd_speed_rpm"


def test_unknown_tag_is_rejected() -> None:
    """Unknown tags cannot be written."""
    assert not SimulatedPLC().write("sis_esd", 1.0).accepted


def test_fault_changes_vibration_response() -> None:
    """Cavitation responds to speed and suction pressure changes."""
    plc = SimulatedPLC()
    plc.set_fault("cavitation", 0.9)
    baseline = plc.vibration_index()
    plc.write("vfd_speed_rpm", 2400.0)
    assert plc.vibration_index() < baseline
    plc.write("suction_pressure_kpa", 3900.0)
    assert plc.vibration_index() < baseline


def test_snapshot_includes_all_tags() -> None:
    """Snapshots include setpoints and derived vibration."""
    snapshot = SimulatedPLC().snapshot()
    assert "vfd_speed_rpm" in snapshot
    assert "vibration_index" in snapshot
