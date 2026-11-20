"""Tests for telemetry ingestion validation, dedupe and status handling."""

from __future__ import annotations

import json

<<<<<<< HEAD
import pytest
=======
>>>>>>> 39dc708905440b9b1693bfb8574ef57fdad29e0d
from conftest import KEY, signed_message
from pipeguard_sim.messages import make_status_message, sign_message

from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
<<<<<<< HEAD
from pipeguard_backend.ingest.service import IngestService, MqttBridge
=======
from pipeguard_backend.ingest.service import IngestService
>>>>>>> 39dc708905440b9b1693bfb8574ef57fdad29e0d
from pipeguard_backend.schemas import FeatureMessage

TOPIC = "pipeguard/gulf-north/seg-12/node-03/features"


async def test_valid_message_is_persisted(repository: Repository, config: Config) -> None:
    """A correctly signed feature message is accepted and stored."""
    service = IngestService(repository, config)
    payload = json.dumps(signed_message(sequence=0)).encode("utf-8")
    message = await service.handle_topic(TOPIC, payload)
    assert isinstance(message, FeatureMessage)
    assert len(repository.recent_features("node-03", 10)) == 1


async def test_duplicate_and_out_of_order_are_rejected(repository: Repository, config: Config) -> None:
    """Duplicate and older sequences are ignored."""
    service = IngestService(repository, config)
    payload0 = json.dumps(signed_message(sequence=0)).encode("utf-8")
    payload1 = json.dumps(signed_message(sequence=1)).encode("utf-8")
    assert await service.handle_topic(TOPIC, payload0) is not None
    assert await service.handle_topic(TOPIC, payload0) is None
    assert await service.handle_topic(TOPIC, payload1) is not None
    assert await service.handle_topic(TOPIC, payload0) is None


async def test_invalid_signature_is_rejected(repository: Repository, config: Config) -> None:
    """Messages signed with the wrong key never reach persistence."""
    service = IngestService(repository, config)
    tampered = signed_message(sequence=0, key="wrong-key")
    assert await service.handle_topic(TOPIC, json.dumps(tampered).encode()) is None
    assert repository.recent_features("node-03", 10) == []


async def test_unknown_node_is_rejected(repository: Repository, config: Config) -> None:
    """A node without a configured key cannot publish telemetry."""
    service = IngestService(repository, config)
    message = signed_message(sequence=0)
    message["node_id"] = "node-99"
    message = sign_message(message, KEY)
    assert await service.handle_topic(TOPIC, json.dumps(message).encode()) is None


async def test_status_message_updates_node_presence(repository: Repository, config: Config) -> None:
    """Retained status messages drive the node online/offline view."""
    service = IngestService(repository, config)
    status = make_status_message(
        site="gulf-north", segment="seg-12", node_id="node-03", online=True, signing_key=KEY
    )
    assert await service.handle_topic("pipeguard/status", json.dumps(status).encode()) is None
    assert service.node_online("node-03")
<<<<<<< HEAD


def test_mqtt_bridge_retries_transient_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broker that is not yet listening does not abort backend startup."""

    class FakeClient:
        attempts = 0
        subscribed = False

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Paho constructor stand-in."""

        def username_pw_set(self, username: str, password: str) -> None:
            """Credential stand-in."""

        def connect(self, broker: str, port: int, keepalive: int = 60) -> None:
            """Fail once, then connect."""
            type(self).attempts += 1
            if self.attempts == 1:
                raise OSError("broker not ready")

        def subscribe(self, topic: str, qos: int = 0) -> None:
            """Record subscription."""
            type(self).subscribed = True

        def loop_start(self) -> None:
            """Network-loop stand-in."""

        def loop_stop(self) -> None:
            """Network-loop stand-in."""

        def disconnect(self) -> None:
            """Disconnect stand-in."""

    monkeypatch.setattr("paho.mqtt.client.Client", FakeClient)
    monkeypatch.setattr("pipeguard_backend.ingest.service.time.sleep", lambda _: None)

    async def handler(topic: str, payload: bytes) -> None:
        """No-op message handler."""

    bridge = MqttBridge(None, broker="broker", handler=handler)  # type: ignore[arg-type]
    bridge.start()
    assert FakeClient.attempts == 2
    assert FakeClient.subscribed
    assert bridge.client is not None
    bridge.stop()
=======
>>>>>>> 39dc708905440b9b1693bfb8574ef57fdad29e0d
