"""Tests for layered detection and debounce behaviour."""

from __future__ import annotations

from conftest import feature_message

from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.detection.detector import Detector
from pipeguard_backend.detection.layers import band_layer, threshold_layer, trend_layer
from pipeguard_backend.schemas import Severity


def test_threshold_layer_follows_velocity_zones(config: Config) -> None:
    """Higher velocity RMS produces a higher threshold score."""
    assert threshold_layer(1.0, config.detection) < 0.1
    assert threshold_layer(5.0, config.detection) > threshold_layer(2.0, config.detection)
    assert threshold_layer(14.0, config.detection) > 0.8


def test_band_and_trend_layers(config: Config) -> None:
    """Band deviation and rising trends are scored."""
    assert band_layer({"500_2000": 0.9}, config.detection, None) > 0.5
    history = [
        {"features": {"velocity_rms_mm_s": value}}
        for value in (2.0, 3.0, 4.0, 5.0, 6.0, 7.0)
    ]
    assert trend_layer(history, config.detection) > 0.5


def test_debounce_requires_n_of_m_high_scores(repository: Repository, config: Config) -> None:
    """Anomaly severity appears only after the configured number of hits."""
    detector = Detector(repository, config, clock=lambda: 0.0)
    results = []
    for sequence in range(4):
        message = feature_message(
            sequence=sequence,
            velocity_rms_mm_s=14.0,
            band_energies={"500_2000": 0.9, "10_50": 0.35},
        )
        results.append(detector.evaluate(message))
    assert [result.debounce_count for result in results] == [1, 2, 3, 3]
    assert all(result.severity is Severity.NORMAL for result in results[:2])
    assert results[2].severity is not Severity.NORMAL


def test_normal_messages_do_not_raise_alarm(repository: Repository, config: Config) -> None:
    """Healthy telemetry stays normal across the warm-up period."""
    detector = Detector(repository, config, clock=lambda: 0.0)
    results = [
        detector.evaluate(feature_message(sequence=sequence))
        for sequence in range(6)
    ]
    assert all(result.severity is Severity.NORMAL for result in results)
