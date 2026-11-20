"""Telemetry ingestion: signature verification, dedupe, lateness and drift."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.schemas import FeatureMessage, StatusMessage
from pipeguard_backend.security import verify_hmac


class IngestService:
    """Normalize and persist incoming node messages."""

    def __init__(self, repository: Repository, config: Config) -> None:
        """Initialize dedupe tracks from configuration."""
        self.repository = repository
        self.config = config
        self.seen: deque[tuple[str, int]] = deque(maxlen=config.ingestion.duplicate_cache_size)
        self.last_sequence: dict[str, int] = {}
        self.node_status: dict[str, dict[str, Any]] = {}

    async def handle_topic(self, topic: str, payload: bytes) -> FeatureMessage | None:
        """Parse a message from an MQTT topic and persist it when valid."""
        try:
            data: dict[str, Any] = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        if "online" in data:
            self._handle_status(data)
            return None
        return await self.handle_feature(data)

    def _handle_status(self, data: dict[str, Any]) -> None:
        """Process a retained status/LWT message."""
        key = data.get("node_id", "")
        if not key:
            return
        device_key = self.config.system.device_keys.get(key, "")
        if device_key and not verify_hmac(data, device_key):
            return
        status = StatusMessage.model_validate(data)
        self.node_status[status.node_id] = status.model_dump()

    async def handle_feature(self, data: dict[str, Any]) -> FeatureMessage | None:
        """Validate, normalize and store a feature message."""
        node_id = str(data.get("node_id", ""))
        device_key = self.config.system.device_keys.get(node_id, "")
        if not device_key or not verify_hmac(data, device_key):
            return None
        try:
            message = FeatureMessage.model_validate(data)
        except ValueError:
            return None

        identity = (message.node_id, message.sequence)
        if identity in self.seen:
            return None
        last = self.last_sequence.get(message.node_id, -1)
        if message.sequence <= last:
            return None

        message.late = self._is_late(message)
        message.drift_corrected = message.health.drift_ppm > 20.0
        if not self.repository.insert_feature(message):
            return None
        self.seen.append(identity)
        self.last_sequence[message.node_id] = message.sequence
        return message

    def _is_late(self, message: FeatureMessage) -> bool:
        """Flag messages whose ISO timestamp is older than the lateness budget."""
        try:
            parsed = datetime.fromisoformat(message.timestamp)
        except ValueError:
            return False
        age = time.time() - parsed.timestamp()
        return 0 < age > self.config.system.max_late_seconds

    def node_online(self, node_id: str) -> bool:
        """Return whether a node's LWT status is online (unknown = offline)."""
        status = self.node_status.get(node_id)
        return bool(status and status.get("online"))


class MqttBridge:
    """Bridge paho-mqtt callbacks into an asyncio queue."""

    def __init__(
        self,
        service: IngestService,
        broker: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "pipeguard/#",
        username: str = "",
        password: str = "",
        handler: Callable[[str, bytes], Awaitable[Any]] | None = None,
    ) -> None:
        """Initialize the bridge without connecting."""
        self.service = service
        self.broker = broker
        self.port = port
        self.topic_prefix = topic_prefix
        self.username = username
        self.password = password
        self.handler = handler or service.handle_topic
        self.queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self.client: Any | None = None

    def on_message(self, client: Any, userdata: Any, message: Any) -> None:
        """paho callback: enqueue an incoming message."""
        self.queue.put_nowait((message.topic, message.payload))

    def start(self) -> None:
        """Connect and subscribe (blocking network setup)."""
        import paho.mqtt.client as mqtt  # imported lazily for testability

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
            client_id="pipeguard-backend",
        )
        if self.username:
            client.username_pw_set(self.username, self.password)
        client.on_message = self.on_message
        last_error: OSError | None = None
        for attempt in range(10):
            try:
                client.connect(self.broker, self.port, keepalive=60)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.5)
        if last_error is not None:
            raise last_error
        client.subscribe(self.topic_prefix, qos=1)
        client.loop_start()
        self.client = client

    def stop(self) -> None:
        """Disconnect the MQTT client."""
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None

    async def run(self) -> None:
        """Consume queued messages until cancelled."""
        while True:
            topic, payload = await self.queue.get()
            await self.handler(topic, payload)
