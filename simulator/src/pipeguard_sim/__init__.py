"""PipeGuard software simulator: synthetic pipeline vibration with fault injection."""

from pipeguard_sim.dsp import (
    FeatureConfig,
    FFTPeak,
    Features,
    extract_features,
)
from pipeguard_sim.signals import (
    FaultType,
    OperatingState,
    SignalParams,
    SignalResult,
    SensorFaultMode,
    generate_signal,
)

__all__ = [
    "FaultType",
    "FeatureConfig",
    "FFTPeak",
    "Features",
    "OperatingState",
    "SensorFaultMode",
    "SignalParams",
    "SignalResult",
    "extract_features",
    "generate_signal",
]
