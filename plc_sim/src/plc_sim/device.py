"""In-process simulated PLC/VFD/valve with a simple physical response model."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "vfd_speed_rpm": (1200.0, 3600.0),
    "valve_close_rate_pct_s": (2.0, 50.0),
    "suction_pressure_kpa": (1800.0, 4200.0),
}

REGISTER_MAP: dict[str, int] = {
    "vfd_speed_rpm": 100,
    "valve_close_rate_pct_s": 101,
    "suction_pressure_kpa": 102,
    "vibration_index": 200,
    "surge_relief_enabled": 300,
}


@dataclass
class WriteResult:
    """Result of a device write."""

    accepted: bool
    tag: str
    before: float
    after: float
    reason: str = ""


@dataclass
class SimulatedPLC:
    """A tiny PLC simulation with setpoints and derived vibration response."""

    bounds: dict[str, tuple[float, float]] = field(
        default_factory=lambda: dict(DEFAULT_BOUNDS)
    )
    values: dict[str, float] = field(
        default_factory=lambda: {
            "vfd_speed_rpm": 2950.0,
            "valve_close_rate_pct_s": 20.0,
            "suction_pressure_kpa": 3450.0,
            "surge_relief_enabled": 0.0,
        }
    )
    active_fault: str = "normal"
    fault_severity: float = 0.0
    write_history: list[tuple[str, float, float, float]] = field(default_factory=list)

    def read(self, tag: str) -> float:
        """Read a tag; unknown tags read as zero."""
        if tag == "vibration_index":
            return self.vibration_index()
        return float(self.values.get(tag, 0.0))

    def write(self, tag: str, value: float) -> WriteResult:
        """Write a setpoint, enforcing physical device bounds."""
        if tag not in self.bounds:
            return WriteResult(False, tag, 0.0, 0.0, f"unknown tag {tag}")
        before = self.read(tag)
        low, high = self.bounds[tag]
        after = min(max(float(value), low), high)
        self.values[tag] = after
        self.write_history.append((tag, before, after, time.time()))
        return WriteResult(True, tag, before, after)

    def set_fault(self, fault: str, severity: float = 0.0) -> None:
        """Inject a fault that affects the simulated vibration response."""
        self.active_fault = fault
        self.fault_severity = severity

    def vibration_index(self) -> float:
        """Return a dimensionless vibration response influenced by fault and setpoints."""
        base = 1.0
        severity = self.fault_severity
        if self.active_fault == "cavitation":
            speed = self.values["vfd_speed_rpm"]
            suction = self.values["suction_pressure_kpa"]
            base += severity * (2.0 * max(0.0, speed - 2650.0) / 1000.0)
            base += severity * max(0.0, (3200.0 - suction) / 1000.0)
        elif self.active_fault == "resonance":
            speed = self.values["vfd_speed_rpm"]
            base += severity * 2.0 * max(0.0, 1.0 - abs(speed - 2950.0) / 300.0)
        elif self.active_fault == "water_hammer":
            base += severity * 1.5 * (self.values["valve_close_rate_pct_s"] / 50.0)
            if self.values.get("surge_relief_enabled", 0.0):
                base *= 0.7
        elif self.active_fault in {"loose_support", "leak", "imbalance"}:
            base += severity * 1.2
        return round(base, 6)

    def snapshot(self) -> dict[str, float]:
        """Return all tag values plus the derived vibration index."""
        return {**dict(self.values), "vibration_index": self.vibration_index()}
