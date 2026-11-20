"""Tests for the simulator command-line interface."""

from __future__ import annotations

import argparse

import pytest

from pipeguard_sim.cli import _publish_mqtt
from pipeguard_sim.scenario import SimulatorConfig


def test_mqtt_publish_retries_transient_broker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broker that is not ready yet does not abort the simulator."""

    connect_attempts: list[int] = []

    class FakeClient:
        attempts = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Paho constructor stand-in."""

        def username_pw_set(self, username: str, password: str) -> None:
            """Credential stand-in."""

        def connect(self, broker: str, port: int, keepalive: int = 60) -> None:
            """Fail once, then connect."""
            connect_attempts.append(port)
            type(self).attempts += 1
            if self.attempts == 1:
                raise OSError("broker not ready")

        def loop_start(self) -> None:
            """Network-loop stand-in."""

        def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None:
            """Publish stand-in."""

        def loop_stop(self) -> None:
            """Network-loop stand-in."""

        def disconnect(self) -> None:
            """Disconnect stand-in."""

    monkeypatch.setattr("paho.mqtt.client.Client", FakeClient)
    monkeypatch.setattr("pipeguard_sim.cli.time.sleep", lambda _: None)

    config = SimulatorConfig(duration_s=0.0, signing_key="device-secret")
    args = argparse.Namespace(broker="broker", port=1883, key="device-secret", pace=False)
    _publish_mqtt(config, args)

    assert connect_attempts == [1883, 1883]
