"""Tests for evidence-based fault diagnosis."""

from __future__ import annotations

from conftest import feature_message
from pipeguard_sim.signals import FaultType

from pipeguard_backend.config import Config
from pipeguard_backend.diagnosis.classifier import DiagnosisEngine
from pipeguard_backend.schemas import (
    Cause,
    DetectionResult,
    FeatureMessage,
    FFTPeak,
    Severity,
)

HISTORY = [
    {
        "operating_state": {"pressure_kpa": 3450.0},
        "features": {"velocity_rms_mm_s": 2.0},
        "ts": "T+0",
    }
    for _ in range(5)
]


def detection(score: float = 0.8) -> DetectionResult:
    """Return a detection result for diagnosis tests."""
    return DetectionResult(
        node_id="node-03",
        timestamp="2026-01-01T00:00:00Z",
        score=score,
        severity=Severity.WARNING,
    )


def test_cavitation_from_high_band_and_pressure_drop(config: Config) -> None:
    """Broadband high-frequency energy plus suction drop indicates cavitation."""
    message: FeatureMessage = feature_message(
        pressure_kpa=2950.0,
        velocity_rms_mm_s=12.0,
        band_energies={"500_2000": 0.9},
    )
    result = DiagnosisEngine(config).diagnose(message, detection(), HISTORY)
    assert result.cause is Cause.CAVITATION
    assert result.confidence > 0.6
    assert any(item.feature == "pressure_drop_kpa" for item in result.evidence)


def test_resonance_from_natural_frequency_peak(config: Config) -> None:
    """A narrow peak at the configured natural frequency indicates resonance."""
    message: FeatureMessage = feature_message(
        velocity_rms_mm_s=9.0,
        band_energies={"150_500": 0.9},
    )
    message.features.fft_peaks = [FFTPeak(hz=187.0, amplitude_mps2=1.5)]
    result = DiagnosisEngine(config).diagnose(message, detection(), HISTORY)
    assert result.cause is Cause.RESONANCE


def test_sensor_fault_dominates_other_evidence(config: Config) -> None:
    """Unhealthy sampling forces a fail-safe sensor-fault diagnosis."""
    message: FeatureMessage = feature_message(
        pressure_kpa=2950.0,
        velocity_rms_mm_s=12.0,
        band_energies={"500_2000": 0.9},
        sampling_ok=False,
        drift_ppm=40.0,
    )
    result = DiagnosisEngine(config).diagnose(message, detection(), HISTORY)
    assert result.cause is Cause.SENSOR_FAULT
    assert result.confidence > 0.9


def test_leak_is_always_critical(config: Config) -> None:
    """A probable leak escalates alarm severity regardless of detection score."""
    message: FeatureMessage = feature_message(
        pressure_kpa=2900.0,
        velocity_rms_mm_s=11.0,
        band_energies={name: 0.6 for name in ("10_50", "50_150", "150_500", "500_2000")},
    )
    result = DiagnosisEngine(config).diagnose(message, detection(0.6), HISTORY)
    assert result.cause is Cause.LEAK
    assert result.severity is Severity.CRITICAL


def test_raised_alarm_is_not_explained_away_as_normal(config: Config) -> None:
    """A moderate detection score with a pressure surge still diagnoses water hammer."""
    message: FeatureMessage = feature_message(
        fault=FaultType.WATER_HAMMER,
        severity=0.9,
        pressure_kpa=3855.0,
    )
    baseline = {"kurtosis_mean": 3.5, "crest_mean": 5.0, "velocity_mean": 2.0}
    result = DiagnosisEngine(config).diagnose(message, detection(0.4), HISTORY, baseline)
    assert result.cause is Cause.WATER_HAMMER
    assert result.confidence > 0.5


def test_broadband_energy_favours_leak_over_cavitation(config: Config) -> None:
    """Cavitation needs high-band dominance; a leak raises mid and high bands together."""
    message: FeatureMessage = feature_message(
        fault=FaultType.LEAK,
        severity=0.8,
        pressure_kpa=3258.0,
        band_energies={
            "10_50": 0.055,
            "50_150": 0.093,
            "150_500": 0.327,
            "500_2000": 0.524,
        },
    )
    result = DiagnosisEngine(config).diagnose(message, detection(0.55), HISTORY)
    assert result.cause is Cause.LEAK
    assert result.all_scores[Cause.LEAK.value] > result.all_scores[Cause.CAVITATION.value]
