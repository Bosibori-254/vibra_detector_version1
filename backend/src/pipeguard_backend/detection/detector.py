"""Layered detector with debounce, hysteresis and persistence timers."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.detection.baseline import BaselineLearner
from pipeguard_backend.detection.layers import (
    MLAnomalyLayer,
    band_layer,
    threshold_layer,
    trend_layer,
)
from pipeguard_backend.schemas import DetectionResult, FeatureMessage, Severity


@dataclass
class NodeDetectorState:
    """Per-node detection state."""

    history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=100))
    recent_scores: deque[float] = field(default_factory=deque)
    active: bool = False
    below_since: float | None = None


class Detector:
    """Combine layered scores and emit debounced severity changes."""

    def __init__(
        self,
        repository: Repository,
        config: Config,
        clock: Any = time.monotonic,
    ) -> None:
        """Initialize baselines, ML layer and per-node state."""
        self.config = config
        self.repository = repository
        self.clock = clock
        self.baselines = BaselineLearner(repository, config.detection)
        self.ml = MLAnomalyLayer(config.detection)
        self.states: dict[str, NodeDetectorState] = {}

    def _state(self, node_id: str) -> NodeDetectorState:
        """Return (and lazily create) a node's detector state."""
        if node_id not in self.states:
            n_of_m = max(int(self.config.detection.debounce.get("n_of_m", 3)), 1)
            self.states[node_id] = NodeDetectorState(
                recent_scores=deque(maxlen=n_of_m)
            )
        return self.states[node_id]

    def evaluate(self, message: FeatureMessage) -> DetectionResult:
        """Evaluate one feature message and persist the resulting score."""
        cfg = self.config.detection
        state = self._state(message.node_id)
        state_key = self.baselines.state_key(message.operating_state)
        baseline = self.baselines.get(message.node_id, state_key)

        layers = {
            "threshold": threshold_layer(message.features.velocity_rms_mm_s, cfg),
            "band": band_layer(message.features.band_energies, cfg, baseline),
            "ml": self.ml.score(message.features, baseline, list(state.history)),
            "trend": trend_layer(list(state.history), cfg),
        }
        weights = cfg.severity_weights
        total_weight = sum(weights.get(name, 0.0) for name in layers) or 1.0
        score = sum(layers[name] * weights.get(name, 0.0) for name in layers) / total_weight

        state.recent_scores.append(score)
        enter = float(cfg.hysteresis.get("enter", 0.45))
        clear = float(cfg.hysteresis.get("clear", 0.3))
        n_of_m = max(int(cfg.debounce.get("n_of_m", 3)), 1)
        hits = sum(1 for value in state.recent_scores if value >= enter)
        now = float(self.clock())
        if hits >= n_of_m:
            state.active = True
            state.below_since = None
        elif score <= clear:
            if state.below_since is None:
                state.below_since = now
            if now - state.below_since >= cfg.persistence_s:
                state.active = False
        else:
            state.below_since = None

        severity = Severity.NORMAL
        if state.active:
            levels = cfg.severity_levels
            if score >= levels.get("critical", 0.8):
                severity = Severity.CRITICAL
            elif score >= levels.get("warning", 0.55):
                severity = Severity.WARNING
            else:
                severity = Severity.ADVISORY

        result = DetectionResult(
            node_id=message.node_id,
            timestamp=message.timestamp,
            score=round(score, 6),
            severity=severity,
            layer_scores={name: round(value, 6) for name, value in layers.items()},
            state_key=state_key,
            debounce_count=hits,
        )
        state.history.append(
            {
                "features": message.features.model_dump(mode="json"),
                "operating_state": message.operating_state.model_dump(),
                "ts": message.timestamp,
            }
        )
        if severity is Severity.NORMAL or len(state.history) <= cfg.warmup_samples:
            self.baselines.update(
                message.node_id, state_key, message.features, message.timestamp
            )
        self.repository.insert_detection(result, state_key)
        return result
