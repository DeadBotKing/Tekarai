"""JWT service — HS256 compact JWS, stdlib only (Phase 07 §7–§8, ADR-022).

Access tokens carry the §8 claim set — sub, jti, iat, exp, iss, aud,
tenantId, sessionId, typ — and NOTHING else: permissions stay out of the
token so a permission change never waits for token expiry (§8; invariant
§35.9). Verification checks signature, issuer, audience, type and expiry;
session revocation is then re-checked against the Session row by the
verifier — the JWT is never the sole session mechanism (§7).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    TokenExpiredError,
)

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_MFA_CHALLENGE = "mfaChallenge"


def b64urlEncode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64urlDecode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class JwtService:
    """Signs and verifies tokens with a symmetric key from settings (ADR-022)."""

    def __init__(
        self,
        *,
        signingKey: str,
        issuer: str,
        audience: str,
        accessTtlMinutes: int,
        challengeTtlMinutes: int = 5,
    ) -> None:
        self.signingKey = signingKey.encode("utf-8")
        self.issuer = issuer
        self.audience = audience
        self.accessTtlMinutes = accessTtlMinutes
        self.challengeTtlMinutes = challengeTtlMinutes

    # -- issuing ---------------------------------------------------------------

    def issueAccessToken(
        self,
        *,
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        sessionId: uuid.UUID,
    ) -> tuple[str, int]:
        now = int(time.time())
        ttlSeconds = self.accessTtlMinutes * 60
        claims = {
            "sub": str(userId),
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + ttlSeconds,
            "iss": self.issuer,
            "aud": self.audience,
            "tenantId": str(tenantId),
            "sessionId": str(sessionId),
            "typ": TOKEN_TYPE_ACCESS,
        }
        return self._encode(claims), ttlSeconds

    def issueMfaChallenge(
        self, *, userId: uuid.UUID, tenantId: uuid.UUID, sessionId: uuid.UUID
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": str(userId),
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + self.challengeTtlMinutes * 60,
            "iss": self.issuer,
            "aud": self.audience,
            "tenantId": str(tenantId),
            "sessionId": str(sessionId),
            "typ": TOKEN_TYPE_MFA_CHALLENGE,
        }
        return self._encode(claims)

    # -- verifying -------------------------------------------------------------

    def verifyAccessToken(self, token: str) -> dict[str, Any]:
        return self._verify(token, expectedType=TOKEN_TYPE_ACCESS)

    def verifyMfaChallenge(self, token: str) -> dict[str, Any]:
        return self._verify(token, expectedType=TOKEN_TYPE_MFA_CHALLENGE)

    # -- internals ---------------------------------------------------------------

    def _encode(self, claims: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        segments = [
            b64urlEncode(json.dumps(header, separators=(",", ":")).encode()),
            b64urlEncode(json.dumps(claims, separators=(",", ":")).encode()),
        ]
        signingInput = ".".join(segments).encode("ascii")
        signature = hmac.new(self.signingKey, signingInput, hashlib.sha256).digest()
        segments.append(b64urlEncode(signature))
        return ".".join(segments)

    def _verify(self, token: str, *, expectedType: str) -> dict[str, Any]:
        try:
            headerPart, payloadPart, signaturePart = token.split(".")
        except ValueError as exc:
            raise AuthenticationRequiredError("Malformed token.") from exc
        header = json.loads(b64urlDecode(headerPart))
        if header.get("alg") != "HS256":
            raise AuthenticationRequiredError("Unsupported token algorithm.")
        signingInput = f"{headerPart}.{payloadPart}".encode("ascii")
        expectedSignature = hmac.new(self.signingKey, signingInput, hashlib.sha256).digest()
        if not hmac.compare_digest(expectedSignature, b64urlDecode(signaturePart)):
            raise AuthenticationRequiredError("Invalid token signature.")
        claims = json.loads(b64urlDecode(payloadPart))
        if claims.get("iss") != self.issuer or claims.get("aud") != self.audience:
            raise AuthenticationRequiredError("Invalid token issuer/audience.")
        if claims.get("typ") != expectedType:
            raise AuthenticationRequiredError("Invalid token type.")
        if int(claims.get("exp", 0)) <= int(time.time()):
            raise TokenExpiredError("Token expired.")
        return claims


def defaultJwtService() -> JwtService:
    """Composition facade reading the settings (ADR-022 configuration)."""
    from django.conf import settings

    config = getattr(settings, "JWT_AUTH", {})
    return JwtService(
        signingKey=config.get("signingKey") or settings.SECRET_KEY,
        issuer=config.get("issuer", "tekarai"),
        audience=config.get("audience", "tekarai-api"),
        accessTtlMinutes=config.get("accessTtlMinutes", 15),
        challengeTtlMinutes=config.get("challengeTtlMinutes", 5),
    )


class JwtTokenIssuerDjango:
    """TokenIssuer port implementation (§7) — thin facade over JwtService."""

    def issueAccessToken(
        self, *, userId: uuid.UUID, tenantId: uuid.UUID, sessionId: uuid.UUID
    ) -> tuple[str, int]:
        return defaultJwtService().issueAccessToken(
            userId=userId, tenantId=tenantId, sessionId=sessionId
        )

    def issueMfaChallenge(
        self, *, userId: uuid.UUID, tenantId: uuid.UUID, sessionId: uuid.UUID
    ) -> str:
        return defaultJwtService().issueMfaChallenge(
            userId=userId, tenantId=tenantId, sessionId=sessionId
        )

    def verifyAccessToken(self, token: str) -> dict:
        return defaultJwtService().verifyAccessToken(token)

    def verifyMfaChallenge(self, token: str) -> dict:
        return defaultJwtService().verifyMfaChallenge(token)
