"""Database session helpers and the repository used by backend services."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pipeguard_backend.db.models import (
    ActionRow,
    AlarmRow,
    Base,
    BaselineRow,
    DetectionRow,
    DiagnosisRow,
    FeatureRow,
    IncidentRow,
)
from pipeguard_backend.schemas import (
    ActionAudit,
    ActionMode,
    ActionResult,
    AlarmRecord,
    Cause,
    DetectionResult,
    Diagnosis,
    FeatureMessage,
    GateResult,
    IncidentRecord,
)


def create_database(url: str) -> tuple[Engine, sessionmaker[Session]]:
    """Create an engine/session factory (SQLite in-memory supported for tests)."""
    if url.startswith("sqlite"):
        engine = create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        # In-memory/file SQLite are used by tests, the demo and local runs.
        # Production PostgreSQL tables are created by infra/db/init.sql.
        Base.metadata.create_all(engine)
    else:
        engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


class Repository:
    """Persistence operations used by the backend services."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Store the session factory."""
        self.session_factory = session_factory

    def _session(self) -> Iterator[Session]:
        """Yield a managed session."""
        with self.session_factory() as session:
            yield session

    def insert_feature(self, message: FeatureMessage) -> bool:
        """Insert a feature message; return False when it is a duplicate."""
        with self.session_factory() as session:
            row = FeatureRow(
                ts=message.timestamp,
                site=message.site,
                segment=message.segment,
                node_id=message.node_id,
                sequence=message.sequence,
                message_id=message.message_id,
                late=message.late,
                drift_corrected=message.drift_corrected,
                operating_state=message.operating_state.model_dump(),
                features=message.features.model_dump(mode="json"),
                health=message.health.model_dump(),
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True

    def recent_features(self, node_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent feature rows for a node, oldest first."""
        with self.session_factory() as session:
            rows = (
                session.query(FeatureRow)
                .filter(FeatureRow.node_id == node_id)
                .order_by(FeatureRow.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "features": row.features,
                    "operating_state": row.operating_state,
                    "ts": row.ts,
                    "health": row.health,
                }
                for row in reversed(rows)
            ]

    def get_baseline(self, node_id: str, state_key: str) -> dict[str, Any] | None:
        """Return a stored baseline for a node/state bucket."""
        with self.session_factory() as session:
            row = (
                session.query(BaselineRow)
                .filter(BaselineRow.node_id == node_id, BaselineRow.state_key == state_key)
                .first()
            )
            return dict(row.stats) if row else None

    def save_baseline(
        self, node_id: str, state_key: str, stats: dict[str, Any], sample_count: int
    ) -> None:
        """Upsert a learned baseline."""
        with self.session_factory() as session:
            row = (
                session.query(BaselineRow)
                .filter(BaselineRow.node_id == node_id, BaselineRow.state_key == state_key)
                .first()
            )
            if row is None:
                row = BaselineRow(node_id=node_id, state_key=state_key, stats=stats)
                session.add(row)
            row.stats = stats
            row.sample_count = sample_count
            row.version = (row.version or 1) + 1
            row.updated_at = stats.get("updated_at", "")
            session.commit()

    def insert_detection(self, result: DetectionResult, state_key: str) -> None:
        """Persist a detection result."""
        with self.session_factory() as session:
            session.add(
                DetectionRow(
                    ts=result.timestamp,
                    node_id=result.node_id,
                    score=result.score,
                    severity=result.severity.value,
                    layer_scores=result.layer_scores,
                    state_key=state_key,
                )
            )
            session.commit()

    def insert_diagnosis(self, diagnosis: Diagnosis) -> None:
        """Persist a diagnosis result."""
        with self.session_factory() as session:
            session.add(
                DiagnosisRow(
                    ts=diagnosis.timestamp,
                    node_id=diagnosis.node_id,
                    segment=diagnosis.segment,
                    cause=diagnosis.cause.value,
                    confidence=diagnosis.confidence,
                    evidence=[e.model_dump() for e in diagnosis.evidence],
                    severity=diagnosis.severity.value,
                    all_scores=diagnosis.all_scores,
                )
            )
            session.commit()

    def upsert_alarm(self, alarm: AlarmRecord) -> None:
        """Insert or update an alarm."""
        with self.session_factory() as session:
            row = session.get(AlarmRow, alarm.alarm_id)
            if row is None:
                row = AlarmRow(id=alarm.alarm_id)
                session.add(row)
            for field in (
                "node_id", "segment", "site", "priority", "state", "cause", "message",
                "created_at", "updated_at", "acked_by", "acked_at", "cleared_at",
                "shelved_until", "escalation_count",
            ):
                value = getattr(alarm, field)
                setattr(row, field, value.value if hasattr(value, "value") else value)
            session.commit()

    @staticmethod
    def _alarm_from_row(row: AlarmRow) -> AlarmRecord:
        """Map a persisted alarm row to its Pydantic record."""
        values = {c.name: getattr(row, c.name) for c in AlarmRow.__table__.columns}
        values["alarm_id"] = values.pop("id")
        return AlarmRecord.model_validate(values)

    def get_alarm(self, alarm_id: str) -> AlarmRecord | None:
        """Read an alarm by ID."""
        with self.session_factory() as session:
            row = session.get(AlarmRow, alarm_id)
            return self._alarm_from_row(row) if row else None

    def list_alarms(self, limit: int = 100) -> list[AlarmRecord]:
        """List alarms, newest first."""
        with self.session_factory() as session:
            rows = session.query(AlarmRow).order_by(AlarmRow.created_at.desc()).limit(limit).all()
            return [self._alarm_from_row(row) for row in rows]

    def list_diagnoses(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recent diagnosis rows as dictionaries."""
        with self.session_factory() as session:
            rows = session.query(DiagnosisRow).order_by(DiagnosisRow.id.desc()).limit(limit).all()
            return [
                {
                    "ts": row.ts,
                    "node_id": row.node_id,
                    "segment": row.segment,
                    "cause": row.cause,
                    "confidence": row.confidence,
                    "evidence": row.evidence,
                    "severity": row.severity,
                    "all_scores": row.all_scores,
                }
                for row in rows
            ]

    def insert_action(self, audit: ActionAudit) -> None:
        """Append an immutable audit record."""
        with self.session_factory() as session:
            session.add(
                ActionRow(
                    id=audit.action_id,
                    ts=audit.timestamp,
                    node_id=audit.node_id,
                    segment=audit.segment,
                    cause=audit.cause.value,
                    mode=audit.mode.value,
                    action_type=audit.action_type,
                    target=audit.target,
                    before=audit.before,
                    after=audit.after,
                    result=audit.result.value,
                    reason=audit.reason,
                    operator=audit.operator,
                    gate_results=[g.model_dump() for g in audit.gate_results],
                    rollback_of=audit.rollback_of,
                )
            )
            session.commit()

    def list_actions(self, limit: int = 100) -> list[ActionAudit]:
        """List action audit records, newest first."""
        with self.session_factory() as session:
            rows = session.query(ActionRow).order_by(ActionRow.id.desc()).limit(limit).all()
            return [
                ActionAudit(
                    action_id=row.id,
                    timestamp=row.ts,
                    node_id=row.node_id,
                    segment=row.segment,
                    cause=Cause(row.cause),
                    mode=ActionMode(row.mode),
                    action_type=row.action_type,
                    target=row.target,
                    before=row.before,
                    after=row.after,
                    result=ActionResult(row.result),
                    reason=row.reason,
                    operator=row.operator,
                    gate_results=[GateResult(**g) for g in row.gate_results],
                    rollback_of=row.rollback_of,
                )
                for row in rows
            ]

    def insert_incident(self, incident: IncidentRecord) -> None:
        """Persist an incident report."""
        with self.session_factory() as session:
            session.add(
                IncidentRow(
                    id=incident.incident_id,
                    created_at=incident.created_at,
                    site=incident.site,
                    segment=incident.segment,
                    cause=incident.cause.value,
                    severity=incident.severity.value,
                    payload=incident.model_dump(mode="json"),
                )
            )
            session.commit()

    def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Read an incident report."""
        with self.session_factory() as session:
            row = session.get(IncidentRow, incident_id)
            return IncidentRecord.model_validate(row.payload) if row else None
