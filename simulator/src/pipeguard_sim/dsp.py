"""DSP primitives for PipeGuard feature extraction.

The same feature definitions are implemented in the Rust edge node (Phase 7);
keeping them here as reference makes cross-checking straightforward.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal as sp_signal

DEFAULT_BANDS_HZ: tuple[tuple[float, float], ...] = (
    (10.0, 50.0),
    (50.0, 150.0),
    (150.0, 500.0),
    (500.0, 2000.0),
)


def band_name(low: float, high: float) -> str:
    """Return the topic/schema key for a frequency band."""
    return f"{low:g}_{high:g}".replace(".", "p")


@dataclass(frozen=True)
class FFTPeak:
    """A dominant spectral peak."""

    hz: float
    amplitude_mps2: float

    def as_dict(self) -> dict[str, float]:
        """Return the wire representation."""
        return {"hz": round(self.hz, 3), "amplitude_mps2": round(self.amplitude_mps2, 6)}


@dataclass(frozen=True)
class FeatureConfig:
    """Configuration for :func:`extract_features` (all values configurable)."""

    sample_rate_hz: int = 2000
    window_seconds: float = 0.5
    bands_hz: tuple[tuple[float, float], ...] = DEFAULT_BANDS_HZ
    top_n_peaks: int = 5
    min_peak_separation_hz: float = 8.0
    velocity_band_hz: tuple[float, float] = (10.0, 1000.0)

    @property
    def window_samples(self) -> int:
        """Number of samples in one analysis window."""
        return round(self.sample_rate_hz * self.window_seconds)


@dataclass(frozen=True)
class Features:
    """Feature vector published by a node."""

    sample_rate_hz: int
    window_seconds: float
    accel_rms_mps2: dict[str, float]
    velocity_rms_mm_s: float
    peak_mps2: float
    crest_factor: float
    kurtosis: float
    band_energies: dict[str, float]
    fft_peaks: list[FFTPeak] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Return the ``features`` block of a FeatureMessage."""
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "window_seconds": self.window_seconds,
            "accel_rms_mps2": {k: round(v, 6) for k, v in self.accel_rms_mps2.items()},
            "velocity_rms_mm_s": round(self.velocity_rms_mm_s, 6),
            "peak_mps2": round(self.peak_mps2, 6),
            "crest_factor": round(self.crest_factor, 6),
            "kurtosis": round(self.kurtosis, 6),
            "band_energies": {k: round(v, 6) for k, v in self.band_energies.items()},
            "fft_peaks": [p.as_dict() for p in self.fft_peaks],
        }


def rms(values: np.ndarray) -> float:
    """Root-mean-square of a 1-D signal."""
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))


def peak(values: np.ndarray) -> float:
    """Maximum absolute amplitude of a 1-D signal."""
    return float(np.max(np.abs(values)))


def crest_factor(values: np.ndarray) -> float:
    """Peak-to-RMS ratio; high values indicate impulsive signals."""
    denominator = rms(values)
    return float(peak(values) / denominator) if denominator > 1e-12 else 0.0


def kurtosis(values: np.ndarray) -> float:
    """Excess kurtosis (Fisher definition, normal distribution ≈ 0)."""
    centered = values - np.mean(values)
    m2 = float(np.mean(centered**2))
    if m2 < 1e-18:
        return 0.0
    m4 = float(np.mean(centered**4))
    return float(m4 / (m2**2) - 3.0)


def velocity_rms_mm_s(
    accel_mps2: np.ndarray,
    sample_rate_hz: int,
    band_hz: tuple[float, float] = (10.0, 1000.0),
) -> float:
    """Band-limited velocity RMS in mm/s, as used by ISO 10816/20816 zones.

    Acceleration is band-pass filtered before integration to avoid low-frequency
    drift dominating the velocity estimate; a linear detrend removes residual bias.
    """
    nyquist = sample_rate_hz / 2.0
    low = max(band_hz[0], 0.1)
    high = min(band_hz[1], nyquist * 0.98)
    if high <= low:
        return 0.0
    sos = sp_signal.butter(
        4, [low, high], btype="bandpass", fs=sample_rate_hz, output="sos"
    )
    filtered = sp_signal.sosfiltfilt(sos, np.asarray(accel_mps2, dtype=np.float64))
    velocity = np.cumsum(filtered) / float(sample_rate_hz)
    velocity = sp_signal.detrend(velocity)
    return float(rms(velocity) * 1000.0)


