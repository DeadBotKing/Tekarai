"""API Key aggregate (Phase 07 §22) — hashed · revocable · scoped ·
expirable · auditable. The raw key exists exactly once: in the creation
response. Server-to-server integrations authenticate with
``X-API-Key: tek_<key>``."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.events import DomainEvent

KEY_PREFIX = "tek"

OWNER_USER = "user"
OWNER_SERVICE_ACCOUNT = "serviceAccount"


class ApiKey(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        name: str,
        keyHash: str,
        prefix: str,
        ownerType: str,
        ownerId: uuid.UUID,
        createdAt: datetime,
        *,
        scopes: tuple[str, ...] = (),
        expiresAt: datetime | None = None,
        revokedAt: datetime | None = None,
        lastUsedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.name = name.strip()
        self.keyHash = keyHash
        self.prefix = prefix  # displayable identifier fragment (never the key)
        self.ownerType = ownerType
        self.ownerId = ownerId
        self.scopes = tuple(scopes)
        self.createdAt = createdAt
        self.expiresAt = expiresAt
        self.revokedAt = revokedAt
        self.lastUsedAt = lastUsedAt

    @staticmethod
    def issue(
        tenantId: uuid.UUID,
        name: str,
        keyHash: str,
        prefix: str,
        ownerType: str,
        ownerId: uuid.UUID,
        now: datetime,
        *,
        scopes: tuple[str, ...] = (),
        expiresAt: datetime | None = None,
    ) -> ApiKey:
        key = ApiKey(
            id=newId(),
            tenantId=tenantId,
            name=name,
            keyHash=keyHash,
            prefix=prefix,
            ownerType=ownerType,
            ownerId=ownerId,
            createdAt=now,
            scopes=scopes,
            expiresAt=expiresAt,
        )
        key.recordEvent(
            DomainEvent(
                name="apiKeyCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"name": key.name, "prefix": prefix},
            )
        )
        return key

    def revoke(self, now: datetime) -> None:
        if self.revokedAt is None:
            self.revokedAt = now
            self.recordEvent(
                DomainEvent(
                    name="apiKeyRevoked",
                    occurredAt=now,
                    tenantId=self.tenantId,
                    payload={"prefix": self.prefix},
                )
            )

    def isValidAt(self, now: datetime) -> bool:
        if self.revokedAt is not None:
            return False
        if self.expiresAt is not None and self.expiresAt <= now:
            return False
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "prefix": self.prefix,
            "ownerType": self.ownerType,
            "ownerId": str(self.ownerId),
            "scopes": list(self.scopes),
            "expiresAt": self.expiresAt.isoformat() if self.expiresAt else None,
            "revoked": self.revokedAt is not None,
        }
