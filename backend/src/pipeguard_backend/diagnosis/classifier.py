"""Rule-based diagnosis with confidence, evidence and recommended actions."""

from __future__ import annotations

from typing import Any

import numpy as np

from pipeguard_backend.config import Config
from pipeguard_backend.schemas import (
    Cause,
    DetectionResult,
    Diagnosis,
    EvidenceItem,
    FeatureMessage,
    Severity,
)


def _ratio(observed: float, expected: float) -> float:
    """Return a bounded observed/expected ratio."""
    return float(np.clip(observed / max(abs(expected), 1e-6), 0.0, 10.0))


class DiagnosisEngine:
    """Classify the probable cause from features, baseline and operating state."""

    def __init__(self, config: Config) -> None:
        """Store configuration."""
        self.config = config

    def diagnose(
        self,
        message: FeatureMessage,
        detection: DetectionResult,
        history: list[dict[str, Any]],
        baseline: dict[str, Any] | None = None,
        arrival_times: dict[str, float] | None = None,
    ) -> Diagnosis:
        """Return the most likely cause with supporting evidence."""
        features = message.features
        bands = features.band_energies
        scores: dict[str, float] = {}
        evidence: dict[str, list[EvidenceItem]] = {}

        expected_pressure = self._expected_pressure(history, message)
        expected_velocity = float(baseline.get("velocity_mean", 0.0)) if baseline else 0.0
        expected_kurtosis = float(baseline.get("kurtosis_mean", 1.0)) if baseline else 1.0
        expected_crest = float(baseline.get("crest_mean", 3.0)) if baseline else 3.0
        high_band = float(bands.get("500_2000", 0.0))
        low_band = float(bands.get("10_50", 0.0))
        ref_high = float(self.config.detection.band_reference.get("500_2000", 0.3))

        def add(cause: Cause, name: str, observed: float, expected: float, weight: float,
                contribution: float, detail: str = "") -> None:
            """Accumulate evidence and score for a cause."""
            scores.setdefault(cause.value, 0.0)
            scores[cause.value] += contribution
            evidence.setdefault(cause.value, []).append(
                EvidenceItem(
                    feature=name,
                    observed=round(float(observed), 4),
                    expected=round(float(expected), 4),
                    weight=round(weight, 3),
                    detail=detail,
                )
            )

        # Cavitation: high-frequency broadband energy plus suction pressure drop.
        high_ratio = _ratio(high_band, ref_high)
        pressure_drop = max(expected_pressure - message.operating_state.pressure_kpa, 0.0)
        cav_score = 0.6 * min(high_ratio / 2.0, 1.0) + 0.4 * min(pressure_drop / 400.0, 1.0)
        if features.velocity_rms_mm_s > expected_velocity > 0:
            cav_score += 0.1
        add(Cause.CAVITATION, "band_500_2000", high_band, ref_high, 0.6,
            0.6 * min(high_ratio / 2.0, 1.0), "broadband high-frequency energy")
        add(Cause.CAVITATION, "pressure_drop_kpa", pressure_drop, 400.0, 0.4,
            0.4 * min(pressure_drop / 400.0, 1.0))

        # Resonance: narrow peak near a configured natural frequency.
        natural = self.config.detection.natural_frequencies_hz
        peak_hit = 0.0
        peak_detail = ""
        for peak in features.fft_peaks:
            for freq in natural:
                if abs(peak.hz - freq) < max(freq * 0.04, 3.0):
                    peak_hit = min(peak.amplitude_mps2 / 1.0, 1.0)
                    peak_detail = f"peak at {peak.hz:.1f} Hz near natural {freq:.1f} Hz"
        add(Cause.RESONANCE, "narrow_peak_amplitude", peak_hit, 1.0, 0.8, 0.8 * peak_hit,
            peak_detail)

        # Water hammer: impulsive transient and pressure surge.
        crest_ratio = _ratio(features.crest_factor, max(expected_crest, 3.0))
        surge = max(message.operating_state.pressure_kpa - expected_pressure, 0.0)
        hammer_score = 0.55 * min(crest_ratio / 2.0, 1.0) + 0.45 * min(surge / 600.0, 1.0)
        add(Cause.WATER_HAMMER, "crest_factor", features.crest_factor, expected_crest, 0.55,
            0.55 * min(crest_ratio / 2.0, 1.0))
        add(Cause.WATER_HAMMER, "pressure_surge_kpa", surge, 600.0, 0.45,
            0.45 * min(surge / 600.0, 1.0))

        # Loose support: impulsive, low-frequency, high kurtosis.
        kurt_ratio = _ratio(features.kurtosis, max(expected_kurtosis, 1.0))
        low_ratio = _ratio(low_band, 0.2)
        loose_score = 0.65 * min(kurt_ratio / 4.0, 1.0) + 0.35 * min(low_ratio / 2.0, 1.0)
        add(Cause.LOOSE_SUPPORT, "kurtosis", features.kurtosis, expected_kurtosis, 0.65,
            0.65 * min(kurt_ratio / 4.0, 1.0), "impact-like impulses")
        add(Cause.LOOSE_SUPPORT, "band_10_50", low_band, 0.2, 0.35,
            0.35 * min(low_ratio / 2.0, 1.0))

        # Leak / third-party interference: localized broadband rise.
        broadband = float(np.mean(list(bands.values())))
        leak_score = min(_ratio(broadband, 0.25) / 2.5, 1.0)
        location = None
        if arrival_times and len(arrival_times) >= 2:
            times = sorted(arrival_times.items(), key=lambda item: item[1])
            location = {
                "first_node": times[0][0],
                "last_node": times[-1][0],
                "delta_s": round(times[-1][1] - times[0][1], 4),
                "method": "time_of_arrival",
            }
            leak_score = min(leak_score + 0.2, 1.0)
        add(Cause.LEAK, "broadband_mean", broadband, 0.25, 0.7,
            min(_ratio(broadband, 0.25) / 2.5, 1.0), "localized broadband energy")
        if pressure_drop > 0:
            add(Cause.LEAK, "pressure_drop_kpa", pressure_drop, 250.0, 0.3,
                0.3 * min(pressure_drop / 250.0, 1.0))

        # Imbalance / misalignment: 1x and 2x running-speed harmonics.
        run_hz = message.operating_state.pump_speed_rpm / 60.0
        harmonic_1 = max(
            (p.amplitude_mps2 for p in features.fft_peaks if abs(p.hz - run_hz) < 5.0),
            default=0.0,
        )
        harmonic_2 = max(
            (p.amplitude_mps2 for p in features.fft_peaks if abs(p.hz - 2 * run_hz) < 7.0),
            default=0.0,
        )
        harmonic_score = min(harmonic_1 / 1.5, 1.0) * 0.6 + min(harmonic_2 / 1.0, 1.0) * 0.4
        add(Cause.IMBALANCE, "harmonic_1x", harmonic_1, 1.5, 0.6, 0.6 * min(harmonic_1 / 1.5, 1.0))
        add(Cause.IMBALANCE, "harmonic_2x", harmonic_2, 1.0, 0.4, 0.4 * min(harmonic_2 / 1.0, 1.0))

        # Sensor fault is a fail-safe cause, never an actuation trigger.
        sensor_score = 0.0
        if not message.health.sampling_ok:
            sensor_score += 0.7
        if message.health.drift_ppm > 20.0:
            sensor_score += 0.3
        add(Cause.SENSOR_FAULT, "sampling_ok", float(message.health.sampling_ok), 1.0, 0.7,
            0.7 if not message.health.sampling_ok else 0.0)
        add(Cause.SENSOR_FAULT, "drift_ppm", message.health.drift_ppm, 20.0, 0.3,
            0.3 * min(message.health.drift_ppm / 20.0, 1.0))

        scores[Cause.NORMAL.value] = max(0.0, 1.0 - detection.score) if detection.score else 0.5
        evidence[Cause.NORMAL.value] = [
            EvidenceItem(
                feature="detection_score", observed=round(detection.score, 4), expected=0.2,
                weight=1.0, detail="layered detector score",
            )
        ]

        # Sensor faults dominate: fail-safe classification.
        if sensor_score >= 0.7:
            cause, confidence = Cause.SENSOR_FAULT, min(0.7 + sensor_score * 0.3, 0.99)
        else:
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            best, best_score = ranked[0]
            second = ranked[1][1] if len(ranked) > 1 else 0.0
            cause = Cause(best)
            if best_score < 0.25:
                cause, best_score = Cause.NORMAL, scores[Cause.NORMAL.value]
            margin = max(best_score - second, 0.0)
            confidence = float(np.clip(0.45 + 0.35 * best_score + 0.4 * margin, 0.0, 0.99))
            if cause is Cause.NORMAL and detection.severity is Severity.NORMAL:
                confidence = max(confidence, 0.8)

        severity = detection.severity
        if cause is Cause.LEAK:
            severity = Severity.CRITICAL
        policy = self.config.policies.policies.get(cause)
        recommendation = policy.action.description or policy.action.type if policy else "investigate"
        return Diagnosis(
            node_id=message.node_id,
            segment=message.segment,
            site=message.site,
            timestamp=message.timestamp,
            cause=cause,
            confidence=round(confidence, 4),
            evidence=evidence.get(cause.value, []),
            recommended_action=recommendation,
            severity=severity,
            location_estimate=location,
            all_scores={key: round(value, 4) for key, value in scores.items()},
        )

    @staticmethod
    def _expected_pressure(history: list[dict[str, Any]], message: FeatureMessage) -> float:
        """Estimate the nominal pressure from recent history."""
        pressures = [
            float(h["operating_state"]["pressure_kpa"])
            for h in history
            if "operating_state" in h
        ]
        if len(pressures) >= 3:
            return float(np.median(pressures))
        return message.operating_state.pressure_kpa
