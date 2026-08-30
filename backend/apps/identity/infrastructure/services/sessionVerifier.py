"""SessionVerifierDjango — the authentication port implementation (§16).

Resolves a bearer token into a ``SessionPrincipal``; authentication only —
no permission decisions happen here (§16 separation).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from apps.identity.infrastructure.models import SessionModel, UserModel
from apps.sharedKernel.domain.errors import TokenExpiredError


class SessionPrincipalImpl:
    """What the request context sees after authentication (§26)."""

    def __init__(self, userId: uuid.UUID, tenantId: uuid.UUID, displayName: str) -> None:
        self.userId = userId
        self.tenantId = tenantId
        self.displayName = displayName

    @property
    def id(self) -> uuid.UUID:  # DRF treats request.user.id as identity
        return self.userId

    @property
    def is_authenticated(self) -> bool:  # DRF compatibility flag
        return True


class SessionVerifierDjango:
    def verifyToken(self, token: str) -> Any:
        from apps.identity.application.useCases.sessionUseCases import hashToken

        model = SessionModel.objects.filter(tokenHash=hashToken(token)).first()
        if model is None or model.revokedAt is not None:
            from apps.sharedKernel.domain.errors import InvalidCredentialsError

            raise InvalidCredentialsError("Invalid session token.")
        if model.expiresAt <= datetime.now(tz=UTC):
            raise TokenExpiredError("Session expired.")
        user = UserModel.objects.filter(id=model.userId, deletedAt__isnull=True).first()
        if user is None or user.status != "active":
            from apps.sharedKernel.domain.errors import AuthenticationRequiredError

            raise AuthenticationRequiredError("Account is not active.")
        SessionModel.objects.filter(id=model.id).update(lastUsedAt=datetime.now(tz=UTC))
        return SessionPrincipalImpl(
            userId=model.userId, tenantId=model.tenantId, displayName=user.displayName
        )
