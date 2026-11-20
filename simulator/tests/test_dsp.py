"""Unit tests for DSP feature extraction."""

from __future__ import annotations

import numpy as np
import pytest

from pipeguard_sim.dsp import (
    FeatureConfig,
    band_energies,
    crest_factor,
    extract_features,
    kurtosis,
    peak,
    rms,
    top_spectral_peaks,
    velocity_rms_mm_s,
)

SR = 2000
T = np.arange(SR) / SR


def test_rms_peak_crest_of_sine() -> None:
    sine = np.sin(2 * np.pi * 50 * T)
    assert rms(sine) == pytest.approx(1 / np.sqrt(2), abs=0.01)
    assert peak(sine) == pytest.approx(1.0, abs=0.01)
    assert crest_factor(sine) == pytest.approx(np.sqrt(2), abs=0.02)


def test_kurtosis_gaussian_is_near_zero() -> None:
    rng = np.random.default_rng(1)
    assert abs(kurtosis(rng.standard_normal(20000))) < 0.15


def test_kurtosis_impulsive_signal_is_positive() -> None:
    signal = np.zeros(2000)
    signal[500] = 20.0
    assert kurtosis(signal) > 20.0


def test_band_energies_localize_60hz_sine() -> None:
    energies = band_energies(np.sin(2 * np.pi * 60 * T), SR)
    assert energies["50_150"] > 0.9
    assert energies["500_2000"] < 0.05
    assert sum(energies.values()) == pytest.approx(1.0, abs=0.05)


def test_top_spectral_peaks_finds_narrow_tone() -> None:
    signal = np.sin(2 * np.pi * 187 * T) + 0.1 * np.sin(2 * np.pi * 60 * T)
    peaks = top_spectral_peaks(signal, SR, top_n=2)
    assert len(peaks) == 2
    assert abs(peaks[0].hz - 187.0) < 4.0


def test_velocity_rms_scales_with_amplitude() -> None:
    low = velocity_rms_mm_s(0.5 * np.sin(2 * np.pi * 80 * T), SR)
    high = velocity_rms_mm_s(2.0 * np.sin(2 * np.pi * 80 * T), SR)
    assert high > low > 0.0
    assert high / low == pytest.approx(4.0, rel=0.1)


def test_extract_features_validates_and_returns_schema() -> None:
    samples = np.column_stack(
        [np.sin(2 * np.pi * 25 * T), np.cos(2 * np.pi * 25 * T), np.sin(2 * np.pi * 80 * T)]
    )
    features = extract_features(samples, FeatureConfig())
    payload = features.as_dict()
    assert payload["sample_rate_hz"] == SR
    assert set(payload["accel_rms_mps2"]) == {"x", "y", "z"}
    assert set(payload["band_energies"]) == {"10_50", "50_150", "150_500", "500_2000"}
    assert payload["velocity_rms_mm_s"] > 0.0
    assert 1 <= len(payload["fft_peaks"]) <= 5
    with pytest.raises(ValueError):
        extract_features(np.zeros(4))
