"""Notification DTOs (Phase 09 §40 responses)."""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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


@dataclass(frozen=True)
class DeliveryDto:
    id: str
    notificationId: str
    channel: str
    status: str
    provider: str
    attemptCount: int
    maxAttempts: int
    errorCode: str
    lastAttemptAt: datetime | None
    deliveredAt: datetime | None
    nextAttemptAt: datetime | None


def deliveryDtoFromDomain(delivery: NotificationDelivery) -> DeliveryDto:
    return DeliveryDto(
        id=str(delivery.id),
        notificationId=str(delivery.notificationId),
        channel=delivery.channel,
        status=delivery.status,
        provider=delivery.provider,
        attemptCount=delivery.attemptCount,
        maxAttempts=delivery.maxAttempts,
        errorCode=delivery.errorCode,
        lastAttemptAt=delivery.lastAttemptAt,
        deliveredAt=delivery.deliveredAt,
        nextAttemptAt=delivery.nextAttemptAt,
    )


@dataclass(frozen=True)
class NotificationDto:
    id: str
    tenantId: str
    recipientId: str
    notificationType: str
    category: str
    priority: str
    title: str
    body: str
    status: str
    channels: list[str] = field(default_factory=list)
    readAt: datetime | None = None
    acknowledgedAt: datetime | None = None
    archivedAt: datetime | None = None
    expiresAt: datetime | None = None
    scheduledAt: datetime | None = None
    sourceType: str = ""
    sourceId: str = ""
    actionUrl: str = ""
    ackRequired: bool = False
    correlationId: str = ""
    causationId: str = ""
    language: str = ""
    createdAt: datetime | None = None
    deliveries: list[DeliveryDto] = field(default_factory=list)


def notificationDtoFromDomain(
    notification: Notification,
    deliveries: list[NotificationDelivery] | None = None,
) -> NotificationDto:
    deliveries = deliveries or []
    return NotificationDto(
        id=str(notification.id),
        tenantId=str(notification.tenantId),
        recipientId=str(notification.recipientId),
        notificationType=notification.notificationType,
        category=notification.category,
        priority=notification.priority,
        title=notification.title,
        body=notification.body,
        status=notification.status,
        channels=[delivery.channel for delivery in deliveries],
        readAt=notification.readAt,
        acknowledgedAt=notification.acknowledgedAt,
        archivedAt=notification.deletedAt,
        expiresAt=notification.expiresAt,
        scheduledAt=notification.scheduledAt,
        sourceType=notification.sourceType,
        sourceId=notification.sourceId,
        actionUrl=str(notification.payload.get("actionUrl", "") or ""),
        ackRequired=notification.requiresAcknowledgement,
        correlationId=notification.correlationId,
        causationId=notification.causationId,
        language=notification.language,
        createdAt=notification.createdAt,
        deliveries=[deliveryDtoFromDomain(delivery) for delivery in deliveries],
    )


@dataclass(frozen=True)
class PreferenceDto:
    id: str
    level: str
    category: str
    notificationType: str
    channel: str
    enabled: bool
    quietHoursStart: str
    quietHoursEnd: str


def preferenceDtoFromDomain(preference: NotificationPreference) -> PreferenceDto:
    return PreferenceDto(
        id=str(preference.id),
        level=preference.level,
        category=preference.category,
        notificationType=preference.notificationType,
        channel=preference.channel,
        enabled=preference.enabled,
        quietHoursStart=preference.quietHoursStart,
        quietHoursEnd=preference.quietHoursEnd,
    )


@dataclass(frozen=True)
class TenantRuleDto:
    id: str
    action: str
    channel: str
    category: str
    notificationType: str
    description: str


def tenantRuleDtoFromDomain(rule: NotificationPreferenceRule) -> TenantRuleDto:
    return TenantRuleDto(
        id=str(rule.id),
        action=rule.action,
        channel=rule.channel,
        category=rule.category,
        notificationType=rule.notificationType,
        description=rule.description,
    )


@dataclass(frozen=True)
class DeviceDto:
    id: str
    platform: str
    deviceIdentifier: str
    provider: str
    isActive: bool
    lastSeenAt: datetime | None
    revokedAt: datetime | None
    createdAt: datetime | None


