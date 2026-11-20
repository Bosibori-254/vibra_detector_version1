"""Tests for telemetry ingestion validation, dedupe and status handling."""

from __future__ import annotations

import json

from conftest import KEY, signed_message
from pipeguard_sim.messages import make_status_message, sign_message

from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.ingest.service import IngestService
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
