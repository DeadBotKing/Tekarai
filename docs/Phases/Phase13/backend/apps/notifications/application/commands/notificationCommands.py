"""Notification commands (Phase 09 §38/§40).

Immutable application messages; camelCase per the platform standard.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CreateNotificationCommand:
    """§38 CreateNotificationService input (§7 event-driven or §40 API)."""

    tenantId: uuid.UUID
    recipientSpec: dict[str, Any]
    eventType: str
    eventId: str
    notificationType: str
    category: str
    priority: str
    title: str
    body: str = ""
    sourceType: str = ""
    sourceId: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    templateKey: str = ""
    actionUrl: str = ""
    ackRequired: bool = False
    channels: tuple[str, ...] = ()
    expiresAt: datetime | None = None
    correlationId: str = ""
    causationId: str = ""
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class ScheduleNotificationCommand:
    """§22 — IMMEDIATE / SCHEDULED / RECURRING / DELAYED / DIGEST."""

    tenantId: uuid.UUID
    kind: str
    recipientSpec: dict[str, Any]
    notificationType: str
    category: str
    priority: str
    title: str
    body: str = ""
    sourceType: str = ""
    sourceId: str = ""
    scheduledAt: datetime | None = None
    recurEverySeconds: int = 0
    delaySeconds: int = 0
    digestKind: str = ""
    expiresAt: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlationId: str = ""
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class CancelNotificationCommand:
    notificationId: uuid.UUID
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class CancelScheduleCommand:
    scheduleId: uuid.UUID
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class MarkNotificationReadCommand:
    notificationId: uuid.UUID
    recipientId: uuid.UUID


@dataclass(frozen=True)
class MarkNotificationsReadCommand:
    """Bulk read — client reconciliation (§42)."""

    recipientId: uuid.UUID
    notificationIds: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class MarkNotificationUnreadCommand:
    notificationId: uuid.UUID
    recipientId: uuid.UUID


@dataclass(frozen=True)
class AcknowledgeNotificationCommand:
    notificationId: uuid.UUID
    recipientId: uuid.UUID


@dataclass(frozen=True)
class ArchiveNotificationCommand:
    notificationId: uuid.UUID
    recipientId: uuid.UUID


@dataclass(frozen=True)
class UpdatePreferencesCommand:
    """§10 — replace the caller's preference set (three levels)."""

    tenantId: uuid.UUID
    userId: uuid.UUID
    preferences: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RegisterDeviceCommand:
    """§15 — one user may own many devices."""

    tenantId: uuid.UUID
    userId: uuid.UUID
    platform: str
    deviceIdentifier: str
    pushToken: str
    provider: str = "FCM"


@dataclass(frozen=True)
class RevokeDeviceCommand:
    deviceId: uuid.UUID
    userId: uuid.UUID


@dataclass(frozen=True)
class SaveTemplateCommand:
    """§18/§19 — new version when the key/language/channel already exists."""

    tenantId: uuid.UUID
    templateKey: str
    language: str
    channel: str
    titleTemplate: str
    subjectTemplate: str = ""
    bodyTemplate: str = ""
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class DeactivateTemplateCommand:
    templateId: uuid.UUID


@dataclass(frozen=True)
class SavePolicyCommand:
    """§8 — config-driven policy upsert (policyKey match type/category)."""

    tenantId: uuid.UUID
    policyKey: str
    matchType: str
    matchValue: str
    channels: tuple[str, ...] = ()
    priority: str = "NORMAL"
    templateKey: str = ""
    maxRetries: int = 3
    escalationStages: tuple[dict[str, Any], ...] = ()
    digestKind: str = ""
    allowPreferenceBypass: bool = False
    expiresAfterSeconds: int = 0
    cooldownSeconds: int = 0
    ackRequired: bool = False
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class DeletePolicyCommand:
    policyId: uuid.UUID


@dataclass(frozen=True)
class SaveTenantRuleCommand:
    """§11 — tenant FORCED/DENIED channel rules (never weaken security)."""

    tenantId: uuid.UUID
    effect: str  # FORCED | DENIED
    channel: str
    category: str = ""
    notificationType: str = ""
    actorId: uuid.UUID | None = None


@dataclass(frozen=True)
class DeleteTenantRuleCommand:
    ruleId: uuid.UUID


@dataclass(frozen=True)
class DispatchPendingCommand:
    """§32 — worker tick input."""

    tenantId: uuid.UUID | None = None
    limit: int = 100


@dataclass(frozen=True)
class RetryDueDeliveriesCommand:
    limit: int = 100


@dataclass(frozen=True)
class SendDueDigestsCommand:
    kind: str = ""  # "" = every due kind


@dataclass(frozen=True)
class RunDueSchedulesCommand:
    limit: int = 50


@dataclass(frozen=True)
class ExpireNotificationsCommand:
    limit: int = 200
