"""Automatic incident report generation (JSON, Markdown, optional PDF)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeguard_backend.db.repository import Repository
from pipeguard_backend.schemas import Cause, IncidentRecord, Severity

DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[3] / "docs" / "reports" / "incidents"


def _now() -> str:
    """Return a UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class IncidentReporter:
    """Assemble timeline, spectra, diagnoses, actions and outcomes into a report."""

    def __init__(self, repository: Repository, output_dir: Path | None = None) -> None:
        """Store dependencies."""
        self.repository = repository
        self.output_dir = output_dir or DEFAULT_REPORT_DIR

    def generate(
        self,
        site: str,
        segment: str,
        cause: Cause,
        severity: Severity,
        spectrum_snapshot: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        """Create and persist a complete incident report."""
        diagnoses = self.repository.list_diagnoses(30)
        actions = [a.model_dump(mode="json") for a in self.repository.list_actions(50)]
        alarms = [a.model_dump(mode="json") for a in self.repository.list_alarms(50)]
        timeline = [
            {"ts": d["ts"], "event": "diagnosis", "detail": d["cause"]}
            for d in diagnoses
        ] + [
            {"ts": a["timestamp"], "event": "action", "detail": f"{a['action_type']}:{a['result']}"}
            for a in actions
        ] + [
            {"ts": a["created_at"], "event": "alarm", "detail": a["message"]}
            for a in alarms
        ]
        timeline.sort(key=lambda item: item["ts"])
        outcome = "in progress"
        for action in actions:
            if action["result"] == "verified":
                outcome = "vibration recovered after bounded action"
            elif action["result"] in {"rolled_back", "failed"}:
                outcome = "action rolled back; escalated to operator"
            elif action["result"] == "recommended":
                outcome = "advisory recommendation issued"
        incident = IncidentRecord(
            incident_id=str(uuid.uuid4()),
            created_at=_now(),
            site=site,
            segment=segment,
            cause=cause,
            severity=severity,
            timeline=timeline,
            diagnoses=diagnoses,
            actions=actions,
            alarms=alarms,
            spectrum_snapshot=spectrum_snapshot or {},
            outcome=outcome,
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = self.output_dir / f"incident-{incident.incident_id[:8]}"
        (stem.with_suffix(".json")).write_text(
            json.dumps(incident.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        (stem.with_suffix(".md")).write_text(self._markdown(incident), encoding="utf-8")
        self._pdf(incident, stem.with_suffix(".pdf"))
        self.repository.insert_incident(incident)
        return incident

    @staticmethod
    def _markdown(incident: IncidentRecord) -> str:
        """Render a human-readable Markdown report."""
        lines = [
            f"# Incident report {incident.incident_id}",
            "",
            f"- Created: {incident.created_at}",
            f"- Site / segment: {incident.site} / {incident.segment}",
            f"- Probable cause: {incident.cause.value}",
            f"- Severity: {incident.severity.value}",
            f"- Outcome: {incident.outcome}",
            "",
            "## Timeline",
            "",
        ]
        lines += [f"- **{item['ts']}** — {item['event']}: {item['detail']}" for item in incident.timeline]
        lines += ["", "## Diagnoses", ""]
        lines += [
            f"- {d['ts']}: {d['cause']} (confidence {d['confidence']:.2f})" for d in incident.diagnoses
        ]
        lines += ["", "## Actions", ""]
        lines += [
            f"- {a['timestamp']}: {a['action_type']} → {a['target']} — {a['result']} ({a['reason']})"
            for a in incident.actions
        ]
        lines += ["", "## Spectrum snapshot", "", "```json",
                  json.dumps(incident.spectrum_snapshot, indent=2), "```"]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _pdf(incident: IncidentRecord, path: Path) -> None:
        """Render a PDF when reportlab is available."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:  # pragma: no cover - optional dependency
            return
        pdf = canvas.Canvas(str(path), pagesize=letter)
        text = pdf.beginText(40, 750)
        for line in IncidentReporter._markdown(incident).splitlines()[:55]:
            text.textLine(line[:100])
        pdf.drawText(text)
        pdf.save()
