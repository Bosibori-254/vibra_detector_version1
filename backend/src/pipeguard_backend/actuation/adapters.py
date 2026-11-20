"""Interchangeable device adapters: in-process simulator, OPC UA and Modbus."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from plc_sim.device import SimulatedPLC


@dataclass(frozen=True)
class WriteOutcome:
    """Result of a device write."""

    accepted: bool
    before: float
    after: float
    reason: str = ""


class DeviceAdapter(ABC):
    """Common interface for all field device transports."""

    @abstractmethod
    async def read(self, tag: str) -> float:
        """Read a tag value."""

    @abstractmethod
    async def write(self, tag: str, value: float) -> WriteOutcome:
        """Write a setpoint value."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return device health/state for the dashboard."""


class SimulatedAdapter(DeviceAdapter):
    """Adapter over the in-process simulated PLC."""

    def __init__(self, plc: SimulatedPLC | None = None) -> None:
        """Wrap a simulated PLC."""
        self.plc = plc or SimulatedPLC()

    async def read(self, tag: str) -> float:
        """Read a simulated tag."""
        return self.plc.read(tag)

    async def write(self, tag: str, value: float) -> WriteOutcome:
        """Write a simulated setpoint."""
        result = self.plc.write(tag, value)
        return WriteOutcome(result.accepted, result.before, result.after, result.reason)

    def describe(self) -> dict[str, Any]:
        """Return the simulated device snapshot."""
        return {"protocol": "simulated", "online": True, **self.plc.snapshot()}


class OpcUaAdapter(DeviceAdapter):
    """OPC UA adapter using asyncua (optional dependency)."""

    def __init__(self, endpoint: str = "opc.tcp://localhost:4840") -> None:
        """Store the endpoint."""
        self.endpoint = endpoint
        self.client: Any | None = None

    async def connect(self) -> None:
        """Connect to the OPC UA server."""
        try:
            from asyncua import Client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("asyncua is required for OPC UA actuation") from exc
        self.client = Client(url=self.endpoint)
        await self.client.connect()

    async def _node(self, tag: str) -> Any:
        """Find a writable tag node."""
        if self.client is None:
            await self.connect()
        assert self.client is not None
        return await self.client.nodes.root.get_child(
            ["0:Objects", "2:PipeGuard", f"2:{tag}"]
        )

    async def read(self, tag: str) -> float:
        """Read an OPC UA variable."""
        return float(await (await self._node(tag)).read_value())

    async def write(self, tag: str, value: float) -> WriteOutcome:
        """Write an OPC UA variable and read back the result."""
        before = await self.read(tag)
        await (await self._node(tag)).write_value(value)
        return WriteOutcome(True, before, await self.read(tag))

    def describe(self) -> dict[str, Any]:
        """Return adapter state."""
        return {"protocol": "opcua", "endpoint": self.endpoint, "online": self.client is not None}


class ModbusAdapter(DeviceAdapter):
    """Modbus TCP adapter using pymodbus (optional dependency)."""

    def __init__(self, host: str = "localhost", port: int = 5020) -> None:
        """Store connection details."""
        self.host = host
        self.port = port
        self.client: Any | None = None
        self._registers = {"vfd_speed_rpm": 100, "valve_close_rate_pct_s": 101}

    async def _connect(self) -> None:
        """Create an async Modbus client."""
        if self.client is not None:
            return
        try:
            from pymodbus.client import AsyncModbusTcpClient
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pymodbus is required for Modbus actuation") from exc
        self.client = AsyncModbusTcpClient(self.host, port=self.port)
        await self.client.connect()

    async def read(self, tag: str) -> float:
        """Read a holding register."""
        await self._connect()
        assert self.client is not None
        address = self._registers.get(tag)
        if address is None:
            return 0.0
        response = await self.client.read_holding_registers(address, count=1)
        if response.isError():
            raise RuntimeError(f"Modbus read failed for {tag}")
        return float(response.registers[0]) / 10.0

    async def write(self, tag: str, value: float) -> WriteOutcome:
        """Write a holding register."""
        before = await self.read(tag)
        address = self._registers.get(tag)
        if address is None:
            return WriteOutcome(False, before, before, f"unknown tag {tag}")
        assert self.client is not None
        await self.client.write_register(address, int(value * 10))
        return WriteOutcome(True, before, await self.read(tag))

    def describe(self) -> dict[str, Any]:
        """Return adapter state."""
        return {
            "protocol": "modbus", "host": self.host, "port": self.port,
            "online": self.client is not None,
        }


class DeviceRegistry:
    """Map a protocol name to a device adapter."""

    def __init__(self, simulated: SimulatedAdapter | None = None, **kwargs: str) -> None:
        """Create a registry with a simulated adapter by default."""
        self.adapters: dict[str, DeviceAdapter] = {
            "simulated": simulated or SimulatedAdapter(),
            "opcua": OpcUaAdapter(str(kwargs.get("opcua_endpoint", "opc.tcp://localhost:4840"))),
            "modbus": ModbusAdapter(
                str(kwargs.get("modbus_host", "localhost")), int(kwargs.get("modbus_port", 5020))
            ),
        }

    def get(self, protocol: str) -> DeviceAdapter:
        """Return an adapter, falling back to the simulator for unknown protocols."""
        return self.adapters.get(protocol, self.adapters["simulated"])
