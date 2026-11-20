"""Optional OPC UA server exposing simulated PLC tags."""

from __future__ import annotations

import asyncio
from typing import Any

from plc_sim.device import REGISTER_MAP, SimulatedPLC


async def run_opcua_server(
    device: SimulatedPLC,
    endpoint: str = "opc.tcp://0.0.0.0:4840",
    namespace: str = "PipeGuard",
) -> None:
    """Serve device tags over OPC UA until cancelled."""
    try:
        from asyncua import Server
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("asyncua is required for the OPC UA server") from exc

    server = Server()
    server.endpoint = endpoint
    await server.init()
    index = await server.register_namespace(namespace)
    objects = await server.get_objects_node()
    folder = await objects.add_folder(index, "PipeGuard")
    variables: dict[str, Any] = {}
    for tag in REGISTER_MAP:
        variable = await folder.add_variable(index, tag, device.read(tag))
        await variable.set_writable()
        variables[tag] = variable
    async with server:
        while True:
            for tag, variable in variables.items():
                try:
                    requested = float(await variable.read_value())
                    if tag in device.bounds and abs(requested - device.read(tag)) > 1e-9:
                        device.write(tag, requested)
                    await variable.write_value(device.read(tag))
                except (ValueError, RuntimeError):  # pragma: no cover - client races
                    continue
            await asyncio.sleep(0.2)
