"""PipeGuard software simulator: synthetic pipeline vibration with fault injection."""

from pipeguard_sim.dsp import (
    FeatureConfig,
    Features,
    FFTPeak,
    extract_features,
)
from pipeguard_sim.signals import (
    FaultType,
    OperatingState,
    SensorFaultMode,
    SignalParams,
    SignalResult,
    generate_signal,
)

__all__ = [
    "FFTPeak",
    "FaultType",
    "FeatureConfig",
    "Features",
    "OperatingState",
    "SensorFaultMode",
    "SignalParams",
    "SignalResult",
    "extract_features",
    "generate_signal",
]
