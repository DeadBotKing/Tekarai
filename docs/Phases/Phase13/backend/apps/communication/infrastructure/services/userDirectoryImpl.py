"""Identity-backed implementation of the communication UserDirectory port.

Cross-context access goes through Identity's PUBLIC application facade
(RULE F / ADR-021) — never Identity's internals.
"""

from __future__ import annotations

import uuid

from apps.identity.application.services import principalDirectory


class UserDirectoryOverIdentity:
    """Anti-corruption lookup over the Identity context (§17)."""

    def exists(self, tenantId: uuid.UUID, userId: uuid.UUID) -> bool:
        return principalDirectory.userExists(tenantId, userId)

    def usernameOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str:
        return principalDirectory.usernameOf(tenantId, userId)

    def idOfUsername(self, tenantId: uuid.UUID, username: str) -> uuid.UUID | None:
        return principalDirectory.userIdOfUsername(tenantId, username)
