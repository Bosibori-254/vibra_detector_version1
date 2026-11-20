"""Tests for HMAC signing and JWT role tokens."""

from __future__ import annotations

import time

import pytest

from pipeguard_backend.security import (
    canonical_json,
    create_jwt,
    decode_jwt,
    expected_signature,
    verify_hmac,
)


def test_canonical_json_sorts_nested_keys() -> None:
    """Canonical JSON is deterministic regardless of insertion order."""
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == '{"a":{"c":3,"d":2},"b":1}'


def test_hmac_verification_roundtrip() -> None:
    """A signed payload verifies with the right key and fails with a wrong key."""
    payload = {"node_id": "node-03", "sequence": 1}
    signature = expected_signature(payload, "secret")
    signed = {**payload, "signature": signature}
    assert verify_hmac(signed, "secret")
    assert not verify_hmac(signed, "other-secret")


def test_hmac_ignores_signature_field_only() -> None:
    """Changing a signed field invalidates the signature."""
    payload = {"node_id": "node-03", "sequence": 1}
    signed = {**payload, "signature": expected_signature(payload, "secret")}
    tampered = {**signed, "sequence": 2}
    assert not verify_hmac(tampered, "secret")


def test_jwt_roundtrip_and_role_claims() -> None:
    """JWTs carry subject/role claims and validate their signature."""
    token = create_jwt("operator", "operator", "secret")
    claims = decode_jwt(token, "secret")
    assert claims["sub"] == "operator"
    assert claims["role"] == "operator"
    assert claims["exp"] > time.time()


def test_jwt_rejects_tampering_and_expiry() -> None:
    """Tampered or expired JWTs are rejected."""
    token = create_jwt("viewer", "viewer", "secret")
    parts = token.split(".")
    assert parts[2]
    signature = parts[2]
    flipped = ("a" if signature[0] != "a" else "b") + signature[1:]
    tampered = f"{parts[0]}.{parts[1]}.{flipped}"
    with pytest.raises(ValueError):
        decode_jwt(tampered, "secret")
    expired = create_jwt("viewer", "viewer", "secret", ttl_s=-10)
    with pytest.raises(ValueError):
        decode_jwt(expired, "secret")
