"""Message signatures, JWT tokens and role-based access control."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SIGNATURE_PREFIX = "hmac-sha256="
ROLE_LEVELS = {"viewer": 0, "operator": 1, "engineer": 2, "admin": 3}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON serialization for HMAC verification."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def expected_signature(payload: dict[str, Any], key: str) -> str:
    """Compute the expected HMAC signature for a payload."""
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    digest = hmac.new(
        key.encode("utf-8"), canonical_json(unsigned).encode("utf-8"), hashlib.sha256
    )
    return SIGNATURE_PREFIX + digest.hexdigest()


def verify_hmac(payload: dict[str, Any], key: str) -> bool:
    """Verify a signed telemetry message in constant time."""
    signature = payload.get("signature")
    if not isinstance(signature, str) or not signature.startswith(SIGNATURE_PREFIX):
        return False
    if not key:
        return False
    return hmac.compare_digest(signature, expected_signature(payload, key))


def _b64url(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    """Base64url decode with restored padding."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_jwt(subject: str, role: str, secret: str, ttl_s: int = 3600) -> str:
    """Create a compact HS256 JWT (prototype-grade token issuance)."""
    if role not in ROLE_LEVELS:
        raise ValueError(f"unknown role: {role}")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {"sub": subject, "role": role, "iat": now, "exp": now + ttl_s}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(signature)


def decode_jwt(token: str, secret: str) -> dict[str, Any]:
    """Decode and validate an HS256 JWT."""
    try:
        header_part, claims_part, signature_part = token.split(".")
        header = json.loads(_b64url_decode(header_part))
        if header.get("alg") != "HS256":
            raise ValueError("unsupported algorithm")
        expected = hmac.new(
            secret.encode(), f"{header_part}.{claims_part}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url(expected), signature_part):
            raise ValueError("invalid signature")
        claims = json.loads(_b64url_decode(claims_part))
        if int(claims.get("exp", 0)) < time.time():
            raise ValueError("token expired")
        return claims
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid token") from exc


def require_role(required: str, secret: str):
    """FastAPI dependency factory enforcing a minimum role level."""
    allowed_level = ROLE_LEVELS[required]

    def dependency(token: str | None = Depends(oauth2_scheme)) -> dict[str, Any]:
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        try:
            claims = decode_jwt(token, secret)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        if ROLE_LEVELS.get(str(claims.get("role")), -1) < allowed_level:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return claims

    return dependency
