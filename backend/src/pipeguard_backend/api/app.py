"""FastAPI REST API and WebSocket endpoint."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from pipeguard_backend.actuation.controller import _now
from pipeguard_backend.api.ws import manager as websocket_manager
from pipeguard_backend.pipeline import AppServices
from pipeguard_backend.schemas import ActionAudit, ActionMode, ActionResult, Cause, Severity
from pipeguard_backend.security import create_jwt, require_role

DEMO_USERS = {
    "viewer": ("viewer", "viewer"),
    "operator": ("operator", "operator"),
    "engineer": ("engineer", "engineer"),
    "admin": ("admin", "admin"),
}


class TokenRequest(BaseModel):
    """Username/password login request."""

    username: str
    password: str


class AckRequest(BaseModel):
    """Operator acknowledgement request."""

    operator: str = "operator"


class ShelveRequest(BaseModel):
    """Alarm shelving request."""

    seconds: int = 300


class KillSwitchRequest(BaseModel):
    """Kill switch command."""

    active: bool


class ManualControlRequest(BaseModel):
    """Bounded manual setpoint change."""

    target: str
    value: float
    reason: str


def create_app(services: AppServices) -> FastAPI:
    """Build the FastAPI application around the service graph."""
    app = FastAPI(title="PipeGuard API", version="0.1.0", docs_url="/docs")
    app.state.services = services
    secret = services.config.jwt_secret
    viewer = require_role("viewer", secret)
    operator = require_role("operator", secret)
    engineer = require_role("engineer", secret)
    admin = require_role("admin", secret)
    router = APIRouter(prefix="/api")

    @router.post("/auth/token")
    def token(request: TokenRequest) -> dict[str, str]:
        """Issue a demo JWT (replace with an identity provider in production)."""
        expected = DEMO_USERS.get(request.username)
        if expected is None or expected[1] != request.password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {
            "access_token": create_jwt(request.username, expected[0], secret),
            "token_type": "bearer",
        }

    @router.get("/health")
    def health(_: dict[str, Any] = Depends(viewer)) -> dict[str, Any]:
        """Return backend health."""
        return {"status": "ok", "service": "pipeguard-backend"}

    @router.get("/overview")
    def overview(_: dict[str, Any] = Depends(viewer)) -> dict[str, Any]:
        """Return segment status and device snapshot for the dashboard."""
        adapters = {
            name: adapter.describe() for name, adapter in services.registry.adapters.items()
        }
        return {
            "site": services.config.system.site,
            "segments": [
                {
                    "id": services.config.system.segment,
                    "status": "green",
                    "nodes": list(services.ingest.node_status),
                }
            ],
            "devices": adapters,
            "kill_switch": services.engine.kill_switch or services.config.system.global_kill_switch,
        }

    @router.get("/alarms")
    def alarms(_: dict[str, Any] = Depends(viewer)) -> list[dict[str, Any]]:
        """List current alarms."""
        return [a.model_dump(mode="json") for a in services.repository.list_alarms()]

    @router.post("/alarms/{alarm_id}/ack")
    async def acknowledge(
        alarm_id: str, request: AckRequest, _: dict[str, Any] = Depends(operator)
    ) -> dict[str, Any]:
        """Acknowledge an alarm."""
        alarm = await services.alarms.acknowledge(alarm_id, request.operator)
        if alarm is None:
            raise HTTPException(status_code=404, detail="Alarm not found")
        return alarm.model_dump(mode="json")

    @router.post("/alarms/{alarm_id}/shelve")
    async def shelve(
        alarm_id: str, request: ShelveRequest, _: dict[str, Any] = Depends(operator)
    ) -> dict[str, Any]:
        """Shelve an alarm temporarily."""
        alarm = await services.alarms.shelve(alarm_id, request.seconds)
        if alarm is None:
            raise HTTPException(status_code=404, detail="Alarm not found")
        return alarm.model_dump(mode="json")

    @router.post("/alarms/{alarm_id}/clear")
    async def clear(
        alarm_id: str, _: dict[str, Any] = Depends(operator)
    ) -> dict[str, Any]:
        """Clear an alarm."""
        alarm = await services.alarms.clear(alarm_id)
        if alarm is None:
            raise HTTPException(status_code=404, detail="Alarm not found")
        return alarm.model_dump(mode="json")

    @router.get("/actions")
    def actions(_: dict[str, Any] = Depends(viewer)) -> list[dict[str, Any]]:
        """List the action audit log."""
        return [a.model_dump(mode="json") for a in services.repository.list_actions()]

    @router.get("/incidents")
    def incidents(_: dict[str, Any] = Depends(viewer)) -> list[dict[str, Any]]:
        """List generated incident reports."""
        with services.repository.session_factory() as session:
            from pipeguard_backend.db.models import IncidentRow

            return [row.payload for row in session.query(IncidentRow).all()]

    @router.get("/incidents/{incident_id}")
    def incident(incident_id: str, _: dict[str, Any] = Depends(viewer)) -> dict[str, Any]:
        """Read one incident report."""
        record = services.repository.get_incident(incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return record.model_dump(mode="json")

    @router.post("/incidents/generate")
    def generate_incident(
        cause: Cause,
        severity: Severity = Severity.WARNING,
        site: str = "gulf-north",
        segment: str = "seg-12",
        _: dict[str, Any] = Depends(operator),
    ) -> dict[str, Any]:
        """Generate an incident report from recorded events."""
        report = services.reporter.generate(site, segment, cause, severity)
        return report.model_dump(mode="json")

    @router.post("/ingest")
    async def ingest(
        request: Request, message: dict[str, Any], _: dict[str, Any] = Depends(viewer)
    ) -> dict[str, Any]:
        """Inject one telemetry message through the full pipeline (demo/tests)."""
        import json

        pipeline = request.app.state.pipeline
        result = await pipeline.handle_message(
            "pipeguard/features", json.dumps(message).encode("utf-8")
        )
        return {"result": result}

    @router.post("/manual-control")
    async def manual_control(
        request: ManualControlRequest, claims: dict[str, Any] = Depends(engineer)
    ) -> dict[str, Any]:
        """Issue a bounded manual setpoint change (engineer role required)."""
        denied = [tag for tag in services.config.policies.deny_tags if tag in request.target.lower()]
        if denied:
            raise HTTPException(status_code=403, detail="SIS/ESD targets are never writable")
        spec = services.config.policies.policies[Cause.CAVITATION].action
        if not spec.min <= request.value <= spec.max:
            raise HTTPException(status_code=400, detail="target outside hard bounds")
        adapter = services.registry.get("simulated")
        before = await adapter.read(request.target)
        if abs(request.value - before) > spec.max_step:
            raise HTTPException(status_code=400, detail="step exceeds maximum")
        result = await adapter.write(request.target, request.value)
        audit = ActionAudit(
            action_id=str(uuid.uuid4()),
            timestamp=_now(),
            node_id="manual",
            segment=services.config.system.segment,
            cause=Cause.NORMAL,
            mode=ActionMode.ADVISORY,
            action_type="manual_setpoint",
            target=request.target,
            before=before,
            after=result.after,
            result=ActionResult.EXECUTED if result.accepted else ActionResult.FAILED,
            reason=request.reason,
            operator=str(claims.get("sub", "engineer")),
        )
        services.repository.insert_action(audit)
        return audit.model_dump(mode="json")

    @router.post("/kill-switch")
    def kill_switch(request: KillSwitchRequest, _: dict[str, Any] = Depends(admin)) -> dict[str, Any]:
        """Engage or release the global automation kill switch."""
        services.engine.set_kill_switch(request.active)
        return {"kill_switch": services.engine.kill_switch, "at": time.time()}

    app.include_router(router)

    @app.websocket("/ws/alerts")
    async def alerts(websocket: WebSocket) -> None:
        """Stream alarms and actions to the dashboard."""
        await websocket_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            websocket_manager.disconnect(websocket)

    return app