def _spectrum(
    values: np.ndarray, sample_rate_hz: int
) -> tuple[np.ndarray, np.ndarray]:
    """Single-sided amplitude spectrum with a Hann window."""
    n = len(values)
    if n == 0:
        return np.array([]), np.array([])
    window = np.hanning(n)
    detrended = sp_signal.detrend(np.asarray(values, dtype=np.float64))
    spectrum = np.fft.rfft(detrended * window)
    amplitude = np.abs(spectrum) / max(float(np.sum(window) / 2.0), 1e-12)
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate_hz)
    return freqs, amplitude


def band_energies(
    values: np.ndarray,
    sample_rate_hz: int,
    bands_hz: tuple[tuple[float, float], ...] = DEFAULT_BANDS_HZ,
) -> dict[str, float]:
    """Return the fraction of spectral energy in each configured band.

    Energies are normalized so that the fractions sum to 1.0 (within rounding),
    making them comparable across nodes with different absolute sensitivity.
    """
    freqs, amplitude = _spectrum(values, sample_rate_hz)
    if len(freqs) < 2:
        return {band_name(lo, hi): 0.0 for lo, hi in bands_hz}
    power = amplitude**2
    total = float(np.sum(power[1:]))
    result: dict[str, float] = {}
    for low, high in bands_hz:
        mask = (freqs >= low) & (freqs < min(high, freqs[-1]))
        energy = float(np.sum(power[mask])) / total if total > 0 else 0.0
        result[band_name(low, high)] = energy
    return result


def top_spectral_peaks(
    values: np.ndarray,
    sample_rate_hz: int,
    top_n: int = 5,
    min_separation_hz: float = 8.0,
) -> list[FFTPeak]:
    """Find the ``top_n`` dominant spectral peaks with minimum separation."""
    freqs, amplitude = _spectrum(values, sample_rate_hz)
    if len(freqs) < 3 or top_n <= 0:
        return []
    resolution = freqs[1] - freqs[0]
    distance = max(1, round(min_separation_hz / resolution))
    indices, _ = sp_signal.find_peaks(
        amplitude[1:], distance=distance, prominence=float(np.max(amplitude) * 0.02)
    )
    indices = indices + 1
    if len(indices) == 0:
        dominant = int(np.argmax(amplitude[1:])) + 1
        indices = np.array([dominant])
    ordered = sorted(indices, key=lambda i: amplitude[i], reverse=True)[:top_n]
    return [FFTPeak(hz=float(freqs[i]), amplitude_mps2=float(amplitude[i])) for i in ordered]


def extract_features(samples: np.ndarray, config: FeatureConfig | None = None) -> Features:
    """Extract the PipeGuard feature vector from acceleration samples.

    ``samples`` may be ``(n,)`` (treated as the Z axis) or ``(n, 3)`` (X, Y, Z).
    Units are metres per second squared.
    """
    cfg = config or FeatureConfig()
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    if data.ndim != 2 or (data.shape[1] != 3 and data.shape[1] != 1):
        raise ValueError("samples must have shape (n,) or (n, 3)")
    if len(data) < 16:
        raise ValueError("at least 16 samples are required")
    axis_names = ("x", "y", "z")
    axis_data = {name: data[:, i] for i, name in enumerate(axis_names[: data.shape[1]])}
    dominant = axis_data.get("z", next(iter(axis_data.values())))
    return Features(
        sample_rate_hz=cfg.sample_rate_hz,
        window_seconds=cfg.window_seconds,
        accel_rms_mps2={name: rms(values) for name, values in axis_data.items()},
        velocity_rms_mm_s=velocity_rms_mm_s(dominant, cfg.sample_rate_hz, cfg.velocity_band_hz),
        peak_mps2=peak(dominant),
        crest_factor=crest_factor(dominant),
        kurtosis=kurtosis(dominant),
        band_energies=band_energies(dominant, cfg.sample_rate_hz, cfg.bands_hz),
        fft_peaks=top_spectral_peaks(
            dominant, cfg.sample_rate_hz, cfg.top_n_peaks, cfg.min_peak_separation_hz
        ),
    )
