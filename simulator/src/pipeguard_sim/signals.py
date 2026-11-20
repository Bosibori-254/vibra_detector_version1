"""Synthetic 3-axis accelerometer signals for every PipeGuard fault class."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy import signal as sp_signal


class FaultType(str, Enum):
    """Injectable pipeline/pump fault classes."""

    NORMAL = "normal"
    CAVITATION = "cavitation"
    RESONANCE = "resonance"
    WATER_HAMMER = "water_hammer"
    LOOSE_SUPPORT = "loose_support"
    LEAK = "leak"
    IMBALANCE = "imbalance"
    SENSOR_FAULT = "sensor_fault"


class SensorFaultMode(str, Enum):
    """How a sensor behaves when it fails."""

    NONE = "none"
    BIAS_DRIFT = "bias_drift"
    DROPOUT = "dropout"
    STUCK = "stuck"
    NOISE = "noise"


@dataclass(frozen=True)
class OperatingState:
    """Process conditions that gate thresholds and baselines."""

    flow_m3h: float = 820.0
    pressure_kpa: float = 3450.0
    pump_speed_rpm: float = 2950.0
    valve_position_pct: float = 100.0

    def as_dict(self) -> dict[str, float]:
        """Return the wire representation."""
        return {
            "flow_m3h": round(self.flow_m3h, 3),
            "pressure_kpa": round(self.pressure_kpa, 3),
            "pump_speed_rpm": round(self.pump_speed_rpm, 3),
            "valve_position_pct": round(self.valve_position_pct, 3),
        }


@dataclass(frozen=True)
class SignalParams:
    """Parameters controlling signal synthesis."""

    fault: FaultType = FaultType.NORMAL
    severity: float = 0.0
    natural_frequency_hz: float = 187.0
    sensor_fault_mode: SensorFaultMode = SensorFaultMode.NONE
    event_time_fraction: float = 0.45
    arrival_delay_s: float = 0.0
    seed: int | None = None

    def __post_init__(self) -> None:
        """Validate severity range."""
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be between 0 and 1")


@dataclass(frozen=True)
class SignalResult:
    """A synthesized acceleration waveform plus the accompanying pressure trace."""

    accel_mps2: np.ndarray
    pressure_kpa: np.ndarray
    time_s: np.ndarray
    event_time_s: float | None = None


def _unit_band_noise(
    rng: np.random.Generator, n: int, sample_rate_hz: int, low: float, high: float
) -> np.ndarray:
    """Band-limited white noise with unit standard deviation."""
    nyquist = sample_rate_hz / 2.0
    upper = min(high, nyquist * 0.98)
    lower = min(low, upper - 1.0)
    sos = sp_signal.butter(4, [lower, upper], btype="bandpass", fs=sample_rate_hz, output="sos")
    noise = sp_signal.sosfiltfilt(sos, rng.standard_normal(n))
    std = float(np.std(noise))
    return np.asarray(noise / std if std > 1e-12 else noise, dtype=np.float64)


def generate_signal(
    duration_s: float,
    sample_rate_hz: int,
    operating_state: OperatingState | None = None,
    params: SignalParams | None = None,
) -> SignalResult:
    """Generate ``duration_s`` of 3-axis acceleration at ``sample_rate_hz``.

    The output is deterministic for a given seed. Amplitudes are in m/s² and the
    pressure trace is in kPa, so fault-induced pressure changes are visible to the
    diagnosis layer.
    """
    state = operating_state or OperatingState()
    cfg = params or SignalParams()
    rng = np.random.default_rng(cfg.seed)
    n = max(round(duration_s * sample_rate_hz), 64)
    t = np.arange(n, dtype=np.float64) / float(sample_rate_hz)
    run_hz = max(state.pump_speed_rpm, 1.0) / 60.0
    phase = rng.uniform(0.0, 2.0 * np.pi)

    # Healthy baseline: small broadband vibration plus pump harmonics.
    xyz = np.zeros((n, 3), dtype=np.float64)
    for axis in range(3):
        xyz[:, axis] = rng.normal(0.0, 0.32, n)
    xyz[:, 2] += 0.48 * np.sin(2.0 * np.pi * run_hz * t + phase)
    xyz[:, 0] += 0.26 * np.sin(2.0 * np.pi * run_hz * t + phase + 0.4)
    xyz[:, 2] += 0.21 * np.sin(2.0 * np.pi * 2.0 * run_hz * t + 0.7)
    xyz[:, 1] += 0.15 * np.sin(2.0 * np.pi * run_hz * t + 1.2)

    pressure = np.full(n, state.pressure_kpa, dtype=np.float64)
    pressure += rng.normal(0.0, 2.5, n)
    event_time: float | None = None

    if cfg.fault is FaultType.CAVITATION:
        high = _unit_band_noise(rng, n, sample_rate_hz, 600.0, 1800.0)
        envelope = 0.55 + 0.45 * np.sin(2.0 * np.pi * 17.0 * t)
        bursts = (rng.random(n) < 0.002 * cfg.severity).astype(float)
        bursts = sp_signal.sosfiltfilt(
            sp_signal.butter(2, 120.0, fs=sample_rate_hz, output="sos"), bursts
        )
        if np.max(np.abs(bursts)) > 0:
            bursts /= float(np.max(np.abs(bursts)))
        cavitation = 1.5 * cfg.severity * high * (envelope + np.abs(bursts))
        xyz[:, 2] += cavitation
        xyz[:, 0] += 0.5 * cavitation
        pressure -= 520.0 * cfg.severity

    elif cfg.fault is FaultType.RESONANCE:
        natural = min(cfg.natural_frequency_hz, sample_rate_hz * 0.4)
        modulation = 1.0 + 0.15 * np.sin(2.0 * np.pi * 0.8 * t)
        resonant = 1.8 * cfg.severity * modulation * np.sin(2.0 * np.pi * natural * t + phase)
        xyz[:, 2] += resonant
        xyz[:, 0] += 0.35 * resonant
        xyz[:, 1] += 0.2 * resonant

    elif cfg.fault is FaultType.WATER_HAMMER:
        event_time = float(cfg.event_time_fraction * duration_s)
        since = t - event_time
        active = since >= 0.0
        ring_hz = 32.0
        impulse = 4.0 * cfg.severity * np.exp(-np.clip(since, 0.0, None) / 0.07)
        impulse *= np.sin(2.0 * np.pi * ring_hz * np.clip(since, 0.0, None))
        xyz[:, 2] += np.where(active, impulse, 0.0)
        xyz[:, 0] += 0.4 * np.where(active, impulse, 0.0)
        pressure += np.where(
            active, 950.0 * cfg.severity * np.exp(-np.clip(since, 0.0, None) / 0.9), 0.0
        )

    elif cfg.fault is FaultType.LOOSE_SUPPORT:
        impact_period = 0.18
        impact_times = np.arange(0.05, duration_s, impact_period)
        for impact in impact_times:
            jitter = rng.normal(0.0, 0.006)
            idx = int((impact + jitter) * sample_rate_hz)
            if 0 <= idx < n:
                decay_len = min(int(0.06 * sample_rate_hz), n - idx)
                k = np.arange(decay_len) / float(sample_rate_hz)
                strike = 12.0 * cfg.severity * np.exp(-k / 0.006)
                strike *= np.sin(2.0 * np.pi * 27.0 * k)
                xyz[idx : idx + decay_len, 2] += strike
                xyz[idx : idx + decay_len, 0] += 0.3 * strike
        xyz[:, 2] += 0.8 * cfg.severity * _unit_band_noise(rng, n, sample_rate_hz, 5.0, 45.0)

    elif cfg.fault is FaultType.LEAK:
        broadband = _unit_band_noise(rng, n, sample_rate_hz, 150.0, 1500.0)
        dig_bursts = (rng.random(n) < 0.004 * cfg.severity).astype(float)
        dig_bursts = sp_signal.sosfiltfilt(
            sp_signal.butter(2, 80.0, fs=sample_rate_hz, output="sos"), dig_bursts
        )
        if np.max(np.abs(dig_bursts)) > 0:
            dig_bursts /= float(np.max(np.abs(dig_bursts)))
        leak = 1.1 * cfg.severity * (broadband + 0.6 * np.abs(dig_bursts))
        delay = round(cfg.arrival_delay_s * sample_rate_hz)
        if delay > 0:
            leak = np.concatenate((np.zeros(delay), leak))[:n]
        xyz[:, 2] += leak
        xyz[:, 0] += 0.7 * leak
        pressure -= 240.0 * cfg.severity

    elif cfg.fault is FaultType.IMBALANCE:
        imbalance = 2.0 * cfg.severity * np.sin(2.0 * np.pi * run_hz * t + phase)
        misalignment = 1.1 * cfg.severity * np.sin(2.0 * np.pi * 2.0 * run_hz * t + 0.7)
        xyz[:, 2] += imbalance + misalignment
        xyz[:, 0] += 0.6 * imbalance + 0.8 * misalignment

    elif cfg.fault is FaultType.SENSOR_FAULT:
        mode = cfg.sensor_fault_mode
        if mode is SensorFaultMode.BIAS_DRIFT:
            xyz += (cfg.severity * 3.0 * t / max(duration_s, 1e-6))[:, None]
        elif mode is SensorFaultMode.DROPOUT:
            mask = rng.random(n) < 0.35 * cfg.severity
            xyz[mask] = 0.0
        elif mode is SensorFaultMode.STUCK:
            freeze = int(n * 0.35)
            xyz[freeze:] = xyz[freeze]
            pressure[freeze:] = pressure[freeze]
        elif mode is SensorFaultMode.NOISE:
            xyz += rng.normal(0.0, 6.0 * cfg.severity, (n, 3))

    return SignalResult(
        accel_mps2=xyz,
        pressure_kpa=pressure,
        time_s=t,
        event_time_s=event_time,
    )
