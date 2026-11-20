"""CLI entry point that starts both simulated field protocols."""

from __future__ import annotations

import argparse
import asyncio

from plc_sim.device import SimulatedPLC
from plc_sim.modbus_server import run_modbus_server
from plc_sim.opcua_server import run_opcua_server


def main() -> None:
    """Run the simulated PLC servers."""
    parser = argparse.ArgumentParser(description="PipeGuard simulated PLC/VFD/valve")
    parser.add_argument("--opcua-endpoint", default="opc.tcp://0.0.0.0:4840")
    parser.add_argument("--modbus-port", type=int, default=5020)
    args = parser.parse_args()

    device = SimulatedPLC()
    device.set_fault("normal", 0.0)

    async def serve() -> None:
        """Start both protocol servers concurrently."""
        await asyncio.gather(
            run_opcua_server(device, args.opcua_endpoint),
            run_modbus_server(device, port=args.modbus_port),
        )

    try:
        asyncio.run(serve())
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
