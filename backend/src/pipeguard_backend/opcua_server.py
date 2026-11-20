"""Optional OPC UA server exposing PipeGuard alarms and state to SCADA."""

from __future__ import annotations

import asyncio
from typing import Any

from pipeguard_backend.pipeline import AppServices


async def run_alarm_opcua_server(
    services: AppServices,
    endpoint: str = "opc.tcp://0.0.0.0:4841",
    namespace: str = "PipeGuardAlarms",
) -> None:
    """Serve alarm state over OPC UA until cancelled."""
    try:
        from asyncua import Server
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("asyncua is required for the alarm OPC UA server") from exc

    server = Server()
    server.endpoint = endpoint
    await server.init()
    index = await server.register_namespace(namespace)
    objects = await server.get_objects_node()
    alarms_folder = await objects.add_folder(index, "Alarms")
    variables: dict[str, Any] = {}
    while True:
        alarms = services.repository.list_alarms(50)
        for alarm in alarms:
            name = alarm.alarm_id.replace(":", "_")
            if name not in variables:
                variables[name] = await alarms_folder.add_variable(
                    index, name, f"{alarm.state}:{alarm.priority.value}"
                )
            await variables[name].write_value(f"{alarm.state}:{alarm.priority.value}")
        await asyncio.sleep(1.0)
