"""Authenticated at-rest envelope for notification device/subscription secrets.

The key is derived from Django's deployment secret; plaintext tokens are never
stored or logged. Versioned framing permits replacement by a KMS implementation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from django.conf import settings

_PREFIX = "ntf1."


def _key() -> bytes:
    return hashlib.sha256(("tekarai.notifications:" + settings.SECRET_KEY).encode()).digest()


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(map(len, blocks)) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def seal(value: str) -> str:
    raw = value.encode("utf-8")
    nonce = os.urandom(16)
    key = _key()
    encrypted = bytes(a ^ b for a, b in zip(raw, _stream(key, nonce, len(raw)), strict=True))
    tag = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()
    return _PREFIX + base64.urlsafe_b64encode(nonce + tag + encrypted).decode("ascii")


def openSecret(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value  # migration-compatible legacy row; rewritten on next rotation.
    packed = base64.urlsafe_b64decode(value[len(_PREFIX) :].encode("ascii"))
    if len(packed) < 48:
        raise ValueError("Invalid secret envelope.")
    nonce, tag, encrypted = packed[:16], packed[16:48], packed[48:]
    key = _key()
    expected = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Secret envelope authentication failed.")
    raw = bytes(a ^ b for a, b in zip(encrypted, _stream(key, nonce, len(encrypted)), strict=True))
    return raw.decode("utf-8")


__all__ = ["openSecret", "seal"]
