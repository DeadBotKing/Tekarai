"""Identity public facade for OTHER contexts (RULE F, ADR-021 pattern).

Other bounded contexts may import exactly this module — never Identity's
domain/infrastructure/presentation. The Communication context (Phase 08)
uses it for session verification and lightweight user lookups (§17).
"""

from __future__ import annotations

import uuid


def verifySessionToken(token: str):
    """Verify a bearer access JWT → SessionPrincipal | None."""
    from apps.identity.infrastructure.services.principals import (
        SessionVerifierDjango,
    )

    try:
        return SessionVerifierDjango().verifyToken(token)
    except Exception:  # noqa: BLE001 — callers treat any failure as anonymous
        return None


def userExists(tenantId: uuid.UUID, userId: uuid.UUID) -> bool:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    return UserRepositoryDjango().getById(userId, tenantId) is not None


def usernameOf(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    user = UserRepositoryDjango().getById(userId, tenantId)
    return user.username if user else ""


def userIdOfUsername(tenantId: uuid.UUID, username: str) -> uuid.UUID | None:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    user = UserRepositoryDjango().getByUsername(tenantId, username.lstrip("@"))
    return user.id if user else None