def deviceDtoFromDomain(device: NotificationDevice) -> DeviceDto:
    """§33 — push tokens never leave the server through a DTO."""
    return DeviceDto(
        id=str(device.id),
        platform=device.platform,
        deviceIdentifier=device.deviceIdentifier,
        provider=device.provider,
        isActive=device.isActive,
        lastSeenAt=device.lastSeenAt,
        revokedAt=device.revokedAt,
        createdAt=device.createdAt,
    )


@dataclass(frozen=True)
class TemplateDto:
    id: str
    templateKey: str
    language: str
    channel: str
    version: int
    isActive: bool
    title: str
    subject: str
    body: str
    placeholders: list[str] = field(default_factory=list)
    createdAt: datetime | None = None


def templateDtoFromDomain(template: NotificationTemplate) -> TemplateDto:
    return TemplateDto(
        id=str(template.id),
        templateKey=template.templateKey,
        language=template.language,
        channel=template.channel,
        version=template.version,
        isActive=template.isActive,
        title=template.title,
        subject=template.subject,
        body=template.body,
        placeholders=list(template.placeholders()),
        createdAt=template.createdAt,
    )


@dataclass(frozen=True)
class PolicyDto:
    id: str
    policyKey: str
    notificationType: str
    category: str
    enabled: bool
    priority: str
    channels: list[str]
    templateKey: str
    maxAttempts: int
    cooldownSeconds: int
    digestible: bool
    escalation: list[dict[str, Any]]
    allowPreferenceBypass: bool
    description: str


def policyDtoFromDomain(policy: NotificationPolicy) -> PolicyDto:
    return PolicyDto(
        id=str(policy.id),
        policyKey=policy.policyKey,
        notificationType=policy.notificationType,
        category=policy.category,
        enabled=policy.enabled,
        priority=policy.priority,
        channels=list(policy.channels),
        templateKey=policy.templateKey,
        maxAttempts=policy.maxAttempts,
        cooldownSeconds=policy.cooldownSeconds,
        digestible=policy.digestible,
        escalation=[dict(stage) for stage in policy.escalation],
        allowPreferenceBypass=policy.allowPreferenceBypass,
        description=policy.description,
    )


@dataclass(frozen=True)
class DigestDto:
    id: str
    userId: str
    kind: str
    status: str
    itemCount: int
    periodStart: datetime
    periodEnd: datetime
    sentAt: datetime | None


def digestDtoFromDomain(digest: NotificationDigest) -> DigestDto:
    return DigestDto(
        id=str(digest.id),
        userId=str(digest.userId),
        kind=digest.kind,
        status=digest.status,
        itemCount=digest.itemCount,
        periodStart=digest.periodStart,
        periodEnd=digest.periodEnd,
        sentAt=digest.sentAt,
    )


@dataclass(frozen=True)
class ScheduleDto:
    id: str
    kind: str
    notificationType: str
    category: str
    priority: str
    title: str
    status: str
    nextRunAt: datetime | None
    lastRunAt: datetime | None
    recurEverySeconds: int


def scheduleDtoFromDomain(schedule: NotificationSchedule) -> ScheduleDto:
    return ScheduleDto(
        id=str(schedule.id),
        kind=schedule.kind,
        notificationType=schedule.notificationType,
        category=schedule.category,
        priority=schedule.priority,
        title=schedule.title,
        status=schedule.status,
        nextRunAt=schedule.nextRunAt,
        lastRunAt=schedule.lastRunAt,
        recurEverySeconds=schedule.recurEverySeconds,
    )


@dataclass(frozen=True)
class NotificationPageDto:
    items: list[NotificationDto]
    unreadCount: int
    hasNext: bool


def dtoAsDict(value: Any) -> Any:
    """dataclass → JSON-safe structure (datetime → isoformat, UUID → str)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            fieldName: dtoAsDict(getattr(value, fieldName))
            for fieldName in (f.name for f in dataclasses.fields(value))
        }
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [dtoAsDict(item) for item in value]
    if isinstance(value, dict):
        return {key: dtoAsDict(item) for key, item in value.items()}
    return value
