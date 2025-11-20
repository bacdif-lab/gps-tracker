"""Security utilities for RBAC, MFA, key management and audit signing."""
from __future__ import annotations

import base64
import hmac
import hashlib
import os
import struct
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Optional


class Roles(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operador"
    CLIENT = "cliente"
    DRIVER_VIEW = "driver-view"

    @classmethod
    def all(cls) -> list[str]:
        return [role.value for role in cls]


@dataclass
class KeyManager:
    """Simple in-memory key manager with rotation support.

    Keys are read from environment variables so they can be injected from
    Vault/Secrets Manager. ``JWT_SIGNING_KEYS`` and ``AUDIT_SIGNING_KEYS``
    accept comma-separated values where the first one is considered the active
    key and the rest are kept for validation/verification until they expire.
    """

    jwt_keys: list[str]
    audit_keys: list[str]

    @classmethod
    def from_env(cls) -> "KeyManager":
        jwt_keys = _load_keys("JWT_SIGNING_KEYS", fallback="change-this-secret")
        audit_keys = _load_keys("AUDIT_SIGNING_KEYS", fallback="audit-signing-secret")
        return cls(jwt_keys=jwt_keys, audit_keys=audit_keys)

    @property
    def active_jwt_key(self) -> str:
        return self.jwt_keys[0]

    @property
    def active_audit_key(self) -> str:
        return self.audit_keys[0]

    def rotate_jwt_key(self, new_key: str) -> None:
        self.jwt_keys.insert(0, new_key)

    def rotate_audit_key(self, new_key: str) -> None:
        self.audit_keys.insert(0, new_key)


# MFA helpers ---------------------------------------------------------------

def generate_totp_secret() -> str:
    """Generate a random base32 secret suitable for TOTP apps."""

    return base64.b32encode(os.urandom(20)).decode("utf-8")


def _time_counter(time_step: int = 30, for_time: Optional[int] = None) -> int:
    epoch_time = for_time if for_time is not None else int(time.time())
    return int(epoch_time / time_step)


def generate_totp(secret: str, digits: int = 6, time_step: int = 30, for_time: Optional[int] = None) -> str:
    """Generate a TOTP code using only stdlib primitives."""

    key = base64.b32decode(secret, casefold=True)
    counter = _time_counter(time_step=time_step, for_time=for_time)
    msg = struct.pack("!Q", counter)
    hmac_digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = hmac_digest[-1] & 0x0F
    binary = struct.unpack("!I", hmac_digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = binary % (10**digits)
    return str(code).zfill(digits)


def verify_totp(secret: str, code: str, allowed_drift: int = 1) -> bool:
    """Validate a submitted code allowing small time drift."""

    try:
        int(code)
    except (TypeError, ValueError):
        return False

    for delta in range(-allowed_drift, allowed_drift + 1):
        expected = generate_totp(secret, for_time=int(time.time()) + delta * 30)
        if hmac.compare_digest(expected, code):
            return True
    return False


# Audit helpers -------------------------------------------------------------

def sign_payload(key: str, payload: str) -> str:
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _load_keys(env_var: str, fallback: str) -> list[str]:
    raw = os.getenv(env_var)
    if raw:
        return [piece.strip() for piece in raw.split(",") if piece.strip()]
    return [fallback]


def ensure_role_allowed(user_role: str, allowed: Iterable[Roles]) -> bool:
    allowed_values = {role.value for role in allowed}
    return user_role in allowed_values
