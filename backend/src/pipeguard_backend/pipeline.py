"""End-to-end wiring: ingest -> detect -> diagnose -> decide -> act -> alarm."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeguard_backend.actuation.adapters import DeviceRegistry
from pipeguard_backend.actuation.controller import ActuationController
from pipeguard_backend.alarms.manager import AlarmManager
from pipeguard_backend.api.ws import ConnectionManager, manager as websocket_manager
from pipeguard_backend.config import Config, load_config
from pipeguard_backend.db.repository import Repository, create_database
from pipeguard_backend.detection.detector import Detector
from pipeguard_backend.diagnosis.classifier import DiagnosisEngine
from pipeguard_backend.ingest.service import IngestService
from pipeguard_backend.notifications import NotificationHub
from pipeguard_backend.reports import IncidentReporter
from pipeguard_backend.rules.engine import RuleEngine
from pipeguard_backend.schemas import Severity


@dataclass
class AppServices:
    """All long-lived backend services."""

    config: Config
    repository: Repository
    ingest: IngestService
    detector: Detector
    classifier: DiagnosisEngine
    engine: RuleEngine
    controller: ActuationController
    alarms: AlarmManager
    notifier: NotificationHub
    reporter: IncidentReporter
    registry: DeviceRegistry
    websockets: ConnectionManager


class Pipeline:
    """Process telemetry through every backend stage."""

    def __init__(
        self,
        config: Config | None = None,
        repository: Repository | None = None,
        registry: DeviceRegistry | None = None,
        report_dir: Path | None = None,
    ) -> None:
        """Build the service graph."""
        self.config = config or load_config()
        if repository is None:
            _, factory = create_database(self.config.database_url)
            repository = Repository(factory)
        self.repository = repository
        self.registry = registry or DeviceRegistry()
        self.websockets = websocket_manager
        self.notifier = NotificationHub(self.config.notifications, self.websockets)
        self.alarms = AlarmManager(repository, self.config, self.notifier.publish)
        self.detector = Detector(repository, self.config)
        self.classifier = DiagnosisEngine(self.config)
        self.engine = RuleEngine(self.config)
        self.controller = ActuationController(
            repository,
            self.registry,
            on_event=self.notifier.publish,
            get_velocity=self._latest_velocity,
        )
        self.reporter = IncidentReporter(repository, report_dir)
        self.ingest = IngestService(repository, self.config)

    def _latest_velocity(self, node_id: str) -> float:
        """Read the most recent velocity RMS for a node from persistence."""
        rows = self.repository.recent_features(node_id, 1)
        if not rows:
            return 0.0
        return float(rows[0]["features"].get("velocity_rms_mm_s", 0.0))

    async def _current_setpoint(self, protocol: str, target: str) -> float:
        """Read the current device setpoint for bounded step calculation."""
        try:
            return float(await self.registry.get(protocol).read(target))
        except (RuntimeError, OSError, ValueError):
            return 0.0

    async def handle_message(self, topic: str, payload: bytes) -> dict[str, Any] | None:
        """Process one raw MQTT payload end to end."""
        message = await self.ingest.handle_topic(topic, payload)
        if message is None:
            return None
        detection = self.detector.evaluate(message)
        if detection.severity is Severity.NORMAL:
            return {"type": "telemetry", "node_id": message.node_id, "score": detection.score}

        diagnosis = self.classifier.diagnose(
            message,
            detection,
            list(self.repository.recent_features(message.node_id, 40)),
            self.detector.baselines.get(message.node_id, detection.state_key),
        )
        self.repository.insert_diagnosis(diagnosis)
        await self.alarms.raise_alarm(diagnosis)

        policy = self.config.policies.policies.get(diagnosis.cause)
        current = 0.0
        if policy and policy.action.target:
            current = await self._current_setpoint(policy.action.protocol, policy.action.target)
        decision = self.engine.evaluate(
            diagnosis,
            message,
            current_value=current,
            sensor_healthy=message.health.sampling_ok,
            message_age_s=detection.score * 0.1,
        )
        audit = await self.controller.execute(decision)
        if decision.command is not None:
            self.engine.record_action(decision.command.target)
        return {
            "type": "diagnosis",
            "diagnosis": diagnosis.model_dump(mode="json"),
            "detection": detection.model_dump(mode="json"),
            "decision_mode": decision.mode.value,
            "recommendation": decision.recommendation,
            "action": audit.model_dump(mode="json"),
        }

    def services(self) -> AppServices:
        """Return the service graph for the API layer."""
        return AppServices(
            config=self.config,
            repository=self.repository,
            ingest=self.ingest,
            detector=self.detector,
            classifier=self.classifier,
            engine=self.engine,
            controller=self.controller,
            alarms=self.alarms,
            notifier=self.notifier,
            reporter=self.reporter,
            registry=self.registry,
            websockets=self.websockets,
        )

    @property
    def simulated_plc(self) -> Any:
        """Expose the simulated PLC when the simulator adapter is in use."""
        adapter = self.registry.get("simulated")
        return getattr(adapter, "plc", None)
