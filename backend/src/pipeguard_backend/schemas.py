"""Shared Pydantic schemas for messages, detection, diagnosis and actions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Detection/diagnosis severity."""

    NORMAL = "normal"
    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmPriority(str, Enum):
    """ISA-18.2-style alarm priorities."""

    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmState(str, Enum):
    """Alarm lifecycle states."""

    ACTIVE = "ACTIVE"
    ACKED = "ACKED"
    CLEARED = "CLEARED"
    CLOSED = "CLOSED"
    SHELVED = "SHELVED"
    SUPPRESSED = "SUPPRESSED"


class ActionMode(str, Enum):
    """Per-rule automation mode."""

    ADVISORY = "advisory"
    AUTO = "auto"


class Cause(str, Enum):
    """Diagnosis classes."""

    NORMAL = "normal"
    CAVITATION = "cavitation"
    RESONANCE = "resonance"
    WATER_HAMMER = "water_hammer"
    LOOSE_SUPPORT = "loose_support"
    LEAK = "leak"
    IMBALANCE = "imbalance"
    SENSOR_FAULT = "sensor_fault"


class ActionResult(str, Enum):
    """Outcome of an actuation attempt."""

    EXECUTED = "executed"
    BLOCKED = "blocked"
    RECOMMENDED = "recommended"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    VERIFIED = "verified"


class OperatingState(BaseModel):
    """Process conditions at the time of measurement."""

    flow_m3h: float = 820.0
    pressure_kpa: float = 3450.0
    pump_speed_rpm: float = 2950.0
    valve_position_pct: float = 100.0


class FFTPeak(BaseModel):
    """Dominant spectral peak."""

    hz: float
    amplitude_mps2: float


class Features(BaseModel):
    """Feature vector published by a sensor node."""

    sample_rate_hz: int
    window_seconds: float
    accel_rms_mps2: dict[str, float] = Field(default_factory=dict)
    velocity_rms_mm_s: float = 0.0
    peak_mps2: float = 0.0
    crest_factor: float = 0.0
    kurtosis: float = 0.0
    band_energies: dict[str, float] = Field(default_factory=dict)
    fft_peaks: list[FFTPeak] = Field(default_factory=list)


class NodeHealth(BaseModel):
    """Node health block."""

    battery_pct: float = 100.0
    temp_c: float = 20.0
    mem_free_kb: int = 0
    sampling_ok: bool = True
    drift_ppm: float = 0.0
    clock_skew_ms: int = 0


class FeatureMessage(BaseModel):
    """A signed feature telemetry message."""

    schema_version: str
    message_id: str
    node_id: str
    site: str
    segment: str
    timestamp: str
    sequence: int
    operating_state: OperatingState
    features: Features
    health: NodeHealth
    signature: str = ""
    late: bool = False
    drift_corrected: bool = False


class StatusMessage(BaseModel):
    """Retained node status / LWT message."""

    node_id: str
    site: str
    segment: str
    online: bool
    reason: str = ""
    timestamp: str = ""
    signature: str = ""


class DetectionResult(BaseModel):
    """Output of the layered detector."""

    node_id: str
    timestamp: str
    score: float
    severity: Severity
    layer_scores: dict[str, float] = Field(default_factory=dict)
    state_key: str = ""
    debounce_count: int = 0


class EvidenceItem(BaseModel):
    """A single piece of diagnostic evidence."""

    feature: str
    observed: float
    expected: float
    weight: float
    detail: str = ""


class Diagnosis(BaseModel):
    """Probable cause with confidence and evidence."""

    node_id: str
    segment: str
    site: str
    timestamp: str
    cause: Cause
    confidence: float
    evidence: list[EvidenceItem] = Field(default_factory=list)
    recommended_action: str = ""
    severity: Severity = Severity.NORMAL
    location_estimate: dict[str, Any] | None = None
    all_scores: dict[str, float] = Field(default_factory=dict)


class GateResult(BaseModel):
    """Result of one safety gate."""

    gate: str
    allowed: bool
    reason: str = ""


class ActionCommand(BaseModel):
    """A bounded command ready for a device adapter."""

    cause: Cause
    mode: ActionMode
    action_type: str
    target: str
    value: float
    previous_value: float
    segment: str
    node_id: str
    reason: str
    gates: list[GateResult] = Field(default_factory=list)
    verification_timeout_s: int = 0
    min_improvement_pct: float = 0.0
    protocol: str = "opcua"


class ActionAudit(BaseModel):
    """Immutable audit record for every actuation attempt."""

    action_id: str
    timestamp: str
    node_id: str
    segment: str
    cause: Cause
    mode: ActionMode
    action_type: str
    target: str
    before: float | None
    after: float | None
    result: ActionResult
    reason: str
    operator: str = "system"
    gate_results: list[GateResult] = Field(default_factory=list)
    rollback_of: str | None = None


class AlarmRecord(BaseModel):
    """Alarm record with ISA-18.2-style lifecycle."""

    alarm_id: str
    node_id: str
    segment: str
    site: str
    priority: AlarmPriority
    state: AlarmState
    cause: Cause
    message: str
    created_at: str
    updated_at: str
    acked_by: str | None = None
    acked_at: str | None = None
    cleared_at: str | None = None
    shelved_until: str | None = None
    escalation_count: int = 0


class IncidentRecord(BaseModel):
    """Incident report payload."""

    incident_id: str
    created_at: str
    site: str
    segment: str
    cause: Cause
    severity: Severity
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    diagnoses: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    alarms: list[dict[str, Any]] = Field(default_factory=list)
    spectrum_snapshot: dict[str, Any] = Field(default_factory=dict)
    outcome: str = ""
