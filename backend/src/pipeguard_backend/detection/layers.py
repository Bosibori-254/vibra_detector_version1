"""The four detection layers: thresholds, spectral bands, ML and trend."""

from __future__ import annotations

from typing import Any

import numpy as np

from pipeguard_backend.config import DetectionConfig


def _clip(value: float) -> float:
    """Clamp a score into [0, 1]."""
    return float(np.clip(value, 0.0, 1.0))


def threshold_layer(velocity_rms_mm_s: float, config: DetectionConfig) -> float:
    """ISO 10816/20816-style velocity zone score."""
    zones = config.velocity_zones_mm_s
    a, b, c = zones.get("A", 2.8), zones.get("B", 7.1), zones.get("C", 11.0)
    value = float(velocity_rms_mm_s)
    if value <= a:
        return _clip(0.1 * value / max(a, 1e-6))
    if value <= b:
        return 0.1 + 0.4 * (value - a) / max(b - a, 1e-6)
    if value <= c:
        return 0.5 + 0.35 * (value - b) / max(c - b, 1e-6)
    return min(1.0, 0.85 + 0.15 * (value - c) / max(c, 1e-6))


def band_layer(
    band_energies: dict[str, float], config: DetectionConfig, baseline: dict[str, Any] | None
) -> float:
    """Score deviation of band energy fractions from reference/baseline."""
    scores: list[float] = []
    for name, observed in band_energies.items():
        if baseline and baseline.get("band_mean", {}).get(name) is not None:
            expected = float(baseline["band_mean"][name])
            std = max(float(baseline.get("band_std", {}).get(name, 0.05)), 0.02)
        else:
            expected = float(config.band_reference.get(name, 0.25))
            std = 0.12
        scores.append(abs(float(observed) - expected) / std)
    return _clip(float(np.mean(scores)) / 4.0) if scores else 0.0


def trend_layer(history: list[dict[str, Any]], config: DetectionConfig) -> float:
    """Score the rate of change of velocity RMS over a short window."""
    window = max(config.trend_window, 2)
    values = [float(h["features"]["velocity_rms_mm_s"]) for h in history[-window:]]
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values), dtype=float)
    slope = float(np.polyfit(x, np.asarray(values), 1)[0])
    return _clip(slope / max(config.trend_alert_slope, 1e-6))


class MLAnomalyLayer:
    """IsolationForest with a robust fallback when sklearn is unavailable."""

    def __init__(self, config: DetectionConfig) -> None:
        """Store configuration and an optional fitted model."""
        self.config = config
        self.model: Any | None = None
        self.baseline_stats: dict[str, Any] | None = None

    def fit(self, samples: list[list[float]]) -> None:
        """Fit an IsolationForest on a feature matrix when possible."""
        if len(samples) < 20:
            return
        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                contamination=max(self.config.ml_contamination, 0.01), random_state=42
            )
            model.fit(np.asarray(samples, dtype=float))
            self.model = model
        except ImportError:  # pragma: no cover - sklearn is a declared dependency
            self.model = None

    def score(
        self, features: Any, baseline: dict[str, Any] | None, history: list[dict[str, Any]]
    ) -> float:
        """Score one feature vector."""
        vector = self._vector(features)
        if self.model is not None:
            raw = -float(self.model.score_samples(np.asarray([vector], dtype=float))[0])
            return _clip(raw / 0.6)
        if len(history) >= 10:
            matrix = np.asarray([self._vector(h["features"]) for h in history[-100:]], dtype=float)
            history_mean = np.mean(matrix, axis=0)
            history_std = np.maximum(np.std(matrix, axis=0), 0.05)
            deviation = float(np.mean(np.abs((np.asarray(vector) - history_mean) / history_std)))
            return _clip(deviation / 4.0)
        values = [
            ("velocity", self._field(features, "velocity_rms_mm_s"), 3.0),
            ("kurtosis", self._field(features, "kurtosis"), 6.0),
            ("crest", self._field(features, "crest_factor"), 6.0),
        ]
        scores: list[float] = []
        for name, value, divisor in values:
            if baseline and baseline.get(f"{name}_std", 0) > 0.02:
                baseline_mean = float(baseline[f"{name}_mean"])
                baseline_std = max(float(baseline[f"{name}_std"]), 0.05)
                scores.append(abs(float(value) - baseline_mean) / (baseline_std * 3.0))
            else:
                scores.append(abs(float(value)) / divisor)
        return _clip(float(np.mean(scores)))

    @staticmethod
    def _field(features: Any, name: str) -> float:
        """Read a scalar feature from a model or its serialized history dict."""
        value = features.get(name) if isinstance(features, dict) else getattr(features, name)
        return float(value) if value is not None else 0.0

    @classmethod
    def _vector(cls, features: Any) -> list[float]:
        """Convert features into the ML input vector."""
        bands = (
            features.get("band_energies", {})
            if isinstance(features, dict)
            else features.band_energies
        )
        return [
            cls._field(features, "velocity_rms_mm_s"),
            cls._field(features, "kurtosis"),
            cls._field(features, "crest_factor"),
            float(bands.get("10_50", 0.0)),
            float(bands.get("50_150", 0.0)),
            float(bands.get("150_500", 0.0)),
            float(bands.get("500_2000", 0.0)),
            cls._field(features, "peak_mps2"),
        ]
