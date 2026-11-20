"""Optional Modbus TCP server exposing simulated PLC holding registers."""

from __future__ import annotations

import asyncio
from typing import Any

from plc_sim.device import REGISTER_MAP, SimulatedPLC


async def run_modbus_server(device: SimulatedPLC, host: str = "0.0.0.0", port: int = 5020) -> None:
    """Serve device tags as Modbus holding registers until cancelled."""
    try:
        from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
        from pymodbus.server import StartAsyncTcpServer

        try:
            from pymodbus.datastore import ModbusSlaveContext as ModbusDeviceContext
        except ImportError:  # pymodbus >= 3.10 renamed the slave context
            from pymodbus.datastore import ModbusDeviceContext
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pymodbus is required for the Modbus server") from exc

    block = ModbusSequentialDataBlock(0, [0] * 500)
    slave = ModbusDeviceContext(hr=block)
    try:
        context: Any = ModbusServerContext(slaves=slave, single=True)
    except TypeError:  # pymodbus >= 3.10 renamed ``slaves`` to ``devices``
        context = ModbusServerContext(devices=slave, single=True)
    for tag, address in REGISTER_MAP.items():
        block.setValues(address, [int(device.read(tag) * 10)])

    async def synchronize() -> None:
        """Mirror device state into registers and accept external writes."""
        while True:
            for tag, address in REGISTER_MAP.items():
                requested = block.getValues(address, 1)[0] / 10.0
                if tag in device.bounds and abs(requested - device.read(tag)) > 0.05:
                    device.write(tag, requested)
                block.setValues(address, [int(device.read(tag) * 10)])
            await asyncio.sleep(0.2)

    updater = asyncio.create_task(synchronize())
    try:
        await StartAsyncTcpServer(context=context, address=(host, port))
    finally:
        updater.cancel()
