"""YAML-backed configuration. All thresholds and policies are config-as-code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from pipeguard_backend.schemas import ActionMode, Cause

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class SystemConfig(BaseModel):
    """Global system settings."""

    site: str = "gulf-north"
    segment: str = "seg-12"
    default_mode: ActionMode = ActionMode.ADVISORY
    global_kill_switch: bool = False
    auto_segments: list[str] = Field(default_factory=list)
    max_late_seconds: float = 10.0
    max_clock_skew_ms: float = 5000.0
    device_keys: dict[str, str] = Field(default_factory=dict)


class IngestionConfig(BaseModel):
    """Ingestion reliability settings."""

    expected_interval_s: float = 0.5
    missing_after_intervals: int = 4
    duplicate_cache_size: int = 5000


class DetectionConfig(BaseModel):
    """Layered detection tuning."""

    warmup_samples: int = 12
    velocity_zones_mm_s: dict[str, float] = Field(
        default_factory=lambda: {"A": 2.8, "B": 7.1, "C": 11.0}
    )
    severity_weights: dict[str, float] = Field(
        default_factory=lambda: {"threshold": 0.35, "band": 0.25, "ml": 0.25, "trend": 0.15}
    )
    debounce: dict[str, float] = Field(default_factory=lambda: {"n_of_m": 3, "window": 5})
    hysteresis: dict[str, float] = Field(default_factory=lambda: {"enter": 0.45, "clear": 0.3})
    severity_levels: dict[str, float] = Field(
        default_factory=lambda: {"warning": 0.55, "critical": 0.8}
    )
    persistence_s: float = 1.5
    band_reference: dict[str, float] = Field(default_factory=dict)
    natural_frequencies_hz: list[float] = Field(default_factory=list)
    state_buckets: dict[str, float] = Field(default_factory=dict)
    trend_window: int = 6
    trend_alert_slope: float = 0.12
    ml_contamination: float = 0.05


class VerificationSpec(BaseModel):
    """Post-action verification settings."""

    timeout_s: int = 20
    min_improvement_pct: float = 10.0
    rollback_on_timeout: bool = True


class ActionSpec(BaseModel):
    """Action definition for one diagnosis cause."""

    type: str
    target: str = ""
    protocol: str = "opcua"
    direction: str = "decrease"
    max_step: float = 0.0
    min: float = 0.0
    max: float = 0.0
    step_per_severity: float = 0.0
    rate_limit_per_min: int = 1
    cooldown_s: int = 60
    skip_bands_hz: list[list[float]] = Field(default_factory=list)
    operating_envelope: dict[str, list[float]] = Field(default_factory=dict)
    description: str = ""


class Policy(BaseModel):
    """Automation policy for one cause."""

    default_mode: ActionMode = ActionMode.ADVISORY
    auto_segments: list[str] = Field(default_factory=list)
    action: ActionSpec
    verification: VerificationSpec = Field(default_factory=VerificationSpec)
    notifications: list[str] = Field(default_factory=lambda: ["dashboard"])


class PoliciesConfig(BaseModel):
    """All cause policies plus the SIS/ESD deny-list."""

    policies: dict[Cause, Policy] = Field(default_factory=dict)
    deny_tags: list[str] = Field(default_factory=list)


class NotificationConfig(BaseModel):
    """Notification channels and escalation timers."""

    channels: list[dict[str, Any]] = Field(default_factory=list)
    escalation: dict[str, float] = Field(
        default_factory=lambda: {"unack_seconds": 60, "repeat_seconds": 120, "max_repeats": 3}
    )


class Config(BaseModel):
    """Complete PipeGuard configuration."""

    system: SystemConfig = Field(default_factory=SystemConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file into a dictionary."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"configuration file must contain a mapping: {path}")
    return data


def load_config(config_dir: Path | None = None) -> Config:
    """Load and merge all configuration files."""
    directory = config_dir or DEFAULT_CONFIG_DIR
    merged = _read_yaml(directory / "default.yaml")
    policies = _read_yaml(directory / "policies.yaml")
    notifications = _read_yaml(directory / "notifications.yaml")
    merged["policies"] = {
        "policies": policies.get("policies", {}),
        "deny_tags": policies.get("deny_tags", []),
    }
    merged["notifications"] = notifications
    return Config.model_validate(merged)
