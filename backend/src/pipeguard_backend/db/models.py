"""SQLAlchemy ORM models mirroring the TimescaleDB schema in infra/db/init.sql."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base."""


class FeatureRow(Base):
    """One feature message."""

    __tablename__ = "feature_samples"
    __table_args__ = (UniqueConstraint("node_id", "sequence", name="uq_node_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(index=True)
    site: Mapped[str]
    segment: Mapped[str]
    node_id: Mapped[str] = mapped_column(index=True)
    sequence: Mapped[int]
    message_id: Mapped[str] = mapped_column(unique=True)
    late: Mapped[bool] = mapped_column(default=False)
    drift_corrected: Mapped[bool] = mapped_column(default=False)
    operating_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    features: Mapped[dict[str, Any]] = mapped_column(JSON)
    health: Mapped[dict[str, Any]] = mapped_column(JSON)


class BaselineRow(Base):
    """Learned baseline for a node and operating-state bucket."""

    __tablename__ = "baselines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[str]
    state_key: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON)
    sample_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[str]


class DetectionRow(Base):
    """Detection score and severity."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(index=True)
    node_id: Mapped[str]
    score: Mapped[float]
    severity: Mapped[str]
    layer_scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    state_key: Mapped[str] = mapped_column(default="")


class DiagnosisRow(Base):
    """Diagnosis result."""

    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(index=True)
    node_id: Mapped[str]
    segment: Mapped[str]
    cause: Mapped[str]
    confidence: Mapped[float]
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    severity: Mapped[str]
    all_scores: Mapped[dict[str, Any]] = mapped_column(JSON)


class AlarmRow(Base):
    """Alarm lifecycle record."""

    __tablename__ = "alarms"

    id: Mapped[str] = mapped_column(primary_key=True)
    node_id: Mapped[str]
    segment: Mapped[str]
    site: Mapped[str]
    priority: Mapped[str]
    state: Mapped[str]
    cause: Mapped[str]
    message: Mapped[str]
    created_at: Mapped[str]
    updated_at: Mapped[str]
    acked_by: Mapped[str | None] = mapped_column(nullable=True)
    acked_at: Mapped[str | None] = mapped_column(nullable=True)
    cleared_at: Mapped[str | None] = mapped_column(nullable=True)
    shelved_until: Mapped[str | None] = mapped_column(nullable=True)
    escalation_count: Mapped[int] = mapped_column(default=0)


class ActionRow(Base):
    """Immutable action audit record."""

    __tablename__ = "actions_audit"

    id: Mapped[str] = mapped_column(primary_key=True)
    ts: Mapped[str] = mapped_column(index=True)
    node_id: Mapped[str]
    segment: Mapped[str]
    cause: Mapped[str]
    mode: Mapped[str]
    action_type: Mapped[str]
    target: Mapped[str]
    before: Mapped[float | None] = mapped_column(nullable=True)
    after: Mapped[float | None] = mapped_column(nullable=True)
    result: Mapped[str]
    reason: Mapped[str]
    operator: Mapped[str] = mapped_column(default="system")
    gate_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    rollback_of: Mapped[str | None] = mapped_column(nullable=True)


class IncidentRow(Base):
    """Generated incident report."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[str]
    site: Mapped[str]
    segment: Mapped[str]
    cause: Mapped[str]
    severity: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
