"""Per-node, per-operating-state baseline learning."""

from __future__ import annotations

import math
from typing import Any

from pipeguard_backend.config import DetectionConfig
from pipeguard_backend.db.repository import Repository


class BaselineLearner:
    """Maintain robust running statistics for each node/operating-state bucket."""

    def __init__(self, repository: Repository, config: DetectionConfig) -> None:
        """Store dependencies."""
        self.repository = repository
        self.config = config

    def state_key(
        self,
        operating_state: Any,
    ) -> str:
        """Quantize the operating state into a bucket key."""
        buckets = self.config.state_buckets
        values = (
            operating_state.flow_m3h,
            operating_state.pressure_kpa,
            operating_state.pump_speed_rpm,
        )
        steps = (
            buckets.get("flow_m3h", 100.0),
            buckets.get("pressure_kpa", 250.0),
            buckets.get("pump_speed_rpm", 100.0),
        )
        return ":".join(str(math.floor(v / step)) for v, step in zip(values, steps))

    def get(self, node_id: str, state_key: str) -> dict[str, Any] | None:
        """Read a baseline from persistence."""
        return self.repository.get_baseline(node_id, state_key)

    def update(
        self, node_id: str, state_key: str, features: Any, timestamp: str = ""
    ) -> dict[str, Any]:
        """Incrementally update the baseline with a new normal-ish sample."""
        current = self.get(node_id, state_key) or self._empty()
        count = int(current.get("count", 0)) + 1
        updated: dict[str, Any] = {"count": count, "updated_at": timestamp}
        for name, value in (
            ("velocity", features.velocity_rms_mm_s),
            ("kurtosis", features.kurtosis),
            ("crest", features.crest_factor),
        ):
            mean = float(current.get(f"{name}_mean", 0.0))
            m2 = float(current.get(f"{name}_m2", 0.0))
            delta = float(value) - mean
            mean += delta / count
            m2 += delta * (float(value) - mean)
            updated[f"{name}_mean"] = mean
            updated[f"{name}_m2"] = m2
            updated[f"{name}_std"] = math.sqrt(m2 / max(count - 1, 1))
        band_mean = dict(current.get("band_mean", {}))
        band_m2 = dict(current.get("band_m2", {}))
        for name, value in features.band_energies.items():
            old_mean = float(band_mean.get(name, 0.0))
            delta = float(value) - old_mean
            new_mean = old_mean + delta / count
            band_mean[name] = new_mean
            band_m2[name] = float(band_m2.get(name, 0.0)) + delta * (float(value) - new_mean)
        updated["band_mean"] = band_mean
        updated["band_m2"] = band_m2
        updated["band_std"] = {
            name: math.sqrt(float(m2) / max(count - 1, 1)) for name, m2 in band_m2.items()
        }
        self.repository.save_baseline(node_id, state_key, updated, count)
        return updated

    @staticmethod
    def _empty() -> dict[str, Any]:
        """Return an empty baseline structure."""
        return {
            "count": 0,
            "velocity_mean": 0.0,
            "velocity_m2": 0.0,
            "velocity_std": 0.0,
            "kurtosis_mean": 0.0,
            "kurtosis_m2": 0.0,
            "kurtosis_std": 0.0,
            "crest_mean": 0.0,
            "crest_m2": 0.0,
            "crest_std": 0.0,
            "band_mean": {},
            "band_m2": {},
            "band_std": {},
        }

    @staticmethod
    def zscore(value: float, mean: float, std: float) -> float:
        """Return a normalized deviation, robust to tiny standard deviations."""
        return abs(float(value) - mean) / max(std, 1e-3)
