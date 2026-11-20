"""Stepwise scenario runner that emits feature messages over time."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pipeguard_sim.dsp import FeatureConfig, Features, extract_features
from pipeguard_sim.messages import (
    NodeHealth,
    make_feature_message,
    make_raw_message,
    make_status_message,
)
from pipeguard_sim.signals import (
    FaultType,
    OperatingState,
    SensorFaultMode,
    SignalParams,
    SignalResult,
    generate_signal,
)


@dataclass(frozen=True)
class FaultWindow:
    """A fault active from ``start_s`` until the next window."""

    start_s: float
    fault: FaultType = FaultType.NORMAL
    severity: float = 0.0
    sensor_fault_mode: SensorFaultMode = SensorFaultMode.NONE
    arrival_delay_s: float = 0.0

    def __post_init__(self) -> None:
        """Validate the fault severity."""
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be between 0 and 1")


@dataclass(frozen=True)
class SimulatorConfig:
    """Configuration for :class:`PipelineSimulator`."""

    site: str = "gulf-north"
    segment: str = "seg-12"
    node_id: str = "node-03"
    sample_rate_hz: int = 2000
    window_seconds: float = 0.5
    natural_frequency_hz: float = 187.0
    duration_s: float = 30.0
    base_state: OperatingState = field(default_factory=OperatingState)
    schedule: tuple[FaultWindow, ...] = field(default_factory=lambda: (FaultWindow(0.0),))
    signing_key: str | None = None
    seed: int = 42

    def feature_config(self) -> FeatureConfig:
        """Return the matching DSP configuration."""
        return FeatureConfig(
            sample_rate_hz=self.sample_rate_hz,
            window_seconds=self.window_seconds,
        )


@dataclass(frozen=True)
class SimulationStep:
    """One emitted analysis window."""

    message: dict[str, object]
    features: Features
    sequence: int
    waveform_mps2: np.ndarray
    fault: FaultType
    severity: float
    pressure_kpa: float
    event_time_s: float | None


def _active_window(schedule: tuple[FaultWindow, ...], elapsed_s: float) -> FaultWindow:
    """Return the last scheduled fault whose start time has passed."""
    active = schedule[0]
    for window in schedule:
        if window.start_s <= elapsed_s:
            active = window
        else:
            break
    return active


def build_schedule(scenario: str) -> tuple[FaultWindow, ...]:
    """Return a fault schedule for a named demo scenario."""
    schedules: dict[str, tuple[FaultWindow, ...]] = {
        "normal": (FaultWindow(0.0),),
        "cavitation": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.CAVITATION, 0.85),
        ),
        "resonance": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.RESONANCE, 0.8),
        ),
        "water_hammer": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.WATER_HAMMER, 0.9),
        ),
        "loose_support": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.LOOSE_SUPPORT, 0.9),
        ),
        "leak": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.LEAK, 0.8),
        ),
        "imbalance": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.IMBALANCE, 0.85),
        ),
        "sensor_failure": (
            FaultWindow(0.0),
            FaultWindow(6.0, FaultType.SENSOR_FAULT, 0.9, SensorFaultMode.BIAS_DRIFT),
        ),
        "mixed": (
            FaultWindow(0.0),
            FaultWindow(5.0, FaultType.CAVITATION, 0.8),
            FaultWindow(11.0),
            FaultWindow(14.0, FaultType.RESONANCE, 0.75),
            FaultWindow(20.0),
            FaultWindow(23.0, FaultType.LOOSE_SUPPORT, 0.85),
        ),
        "all": (
            FaultWindow(0.0),
            FaultWindow(4.0, FaultType.CAVITATION, 0.85),
            FaultWindow(9.0),
            FaultWindow(12.0, FaultType.RESONANCE, 0.8),
            FaultWindow(17.0),
            FaultWindow(20.0, FaultType.WATER_HAMMER, 0.9),
            FaultWindow(24.0),
            FaultWindow(27.0, FaultType.LOOSE_SUPPORT, 0.9),
            FaultWindow(32.0),
            FaultWindow(35.0, FaultType.LEAK, 0.8),
            FaultWindow(40.0),
            FaultWindow(43.0, FaultType.IMBALANCE, 0.85),
            FaultWindow(48.0),
            FaultWindow(51.0, FaultType.SENSOR_FAULT, 0.9, SensorFaultMode.BIAS_DRIFT),
        ),
    }
    if scenario not in schedules:
        raise ValueError(f"unknown scenario: {scenario}")
    return schedules[scenario]


class PipelineSimulator:
    """Deterministic, stateful producer of PipeGuard feature messages."""

    def __init__(self, config: SimulatorConfig | None = None) -> None:
        """Initialize the simulator cursor."""
        self.config = config or SimulatorConfig()
        self.elapsed_s = 0.0
        self.sequence = 0
        self.last_features: Features | None = None

    @property
    def finished(self) -> bool:
        """Whether the configured duration has elapsed."""
        return self.elapsed_s >= self.config.duration_s - 1e-9

    def step(self) -> SimulationStep:
        """Generate and return the next analysis window."""
        cfg = self.config
        window = _active_window(cfg.schedule, self.elapsed_s)
        params = SignalParams(
            fault=window.fault,
            severity=window.severity,
            natural_frequency_hz=cfg.natural_frequency_hz,
            sensor_fault_mode=window.sensor_fault_mode,
            arrival_delay_s=window.arrival_delay_s,
            seed=cfg.seed,
        )
        result: SignalResult = generate_signal(
            duration_s=cfg.window_seconds,
            sample_rate_hz=cfg.sample_rate_hz,
            operating_state=cfg.base_state,
            params=params,
        )
        features = extract_features(result.accel_mps2, cfg.feature_config())
        pressure = float(np.mean(result.pressure_kpa))
        state = OperatingState(
            flow_m3h=cfg.base_state.flow_m3h * (1.0 - 0.08 * window.severity)
            if window.fault is FaultType.CAVITATION
            else cfg.base_state.flow_m3h,
            pressure_kpa=pressure,
            pump_speed_rpm=cfg.base_state.pump_speed_rpm,
            valve_position_pct=cfg.base_state.valve_position_pct,
        )
        health = NodeHealth(
            sampling_ok=window.fault is not FaultType.SENSOR_FAULT,
            drift_ppm=25.0
            if window.sensor_fault_mode is SensorFaultMode.BIAS_DRIFT
            else 3.1,
        )
        timestamp = f"T+{self.elapsed_s:.3f}s"
        message = make_feature_message(
            site=cfg.site,
            segment=cfg.segment,
            node_id=cfg.node_id,
            sequence=self.sequence,
            features=features,
            operating_state=state,
            timestamp=timestamp,
            health=health,
            signing_key=cfg.signing_key,
        )
        step = SimulationStep(
            message=message,
            features=features,
            sequence=self.sequence,
            waveform_mps2=result.accel_mps2,
            fault=window.fault,
            severity=window.severity,
            pressure_kpa=pressure,
            event_time_s=result.event_time_s,
        )
        self.last_features = features
        self.elapsed_s += cfg.window_seconds
        self.sequence += 1
        return step

    def run(self) -> list[SimulationStep]:
        """Run the whole configured scenario and return every step."""
        steps: list[SimulationStep] = []
        while not self.finished:
            steps.append(self.step())
        return steps

    def status_message(self, online: bool, reason: str = "") -> dict[str, object]:
        """Build a status/LWT message for this node."""
        return make_status_message(
            site=self.config.site,
            segment=self.config.segment,
            node_id=self.config.node_id,
            online=online,
            reason=reason,
            signing_key=self.config.signing_key,
        )

    def raw_message(self, step: SimulationStep, trigger_reason: str = "test") -> dict[str, object]:
        """Build a raw waveform message for the most recent step."""
        samples_mg = (step.waveform_mps2[:, 2] / 9.80665) * 1000.0
        return make_raw_message(
            site=self.config.site,
            segment=self.config.segment,
            node_id=self.config.node_id,
            sequence=step.sequence + 100000,
            t0=str(step.message["timestamp"]),
            sample_rate_hz=self.config.sample_rate_hz,
            axis="z",
            samples=samples_mg.tolist(),
            trigger_reason=trigger_reason,
            signing_key=self.config.signing_key,
        )
