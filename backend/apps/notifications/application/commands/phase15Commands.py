"""Phase 15 Notification Platform completion commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class SearchNotificationsQuery(Command):
    query: str = ""
    notificationType: str = ""
    status: str = ""
    readState: str = ""
    channel: str = ""
    dateFrom: datetime | None = None
    dateTo: datetime | None = None
    beforeId: str = ""
    limit: int = 50


@dataclass(frozen=True)
class ProcessProviderWebhookCommand(Command):
    tenantId: str
    provider: str
    providerEventId: str
    providerMessageId: str
    status: str
    timestamp: str
    signature: str
    rawBody: bytes
    errorCode: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegisterPushSubscriptionCommand(Command):
    endpoint: str
    publicKey: str
    authSecret: str
    expiresAt: datetime | None = None


@dataclass(frozen=True)
class RevokePushSubscriptionCommand(Command):
    subscriptionId: str


@dataclass(frozen=True)
class SaveProviderConfigurationCommand(Command):
    channel: str
    provider: str
    credentialRef: str = ""
    configuration: dict[str, Any] = field(default_factory=dict)
    isActive: bool = True


@dataclass(frozen=True)
class RunNotificationCleanupCommand(Command):
    retentionDays: int | None = None
    dryRun: bool = True


__all__ = [
    "ProcessProviderWebhookCommand",
    "RegisterPushSubscriptionCommand",
    "RevokePushSubscriptionCommand",
    "RunNotificationCleanupCommand",
    "SaveProviderConfigurationCommand",
    "SearchNotificationsQuery",
]
