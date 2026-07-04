"""Token + OTP cryptography (spec F3 / F4).

- Access tokens: short-lived signed JWTs carrying the user's `token_epoch`.
  Instant "log out everywhere" = bump the user's epoch; stale tokens fail the
  epoch check at validation time.
- Refresh tokens: opaque random strings; only their SHA-256 hash is stored, in
  a server-side registry, with rotation + reuse detection.
- OTP codes: random 6-digit, stored as SHA-256 hash only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from jose import JWTError, jwt

from .config import get_settings

settings = get_settings()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- Hashing (OTP + refresh tokens) ---
def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --- OTP ---
def generate_otp_code() -> str:
    # cryptographically random 6-digit, zero-padded
    return f"{secrets.randbelow(1_000_000):06d}"


# --- Refresh tokens ---
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def refresh_expiry() -> dt.datetime:
    return _now() + dt.timedelta(days=settings.refresh_token_ttl_days)


# --- Access tokens (JWT) ---
def mint_access_token(user_id: str, token_epoch: int) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    expires_in = settings.access_token_ttl_minutes * 60
    now = _now()
    payload = {
        "sub": user_id,
        "epoch": token_epoch,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_in)).timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Raise JWTError if invalid/expired. Epoch comparison happens in the dependency."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise JWTError("wrong token type")
    return payload
