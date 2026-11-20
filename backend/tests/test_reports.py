"""Tests for incident report generation."""

from __future__ import annotations

from conftest import audit, diagnosis

from pipeguard_backend.alarms.manager import AlarmManager
from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.reports import IncidentReporter
from pipeguard_backend.schemas import ActionResult, Cause, Severity


async def test_incident_report_contains_timeline_and_outcome(
    repository: Repository, config: Config, tmp_path: object
) -> None:
    """A report assembles persisted events and writes JSON/Markdown files."""
    repository.insert_diagnosis(diagnosis())
    repository.insert_action(audit(ActionResult.VERIFIED))
    await AlarmManager(repository, config).raise_alarm(diagnosis())
    reporter = IncidentReporter(repository, tmp_path)  # type: ignore[arg-type]

    report = reporter.generate("gulf-north", "seg-12", Cause.CAVITATION, Severity.WARNING)
    assert report.cause is Cause.CAVITATION
    assert report.outcome == "vibration recovered after bounded action"
    assert any(item["event"] == "action" for item in report.timeline)
    assert (tmp_path / f"incident-{report.incident_id[:8]}.json").exists()  # type: ignore[operator]
    assert (tmp_path / f"incident-{report.incident_id[:8]}.md").exists()  # type: ignore[operator]
    assert repository.get_incident(report.incident_id) is not None


async def test_report_outcome_prioritizes_verified_over_later_recommendation(
    repository: Repository, config: Config, tmp_path: object
) -> None:
    """A later advisory entry must not mask a completed bounded recovery."""
    repository.insert_action(audit(ActionResult.VERIFIED, action_id="action-verified"))
    repository.insert_action(audit(ActionResult.RECOMMENDED, action_id="action-advice"))
    reporter = IncidentReporter(repository, tmp_path)  # type: ignore[arg-type]

    report = reporter.generate("gulf-north", "seg-12", Cause.CAVITATION, Severity.WARNING)
    assert report.outcome == "vibration recovered after bounded action"
