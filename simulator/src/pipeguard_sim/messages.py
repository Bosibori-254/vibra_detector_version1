"""Wire-format message builders and HMAC signing for the simulator."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pipeguard_sim.dsp import Features
from pipeguard_sim.signals import OperatingState

SCHEMA_VERSION = "1.0"
SIGNATURE_PREFIX = "hmac-sha256="


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(payload: dict[str, object]) -> str:
    """Serialize a message deterministically for HMAC computation."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_message(payload: dict[str, object], key: str) -> dict[str, object]:
    """Return a copy of ``payload`` with an HMAC-SHA256 signature attached."""
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    digest = hmac.new(key.encode("utf-8"), canonical_json(unsigned).encode("utf-8"), hashlib.sha256)
    return {**unsigned, "signature": SIGNATURE_PREFIX + digest.hexdigest()}


def verify_signature(payload: dict[str, object], key: str) -> bool:
    """Verify a message signature in constant time."""
    signature = payload.get("signature")
    if not isinstance(signature, str) or not signature.startswith(SIGNATURE_PREFIX):
        return False
    expected = sign_message(payload, key)["signature"]
    return hmac.compare_digest(signature, str(expected))


@dataclass(frozen=True)
class NodeHealth:
    """Node telemetry included in every feature message."""

    battery_pct: float = 87.2
    temp_c: float = 41.5
    mem_free_kb: int = 184
    sampling_ok: bool = True
    drift_ppm: float = 3.1
    clock_skew_ms: int = -4

    def as_dict(self) -> dict[str, object]:
        """Return the wire representation."""
        return {
            "battery_pct": self.battery_pct,
            "temp_c": self.temp_c,
            "mem_free_kb": self.mem_free_kb,
            "sampling_ok": self.sampling_ok,
            "drift_ppm": self.drift_ppm,
            "clock_skew_ms": self.clock_skew_ms,
        }


def make_feature_message(
    *,
    site: str,
    segment: str,
    node_id: str,
    sequence: int,
    features: Features,
    operating_state: OperatingState,
    timestamp: str | None = None,
    health: NodeHealth | None = None,
    signing_key: str | None = None,
) -> dict[str, object]:
    """Build a signed ``FeatureMessage`` matching the architecture schema."""
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "message_id": str(uuid.uuid4()),
        "node_id": node_id,
        "site": site,
        "segment": segment,
        "timestamp": timestamp or utc_now(),
        "sequence": sequence,
        "operating_state": operating_state.as_dict(),
        "features": features.as_dict(),
        "health": (health or NodeHealth()).as_dict(),
    }
    return sign_message(payload, signing_key) if signing_key else {**payload, "signature": ""}


def make_raw_message(
    *,
    site: str,
    segment: str,
    node_id: str,
    sequence: int,
    t0: str,
    sample_rate_hz: int,
    axis: str,
    samples: list[float],
    trigger_reason: str,
    signing_key: str | None = None,
) -> dict[str, object]:
    """Build a signed ``RawMessage`` for on-demand waveform capture."""
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "message_id": str(uuid.uuid4()),
        "site": site,
        "segment": segment,
        "node_id": node_id,
        "sequence": sequence,
        "t0": t0,
        "sample_rate_hz": sample_rate_hz,
        "axis": axis,
        "samples_mg": [round(float(s), 3) for s in samples],
        "trigger_reason": trigger_reason,
    }
    return sign_message(payload, signing_key) if signing_key else {**payload, "signature": ""}


def make_status_message(
    *,
    site: str,
    segment: str,
    node_id: str,
    online: bool,
    reason: str = "",
    signing_key: str | None = None,
) -> dict[str, object]:
    """Build a retained status/LWT message."""
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "node_id": node_id,
        "site": site,
        "segment": segment,
        "online": online,
        "reason": reason,
        "timestamp": utc_now(),
    }
    return sign_message(payload, signing_key) if signing_key else {**payload, "signature": ""}


def feature_topic(site: str, segment: str, node_id: str, kind: str = "features") -> str:
    """Return the MQTT topic for a node message kind."""
    return f"pipeguard/{site}/{segment}/{node_id}/{kind}"
