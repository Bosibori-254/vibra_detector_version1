"""Unit tests for synthetic fault signals."""

from __future__ import annotations

import numpy as np
import pytest

from pipeguard_sim.dsp import FeatureConfig, extract_features
from pipeguard_sim.signals import (
    FaultType,
    OperatingState,
    SensorFaultMode,
    SignalParams,
    generate_signal,
)

SR = 2000
DURATION = 2.0
CFG = FeatureConfig(sample_rate_hz=SR, window_seconds=DURATION)
STATE = OperatingState()


def features_for(fault: FaultType, severity: float = 0.8, **kwargs: object) -> object:
    """Generate a signal and return its feature vector."""
    signal = generate_signal(
        DURATION,
        SR,
        STATE,
        SignalParams(fault=fault, severity=severity, seed=7, **kwargs),  # type: ignore[arg-type]
    )
    return extract_features(signal.accel_mps2, CFG)


def test_generation_is_deterministic_for_a_seed() -> None:
    params = SignalParams(fault=FaultType.CAVITATION, severity=0.7, seed=123)
    a = generate_signal(DURATION, SR, STATE, params)
    b = generate_signal(DURATION, SR, STATE, params)
    assert np.array_equal(a.accel_mps2, b.accel_mps2)


def test_severity_is_validated() -> None:
    with pytest.raises(ValueError):
        SignalParams(severity=1.5)


def test_normal_vibration_is_low_and_broadband() -> None:
    normal = features_for(FaultType.NORMAL, 0.0)
    assert normal.velocity_rms_mm_s < 15.0  # type: ignore[attr-defined]
    assert normal.kurtosis < 2.0  # type: ignore[attr-defined]


def test_cavitation_adds_high_frequency_energy_and_pressure_drop() -> None:
    normal = features_for(FaultType.NORMAL, 0.0)
    cavitation = features_for(FaultType.CAVITATION, 0.9)
    assert cavitation.band_energies["500_2000"] > normal.band_energies["500_2000"] * 1.5  # type: ignore[attr-defined]
    signal = generate_signal(
        DURATION,
        SR,
        STATE,
        SignalParams(fault=FaultType.CAVITATION, severity=0.9, seed=7),
    )
    assert float(np.mean(signal.pressure_kpa)) < STATE.pressure_kpa - 300.0


def test_resonance_creates_narrow_peak_at_natural_frequency() -> None:
    resonance = features_for(FaultType.RESONANCE, 0.9, natural_frequency_hz=187.0)
    assert any(abs(p.hz - 187.0) < 5.0 for p in resonance.fft_peaks)  # type: ignore[attr-defined]


def test_water_hammer_has_high_crest_factor_and_pressure_surge() -> None:
    normal = features_for(FaultType.NORMAL, 0.0)
    hammer = features_for(FaultType.WATER_HAMMER, 0.9)
    assert hammer.crest_factor > normal.crest_factor * 2.0  # type: ignore[attr-defined]
    signal = generate_signal(
        DURATION,
        SR,
        STATE,
        SignalParams(fault=FaultType.WATER_HAMMER, severity=0.9, seed=7),
    )
    assert float(np.max(signal.pressure_kpa)) > STATE.pressure_kpa + 500.0


def test_loose_support_raises_kurtosis() -> None:
    normal = features_for(FaultType.NORMAL, 0.0)
    loose = features_for(FaultType.LOOSE_SUPPORT, 0.9)
    assert loose.kurtosis > normal.kurtosis + 3.0  # type: ignore[attr-defined]
    assert loose.band_energies["10_50"] > normal.band_energies["10_50"]  # type: ignore[attr-defined]


def test_leak_is_localizable_by_arrival_delay() -> None:
    params_a = SignalParams(fault=FaultType.LEAK, severity=0.8, seed=7, arrival_delay_s=0.0)
    params_b = SignalParams(fault=FaultType.LEAK, severity=0.8, seed=7, arrival_delay_s=0.05)
    a = generate_signal(DURATION, SR, STATE, params_a).accel_mps2[:, 2]
    b = generate_signal(DURATION, SR, STATE, params_b).accel_mps2[:, 2]
    correlation = np.correlate(a, b, mode="full")
    lag_samples = int(np.argmax(correlation) - (len(a) - 1))
    assert abs(lag_samples / SR - 0.05) < 0.01


def test_imbalance_has_running_speed_harmonic() -> None:
    imbalance = features_for(FaultType.IMBALANCE, 0.9)
    run_hz = STATE.pump_speed_rpm / 60.0
    assert any(abs(p.hz - run_hz) < 5.0 for p in imbalance.fft_peaks)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "mode",
    [
        SensorFaultMode.BIAS_DRIFT,
        SensorFaultMode.DROPOUT,
        SensorFaultMode.STUCK,
        SensorFaultMode.NOISE,
    ],
)
def test_sensor_fault_modes_change_the_signal(mode: SensorFaultMode) -> None:
    healthy = generate_signal(DURATION, SR, STATE, SignalParams(seed=7)).accel_mps2
    faulty = generate_signal(
        DURATION,
        SR,
        STATE,
        SignalParams(
            fault=FaultType.SENSOR_FAULT,
            severity=0.9,
            sensor_fault_mode=mode,
            seed=7,
        ),
    ).accel_mps2
    assert not np.allclose(healthy, faulty)
