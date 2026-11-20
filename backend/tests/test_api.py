"""Tests for REST authentication, RBAC and bounded manual control."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pipeguard_backend.actuation.adapters import DeviceRegistry
from pipeguard_backend.api.app import create_app
from pipeguard_backend.config import Config
from pipeguard_backend.db.repository import Repository
from pipeguard_backend.pipeline import Pipeline
from pipeguard_backend.schemas import Cause


@pytest.fixture
def app(config: Config, repository: Repository) -> FastAPI:
    """Build an isolated FastAPI application."""
    config.policies.policies[Cause.CAVITATION].action.protocol = "simulated"
    pipeline = Pipeline(config, repository=repository, registry=DeviceRegistry())
    application = create_app(pipeline.services())
    application.state.pipeline = pipeline
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Return an ASGI test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


async def token(client: AsyncClient, role: str) -> str:
    """Obtain a demo JWT for a role."""
    response = await client.post(
        "/api/auth/token", json={"username": role, "password": role}
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


async def test_health_requires_authentication(client: AsyncClient) -> None:
    """Protected endpoints reject anonymous callers."""
    assert (await client.get("/api/health")).status_code == 401
    viewer = await token(client, "viewer")
    response = await client.get("/api/health", headers={"Authorization": f"Bearer {viewer}"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_role_hierarchy_for_kill_switch(client: AsyncClient, app: FastAPI) -> None:
    """Only admins may engage the kill switch."""
    viewer = await token(client, "viewer")
    denied = await client.post(
        "/api/kill-switch", json={"active": True}, headers={"Authorization": f"Bearer {viewer}"}
    )
    assert denied.status_code == 403

    admin = await token(client, "admin")
    allowed = await client.post(
        "/api/kill-switch", json={"active": True}, headers={"Authorization": f"Bearer {admin}"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["kill_switch"] is True
    assert app.state.pipeline.engine.kill_switch is True


async def test_manual_control_enforces_bounds_and_deny_list(client: AsyncClient) -> None:
    """Manual setpoint changes are bounded and never touch SIS/ESD tags."""
    engineer = await token(client, "engineer")
    headers = {"Authorization": f"Bearer {engineer}"}
    accepted = await client.post(
        "/api/manual-control",
        json={"target": "vfd_speed_rpm", "value": 2830.0, "reason": "test"},
        headers=headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["result"] == "executed"

    out_of_bounds = await client.post(
        "/api/manual-control",
        json={"target": "vfd_speed_rpm", "value": 100.0, "reason": "test"},
        headers=headers,
    )
    assert out_of_bounds.status_code == 400

    denied = await client.post(
        "/api/manual-control",
        json={"target": "sis_esd_trip", "value": 2000.0, "reason": "test"},
        headers=headers,
    )
    assert denied.status_code == 403


async def test_action_log_is_auditable(client: AsyncClient) -> None:
    """Manual commands appear in the action audit log."""
    engineer = await token(client, "engineer")
    headers = {"Authorization": f"Bearer {engineer}"}
    await client.post(
        "/api/manual-control",
        json={"target": "vfd_speed_rpm", "value": 2830.0, "reason": "logged"},
        headers=headers,
    )
    viewer = await token(client, "viewer")
    response = await client.get("/api/actions", headers={"Authorization": f"Bearer {viewer}"})
    assert response.status_code == 200
    assert any(action["reason"] == "logged" for action in response.json())
