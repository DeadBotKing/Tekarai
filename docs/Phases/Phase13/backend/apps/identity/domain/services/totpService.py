"""TOTP service — RFC 6238, pure domain, stdlib only (Phase 07 §24).

No dependency, no Django: HMAC-SHA1 over a 30-second step, 6 digits,
±1 step drift tolerance on verification. Used by MFA setup/confirm and the
login challenge. WebAuthn/OTP methods plug in beside it (§24) without
touching callers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1  # ±30s clock tolerance


def generateSecret() -> str:
    """New base32 secret (160 bits) for a TOTP factor."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def currentCode(secret: str, *, at: int | None = None) -> str:
    timestamp = at if at is not None else int(time.time())
    counter = timestamp // STEP_SECONDS
    return _codeForCounter(secret, counter)


def verifyCode(secret: str, code: str, *, at: int | None = None) -> bool:
    if len(code) != DIGITS or not code.isdigit():
        return False
    timestamp = at if at is not None else int(time.time())
    counter = timestamp // STEP_SECONDS
    for drift in range(-DRIFT_STEPS, DRIFT_STEPS + 1):
        if hmac.compare_digest(_codeForCounter(secret, counter + drift), code):
            return True
    return False


def otpauthUrl(secret: str, account: str, issuer: str = "Tekarai") -> str:
    label = f"{issuer}:{account}"
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"


def _codeForCounter(secret: str, counter: int) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**DIGITS)).zfill(DIGITS)
