"""Principal resolution — token verifiers behind the shared-kernel ports.

- ``SessionVerifierDjango`` (§16): Bearer **access JWT** → principal; the
  signature is checked, then the Session row is re-checked so a revoked or
  expired session is rejected instantly (invariants §35.4/5) — JWT is never
  the sole session mechanism (§7).
- ``ApiKeyVerifierDjango`` (§22): ``X-API-Key`` → principal (user or service
  account); revoked/expired keys are rejected (invariants §35.6).

Authentication only — no permission decisions here (§20).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    TokenExpiredError,
)


class SessionPrincipalImpl:
    """What the request context sees after authentication (§26)."""

    def __init__(
        self,
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        displayName: str,
        *,
        sessionId: uuid.UUID | None = None,
        isServiceAccount: bool = False,
        scopes: tuple[str, ...] = (),
    ) -> None:
        self.userId = userId
        self.tenantId = tenantId
        self.displayName = displayName
        self.sessionId = sessionId
        self.isServiceAccount = isServiceAccount
        self.scopes = tuple(scopes)

    @property
    def id(self) -> uuid.UUID:  # DRF identity
        return self.userId

    @property
    def is_authenticated(self) -> bool:  # DRF compatibility flag
        return True


class SessionVerifierDjango:
    """verifyToken(bearerJwt) → principal (access JWT, §7/§8)."""

    def verifyToken(self, token: str) -> Any:
        from apps.identity.infrastructure.models import SessionModel, UserModel
        from apps.identity.infrastructure.services.jwtService import defaultJwtService

        claims = defaultJwtService().verifyAccessToken(token)
        sessionId = uuid.UUID(claims["sessionId"])
        session = SessionModel.objects.filter(id=sessionId).first()
        now = datetime.now(tz=UTC)
        if session is None or session.revokedAt is not None:
            raise AuthenticationRequiredError("Session revoked.")  # §35.4
        if session.expiresAt <= now:
            raise TokenExpiredError("Session expired.")  # §35.5
        user = UserModel.objects.filter(id=session.userId, deletedAt__isnull=True).first()
        if user is None or user.status != "active":
            raise AuthenticationRequiredError("Account is not active.")  # §35.7
        SessionModel.objects.filter(id=session.id).update(lastActivityAt=now)
        return SessionPrincipalImpl(
            userId=user.id,
            tenantId=session.tenantId,
            displayName=user.displayName or user.username,
            sessionId=session.id,
        )


class ApiKeyVerifierDjango:
    """verifyApiKey(rawKey) → principal (§22; invariants §35.6)."""

    def verifyApiKey(self, rawKey: str) -> Any:
        import hashlib

        from apps.identity.infrastructure.models import (
            ApiKeyModel,
            ServiceAccountModel,
            UserModel,
        )

        keyHash = hashlib.sha256(rawKey.encode("utf-8")).hexdigest()
        apiKey = ApiKeyModel.objects.select_related(None).filter(keyHash=keyHash).first()
        now = datetime.now(tz=UTC)
        if apiKey is None:
            raise AuthenticationRequiredError("Unknown API key.")
        if apiKey.revokedAt is not None:
            raise AuthenticationRequiredError("API key revoked.")  # §35.6
        if apiKey.expiresAt is not None and apiKey.expiresAt <= now:
            raise TokenExpiredError("API key expired.")  # §35.6
        ApiKeyModel.objects.filter(id=apiKey.id).update(lastUsedAt=now)
        if apiKey.ownerType == "serviceAccount":
            account = ServiceAccountModel.objects.filter(id=apiKey.ownerId).first()
            if account is None or account.status != "active":
                raise AuthenticationRequiredError("Service account disabled.")
            return SessionPrincipalImpl(
                userId=account.id,
                tenantId=apiKey.tenantId,
                displayName=f"service:{account.code}",
                isServiceAccount=True,
                scopes=tuple(apiKey.scopes or []),
            )
        user = UserModel.objects.filter(id=apiKey.ownerId, deletedAt__isnull=True).first()
        if user is None or user.status != "active":
            raise AuthenticationRequiredError("Account is not active.")
        return SessionPrincipalImpl(
            userId=user.id,
            tenantId=apiKey.tenantId,
            displayName=user.displayName or user.username,
            scopes=tuple(apiKey.scopes or []),
        )
