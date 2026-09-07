"""Ports for Phase 15 notification completion services."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


class NotificationPlatformStore(Protocol):
    def search(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        *,
        query: str,
        notificationType: str,
        status: str,
        readState: str,
        channel: str,
        dateFrom: datetime | None,
        dateTo: datetime | None,
        beforeId: uuid.UUID | None,
        limit: int,
    ) -> tuple[dict[str, Any], ...]: ...

    def registerSubscription(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        endpoint: str,
        publicKey: str,
        authSecret: str,
        expiresAt: datetime | None,
    ) -> dict[str, Any]: ...

    def listSubscriptions(
        self, tenantId: uuid.UUID, userId: uuid.UUID
    ) -> tuple[dict[str, Any], ...]: ...

    def revokeSubscription(
        self, tenantId: uuid.UUID, userId: uuid.UUID, subscriptionId: uuid.UUID, now: datetime
    ) -> bool: ...

    def processWebhook(
        self,
        tenantId: uuid.UUID,
        provider: str,
        providerEventId: str,
        providerMessageId: str,
        status: str,
        payloadHash: str,
        errorCode: str,
        metadata: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]: ...

    def saveProviderConfiguration(
        self,
        tenantId: uuid.UUID,
        actorId: uuid.UUID,
        channel: str,
        provider: str,
        credentialRef: str,
        configuration: dict[str, Any],
        isActive: bool,
    ) -> dict[str, Any]: ...

    def listProviderConfigurations(self, tenantId: uuid.UUID) -> tuple[dict[str, Any], ...]: ...

    def cleanup(
        self,
        tenantId: uuid.UUID,
        actorId: uuid.UUID,
        cutoff: datetime,
        *,
        dryRun: bool,
    ) -> dict[str, int]: ...


class WebhookSecretProvider(Protocol):
    def secretFor(self, tenantId: uuid.UUID, provider: str) -> str: ...


__all__ = ["NotificationPlatformStore", "WebhookSecretProvider"]
