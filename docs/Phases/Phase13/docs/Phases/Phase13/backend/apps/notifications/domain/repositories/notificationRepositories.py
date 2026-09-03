"""Notification repository Protocols + ports (Phase 09 §13/§31/§39).

Domain/application depend on these interfaces only; infrastructure
implements them (house rule §36/§37 — the domain never touches the ORM,
Redis, Channels or provider SDKs).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from apps.notifications.domain.entities.notification import Notification
from apps.notifications.domain.entities.notificationDelivery import NotificationDelivery
from apps.notifications.domain.entities.notificationDevice import NotificationDevice
from apps.notifications.domain.entities.notificationDigest import (
    NotificationDigest,
    NotificationSchedule,
)
from apps.notifications.domain.entities.notificationPolicy import NotificationPolicy
from apps.notifications.domain.entities.notificationPreference import (
    NotificationPreference,
    NotificationPreferenceRule,
)
from apps.notifications.domain.entities.notificationTemplate import NotificationTemplate


# ---------------------------------------------------------------------------
# §39 repositories
# ---------------------------------------------------------------------------


class NotificationRepository(Protocol):
    def create(self, notification: Notification) -> None: ...
    def update(self, notification: Notification) -> None: ...
    def getById(
        self, notificationId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Notification | None: ...
    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, idempotencyKey: str
    ) -> Notification | None: ...
    def lastCreatedAtOfType(
        self, tenantId: uuid.UUID, recipientId: uuid.UUID, notificationType: str
    ) -> datetime | None: ...
    def countRecentOfType(
        self,
        tenantId: uuid.UUID,
        recipientId: uuid.UUID,
        notificationType: str,
        since: datetime,
    ) -> int: ...
    def listForRecipient(
        self,
        tenantId: uuid.UUID,
        recipientId: uuid.UUID,
        *,
        unreadOnly: bool = False,
        category: str = "",
        priority: str = "",
        beforeId: uuid.UUID | None = None,
        limit: int = 50,
        includeArchived: bool = False,
    ) -> tuple[list[Notification], int, bool]: ...
    def listDispatchable(
        self, tenantId: uuid.UUID | None, *, limit: int = 100
    ) -> list[Notification]: ...
    def listExpiredUndelivered(self, now: datetime, *, limit: int = 200) -> list[Notification]: ...
    def listDigestible(
        self, tenantId: uuid.UUID, userId: uuid.UUID, since: datetime, until: datetime
    ) -> list[Notification]: ...
    def unreadCount(self, tenantId: uuid.UUID, recipientId: uuid.UUID) -> int: ...
    def readAndAckCounts(
        self, tenantId: uuid.UUID, recipientId: uuid.UUID
    ) -> tuple[int, int, int]: ...  # (total, read, acknowledged)


class NotificationDeliveryRepository(Protocol):
    def create(self, delivery: NotificationDelivery) -> None: ...
    def update(self, delivery: NotificationDelivery) -> None: ...
    def getForNotification(
        self, notificationId: uuid.UUID
    ) -> list[NotificationDelivery]: ...
    def listPendingRetry(self, now: datetime, *, limit: int = 100) -> list[NotificationDelivery]: ...
    def channelUsageCounts(self, tenantId: uuid.UUID) -> dict[str, int]: ...


class NotificationPreferenceRepository(Protocol):
    def save(self, preference: NotificationPreference) -> None: ...
    def replaceForUser(self, userId: uuid.UUID, rows: list[NotificationPreference]) -> None: ...
    def listForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID
    ) -> list[NotificationPreference]: ...
    def saveRule(self, rule: NotificationPreferenceRule) -> None: ...
    def deleteRule(self, ruleId: uuid.UUID) -> bool: ...
    def listRules(self, tenantId: uuid.UUID) -> list[NotificationPreferenceRule]: ...


class NotificationTemplateRepository(Protocol):
    def create(self, template: NotificationTemplate) -> None: ...
    def deactivate(self, templateId: uuid.UUID) -> None: ...
    def findActive(
        self, tenantId: uuid.UUID, templateKey: str, language: str, channel: str
    ) -> NotificationTemplate | None: ...
    def listVersions(
        self, tenantId: uuid.UUID, templateKey: str, language: str, channel: str
    ) -> list[NotificationTemplate]: ...
    def listAll(self, tenantId: uuid.UUID) -> list[NotificationTemplate]: ...


class NotificationPolicyRepository(Protocol):
    def create(self, policy: NotificationPolicy) -> None: ...
    def update(self, policy: NotificationPolicy) -> None: ...
    def getById(self, policyId: uuid.UUID) -> NotificationPolicy | None: ...
    def findByKey(self, tenantId: uuid.UUID, policyKey: str) -> NotificationPolicy | None: ...
    def findApplicable(
        self, tenantId: uuid.UUID, notificationType: str, category: str
    ) -> NotificationPolicy | None: ...
    def listAll(self, tenantId: uuid.UUID) -> list[NotificationPolicy]: ...
    def delete(self, policyId: uuid.UUID) -> bool: ...


class NotificationDeviceRepository(Protocol):
    def create(self, device: NotificationDevice) -> None: ...
    def update(self, device: NotificationDevice) -> None: ...
    def getById(self, deviceId: uuid.UUID) -> NotificationDevice | None: ...
    def findByIdentifier(
        self, tenantId: uuid.UUID, userId: uuid.UUID, deviceIdentifier: str
    ) -> NotificationDevice | None: ...
    def listForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID, *, activeOnly: bool = False
    ) -> list[NotificationDevice]: ...
    def activeForUser(self, tenantId: uuid.UUID, userId: uuid.UUID) -> list[NotificationDevice]: ...


class NotificationDigestRepository(Protocol):
    def create(self, digest: NotificationDigest) -> None: ...
    def update(self, digest: NotificationDigest) -> None: ...
    def openDigest(
        self, tenantId: uuid.UUID, userId: uuid.UUID, kind: str
    ) -> NotificationDigest | None: ...
    def addItem(self, digestId: uuid.UUID, notificationId: uuid.UUID) -> None: ...
    def itemsOf(self, digestId: uuid.UUID) -> list[uuid.UUID]: ...


class NotificationScheduleRepository(Protocol):
    def create(self, schedule: NotificationSchedule) -> None: ...
    def update(self, schedule: NotificationSchedule) -> None: ...
    def getById(self, scheduleId: uuid.UUID) -> NotificationSchedule | None: ...
    def listDue(self, now: datetime, *, limit: int = 100) -> list[NotificationSchedule]: ...
    def listAll(self, tenantId: uuid.UUID) -> list[NotificationSchedule]: ...


# ---------------------------------------------------------------------------
# §13 provider ports — the domain is provider agnostic
# ---------------------------------------------------------------------------


@runtime_checkable
class NotificationChannelPort(Protocol):
    """A delivery channel (InApp/Email/Push/Sms/…) owned by infrastructure."""

    channelName: str

    def deliver(
        self,
        *,
        tenantId: uuid.UUID,
        notification: Notification,
        renderedTitle: str,
        renderedSubject: str,
        renderedBody: str,
    ) -> "DeliveryResult": ...


class DeliveryResult:
    """Uniform channel outcome (§25) — retry classification included."""

    def __init__(self, *, ok: bool, errorCode: str = "", errorMessage: str = "") -> None:
        self.ok = ok
        self.errorCode = errorCode
        self.errorMessage = errorMessage


@runtime_checkable
class NotificationProviderPort(Protocol):
    """§13 — SMTP/FCM/APNs/Graph… all hide behind this port."""

    providerName: str

    def send(
        self,
        *,
        tenantId: uuid.UUID,
        recipientAddress: str,
        title: str,
        subject: str,
        body: str,
        meta: dict[str, Any],
    ) -> "DeliveryResult": ...


# ---------------------------------------------------------------------------
# §9 recipient resolution + user contact directory (application ports)
# ---------------------------------------------------------------------------


@runtime_checkable
class RecipientDirectory(Protocol):
    """Resolves a recipient spec to concrete user ids (§9)."""

    def resolveUserIds(
        self, tenantId: uuid.UUID, recipientSpec: dict[str, Any]
    ) -> list[uuid.UUID]: ...


@runtime_checkable
class UserContactDirectory(Protocol):
    """Contact data needed by channels — never loaded by the domain."""

    def emailOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str: ...
    def phoneOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str: ...
    def languageOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str: ...
    def exists(self, tenantId: uuid.UUID, userId: uuid.UUID) -> bool: ...


# ---------------------------------------------------------------------------
# §41 realtime push port (WebSocket is an optimization, DB is truth §14/§42)
# ---------------------------------------------------------------------------


@runtime_checkable
class NotificationRealtimePort(Protocol):
    def toUser(self, userId: uuid.UUID, event: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# §30 event subscription port — consuming outbox/integration events
# ---------------------------------------------------------------------------


@runtime_checkable
class EventSubscriberPort(Protocol):
    def subscribe(self, eventName: str, handler: Any) -> None: ...
