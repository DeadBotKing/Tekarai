"""Notification repositories over Django ORM (Phase 09 §39).

The domain/application layers see only the repository Protocols; every
ORM detail stops here. Mapping helpers keep rows and entities separate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable

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
from apps.notifications.infrastructure.models import (
    NotificationDeliveryModel,
    NotificationDeviceModel,
    NotificationDigestItemModel,
    NotificationDigestModel,
    NotificationPolicyChannelModel,
    NotificationPolicyModel,
    NotificationPreferenceModel,
    NotificationPreferenceRuleModel,
    NotificationRecordModel,
    NotificationScheduleModel,
    NotificationTemplateModel,
    NotificationTemplateVersionModel,
)

# --------------------------------------------------------------------------- #
# mapping helpers
# --------------------------------------------------------------------------- #


def notificationFromRow(row: NotificationRecordModel) -> Notification:
    return Notification(
        id=row.id,
        tenantId=row.tenantId,
        recipientId=row.recipientId,
        notificationType=row.notificationType,
        category=row.category,
        title=row.title,
        body=row.body,
        priority=row.priority,
        sourceType=row.sourceType,
        sourceId=row.sourceId,
        createdAt=row.createdAt,
        scheduledAt=row.scheduledAt,
        expiresAt=row.expiresAt,
        readAt=row.readAt,
        acknowledgedAt=row.acknowledgedAt,
        status=row.status,
        idempotencyKey=row.idempotencyKey,
        requiresAcknowledgement=row.requiresAcknowledgement,
        language=row.language,
        correlationId=row.correlationId,
        causationId=row.causationId,
        payload=dict(row.payload or {}),
        deletedAt=row.deletedAt,
    )


def applyNotificationToRow(notification: Notification, row: NotificationRecordModel) -> None:
    row.status = notification.status
    row.readAt = notification.readAt
    row.acknowledgedAt = notification.acknowledgedAt
    row.deletedAt = notification.deletedAt
    row.expiresAt = notification.expiresAt
    row.payload = notification.payload
    row.language = notification.language


def deliveryFromRow(row: NotificationDeliveryModel) -> NotificationDelivery:
    return NotificationDelivery(
        id=row.id,
        tenantId=row.tenantId,
        notificationId=row.notificationId,
        channel=row.channel,
        provider=row.provider,
        status=row.status,
        attemptCount=row.attemptCount,
        maxAttempts=row.maxAttempts,
        lastAttemptAt=row.lastAttemptAt,
        nextAttemptAt=row.nextAttemptAt,
        deliveredAt=row.deliveredAt,
        failedAt=row.failedAt,
        errorCode=row.errorCode,
        errorMessage=row.errorMessage,
        createdAt=row.createdAt,
    )


def applyDeliveryToRow(delivery: NotificationDelivery, row: NotificationDeliveryModel) -> None:
    row.status = delivery.status
    row.attemptCount = delivery.attemptCount
    row.maxAttempts = delivery.maxAttempts
    row.lastAttemptAt = delivery.lastAttemptAt
    row.nextAttemptAt = delivery.nextAttemptAt
    row.deliveredAt = delivery.deliveredAt
    row.failedAt = delivery.failedAt
    row.errorCode = delivery.errorCode
    row.errorMessage = delivery.errorMessage
    row.provider = delivery.provider


def digestFromRow(row: NotificationDigestModel) -> NotificationDigest:
    return NotificationDigest(
        id=row.id,
        tenantId=row.tenantId,
        userId=row.userId,
        kind=row.kind,
        periodStart=row.periodStart,
        periodEnd=row.periodEnd,
        status=row.status,
        itemCount=row.itemCount,
        sentAt=row.sentAt,
    )


def scheduleFromRow(row: NotificationScheduleModel) -> NotificationSchedule:
    return NotificationSchedule(
        id=row.id,
        tenantId=row.tenantId,
        kind=row.kind,
        recipientSpec=dict(row.recipientSpec or {}),
        notificationType=row.notificationType,
        category=row.category,
        priority=row.priority,
        title=row.title,
        body=row.body,
        sourceType=row.sourceType,
        sourceId=row.sourceId,
        scheduledAt=row.scheduledAt,
        recurEverySeconds=row.recurEverySeconds,
        status=row.status,
        lastRunAt=row.lastRunAt,
        nextRunAt=row.nextRunAt,
        expiresAt=row.expiresAt,
        payload=dict(row.payload or {}),
        correlationId=row.correlationId,
    )


# --------------------------------------------------------------------------- #
# §39 repositories
# --------------------------------------------------------------------------- #


class NotificationRepositoryDjango:
    def create(self, notification: Notification) -> None:
        NotificationRecordModel.objects.create(
            id=notification.id,
            tenantId=notification.tenantId,
            recipientId=notification.recipientId,
            notificationType=notification.notificationType,
            category=notification.category,
            priority=notification.priority,
            title=notification.title,
            body=notification.body,
            status=notification.status,
            sourceType=notification.sourceType,
            sourceId=notification.sourceId,
            idempotencyKey=notification.idempotencyKey,
            requiresAcknowledgement=notification.requiresAcknowledgement,
            language=notification.language,
            correlationId=notification.correlationId,
            causationId=notification.causationId,
            payload=notification.payload,
            createdAt=notification.createdAt,
            scheduledAt=notification.scheduledAt,
            expiresAt=notification.expiresAt,
            readAt=notification.readAt,
            acknowledgedAt=notification.acknowledgedAt,
            deletedAt=notification.deletedAt,
        )

    def update(self, notification: Notification) -> None:
        row = NotificationRecordModel.objects.get(id=notification.id)
        applyNotificationToRow(notification, row)
        row.save()

    def getById(
        self, notificationId: uuid.UUID | str, tenantId: uuid.UUID | None = None
    ) -> Notification | None:
        try:
            query = NotificationRecordModel.objects.filter(id=notificationId)
            if tenantId is not None:
                query = query.filter(tenantId=tenantId)
            row = query.get()
        except NotificationRecordModel.DoesNotExist:
            return None
        return notificationFromRow(row)

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, idempotencyKey: str
    ) -> Notification | None:
        row = (
            NotificationRecordModel.objects.filter(
                tenantId=tenantId, idempotencyKey=idempotencyKey
            )
            .order_by("createdAt")
            .first()
        )
        return notificationFromRow(row) if row else None

    def lastCreatedAtOfType(
        self, tenantId: uuid.UUID, recipientId: uuid.UUID, notificationType: str
    ) -> datetime | None:
        row = (
            NotificationRecordModel.objects.filter(
                tenantId=tenantId,
                recipientId=recipientId,
                notificationType=notificationType,
            )
            .order_by("-createdAt")
            .first()
        )
        return row.createdAt if row else None

    def countRecentOfType(
        self,
        tenantId: uuid.UUID,
        recipientId: uuid.UUID,
        notificationType: str,
        since: datetime,
    ) -> int:
        return NotificationRecordModel.objects.filter(
            tenantId=tenantId,
            recipientId=recipientId,
            notificationType=notificationType,
            createdAt__gte=since,
        ).count()

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
    ) -> tuple[list[Notification], int, bool]:
        query = NotificationRecordModel.objects.filter(
            tenantId=tenantId, recipientId=recipientId
        )
        if not includeArchived:
            query = query.filter(deletedAt__isnull=True)
        if unreadOnly:
            query = query.filter(readAt__isnull=True)
        if category:
            query = query.filter(category=category)
        if priority:
            query = query.filter(priority=priority)
        if beforeId is not None:
            anchor = NotificationRecordModel.objects.filter(id=beforeId).first()
            if anchor is not None:
                query = query.filter(createdAt__lt=anchor.createdAt)
        rows = list(query.order_by("-createdAt")[: limit + 1])
        hasNext = len(rows) > limit
        rows = rows[:limit]
        unreadCount = NotificationRecordModel.objects.filter(
            tenantId=tenantId,
            recipientId=recipientId,
            deletedAt__isnull=True,
            readAt__isnull=True,
        ).count()
        return [notificationFromRow(row) for row in rows], unreadCount, hasNext

    def listDispatchable(
        self, tenantId: uuid.UUID | None, *, limit: int = 100
    ) -> list[Notification]:
        from apps.notifications.domain.valueObjects.notificationTypes import (
            NOTIFICATION_DISPATCHABLE,
        )

        query = NotificationRecordModel.objects.filter(
            status__in=NOTIFICATION_DISPATCHABLE, deletedAt__isnull=True
        )
        if tenantId is not None:
            query = query.filter(tenantId=tenantId)
        rows = query.order_by("createdAt")[:limit]
        return [notificationFromRow(row) for row in rows]

    def listExpiredUndelivered(self, now: datetime, *, limit: int = 200) -> list[Notification]:
        from apps.notifications.domain.valueObjects.notificationTypes import (
            NOTIFICATION_DISPATCHABLE,
        )

        rows = NotificationRecordModel.objects.filter(
            status__in=NOTIFICATION_DISPATCHABLE,
            expiresAt__isnull=False,
            expiresAt__lte=now,
        ).order_by("expiresAt")[:limit]
        return [notificationFromRow(row) for row in rows]

    def listDigestible(
        self, tenantId: uuid.UUID, userId: uuid.UUID, since: datetime, until: datetime
    ) -> list[Notification]:
        rows = NotificationRecordModel.objects.filter(
            tenantId=tenantId,
            recipientId=userId,
            createdAt__gte=since,
            createdAt__lte=until,
            deletedAt__isnull=True,
        ).order_by("createdAt")
        return [notificationFromRow(row) for row in rows]

    def unreadCount(self, tenantId: uuid.UUID, recipientId: uuid.UUID) -> int:
        return NotificationRecordModel.objects.filter(
            tenantId=tenantId,
            recipientId=recipientId,
            deletedAt__isnull=True,
            readAt__isnull=True,
        ).count()

    def readAndAckCounts(
        self, tenantId: uuid.UUID, recipientId: uuid.UUID
    ) -> tuple[int, int, int]:
        base = NotificationRecordModel.objects.filter(
            tenantId=tenantId, recipientId=recipientId, deletedAt__isnull=True
        )
        total = base.count()
        read = base.filter(readAt__isnull=False).count()
        acknowledged = base.filter(acknowledgedAt__isnull=False).count()
        return total, read, acknowledged


class NotificationDeliveryRepositoryDjango:
    def create(self, delivery: NotificationDelivery) -> None:
        NotificationDeliveryModel.objects.create(
            id=delivery.id,
            tenantId=delivery.tenantId,
            notificationId=delivery.notificationId,
            channel=delivery.channel,
            provider=delivery.provider,
            status=delivery.status,
            attemptCount=delivery.attemptCount,
            maxAttempts=delivery.maxAttempts,
            lastAttemptAt=delivery.lastAttemptAt,
            nextAttemptAt=delivery.nextAttemptAt,
            deliveredAt=delivery.deliveredAt,
            failedAt=delivery.failedAt,
            errorCode=delivery.errorCode,
            errorMessage=delivery.errorMessage,
            createdAt=delivery.createdAt,
        )

    def update(self, delivery: NotificationDelivery) -> None:
        row = NotificationDeliveryModel.objects.get(id=delivery.id)
        applyDeliveryToRow(delivery, row)
        row.save()

    def getForNotification(
        self, notificationId: uuid.UUID
    ) -> list[NotificationDelivery]:
        rows = NotificationDeliveryModel.objects.filter(
            notificationId=notificationId
        ).order_by("channel")
        return [deliveryFromRow(row) for row in rows]

    def listPendingRetry(self, now: datetime, *, limit: int = 100) -> list[NotificationDelivery]:
        from apps.notifications.domain.valueObjects.notificationTypes import (
            DELIVERY_RETRY_SCHEDULED,
        )

        rows = NotificationDeliveryModel.objects.filter(
            status=DELIVERY_RETRY_SCHEDULED, nextAttemptAt__lte=now
        ).order_by("nextAttemptAt")[:limit]
        return [deliveryFromRow(row) for row in rows]

    def channelUsageCounts(self, tenantId: uuid.UUID) -> dict[str, int]:
        from django.db.models import Count

        rows = NotificationDeliveryModel.objects.filter(tenantId=tenantId).values(
            "channel"
        ).annotate(total=Count("id"))
        return {str(row["channel"]): int(row["total"]) for row in rows}


class NotificationPreferenceRepositoryDjango:
    def save(self, preference: NotificationPreference) -> None:
        NotificationPreferenceModel.objects.update_or_create(
            userId=preference.userId,
            level=preference.level,
            category=preference.category,
            notificationType=preference.notificationType,
            channel=preference.channel,
            defaults={
                "tenantId": preference.tenantId,
                "enabled": preference.enabled,
                "quietHoursStart": preference.quietHoursStart,
                "quietHoursEnd": preference.quietHoursEnd,
            },
        )

    def replaceForUser(self, userId: uuid.UUID, rows: list[NotificationPreference]) -> None:
        NotificationPreferenceModel.objects.filter(userId=userId).delete()
        for preference in rows:
            NotificationPreferenceModel.objects.create(
                id=preference.id,
                tenantId=preference.tenantId,
                userId=preference.userId,
                level=preference.level,
                category=preference.category,
                notificationType=preference.notificationType,
                channel=preference.channel,
                enabled=preference.enabled,
                quietHoursStart=preference.quietHoursStart,
                quietHoursEnd=preference.quietHoursEnd,
            )

    def listForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID
    ) -> list[NotificationPreference]:
        rows = NotificationPreferenceModel.objects.filter(
            tenantId=tenantId, userId=userId
        )
        return [
            NotificationPreference(
                id=row.id,
                tenantId=row.tenantId,
                userId=row.userId,
                level=row.level,
                channel=row.channel,
                category=row.category,
                notificationType=row.notificationType,
                enabled=row.enabled,
                quietHoursStart=row.quietHoursStart,
                quietHoursEnd=row.quietHoursEnd,
            )
            for row in rows
        ]

    def saveRule(self, rule: NotificationPreferenceRule) -> None:
        """Upsert keeping the caller's id stable (delete uses that id)."""
        existing = NotificationPreferenceRuleModel.objects.filter(
            tenantId=rule.tenantId,
            channel=rule.channel,
            action=rule.action,
            category=rule.category,
            notificationType=rule.notificationType,
        ).first()
        if existing is not None:
            existing.description = rule.description
            existing.save()
            return
        NotificationPreferenceRuleModel.objects.create(
            id=rule.id,
            tenantId=rule.tenantId,
            channel=rule.channel,
            action=rule.action,
            category=rule.category,
            notificationType=rule.notificationType,
            description=rule.description,
        )

    def deleteRule(self, ruleId: uuid.UUID) -> bool:
        deleted, _ = NotificationPreferenceRuleModel.objects.filter(id=ruleId).delete()
        return deleted > 0

    def listRules(self, tenantId: uuid.UUID) -> list[NotificationPreferenceRule]:
        rows = NotificationPreferenceRuleModel.objects.filter(tenantId=tenantId)
        return [
            NotificationPreferenceRule(
                id=row.id,
                tenantId=row.tenantId,
                channel=row.channel,
                action=row.action,
                category=row.category,
                notificationType=row.notificationType,
                description=row.description,
            )
            for row in rows
        ]


class NotificationTemplateRepositoryDjango:
    """§19 — the templates table holds the ACTIVE row; every write also
    appends an immutable row to the versions table."""

    def create(self, template: NotificationTemplate) -> None:
        row = NotificationTemplateModel.objects.create(
            id=template.id,
            tenantId=template.tenantId,
            templateKey=template.templateKey,
            language=template.language,
            channel=template.channel,
            version=template.version,
            title=template.title,
            subject=template.subject,
            body=template.body,
            isActive=template.isActive,
            createdBy=template.createdBy,
            createdAt=template.createdAt,
        )
        NotificationTemplateVersionModel.objects.create(
            templateId=row.id,
            tenantId=template.tenantId,
            templateKey=template.templateKey,
            language=template.language,
            channel=template.channel,
            version=template.version,
            title=template.title,
            subject=template.subject,
            body=template.body,
            isActive=template.isActive,
            createdBy=template.createdBy,
            createdAt=template.createdAt,
        )

    def deactivate(self, templateId: uuid.UUID) -> None:
        NotificationTemplateModel.objects.filter(id=templateId).update(isActive=False)

    def _activeQuery(
        self, tenantId: uuid.UUID, templateKey: str, language: str, channel: str
    ):
        return NotificationTemplateModel.objects.filter(
            tenantId=tenantId,
            templateKey=templateKey,
            language=language,
            channel=channel,
            isActive=True,
        )

    def findActive(
        self, tenantId: uuid.UUID, templateKey: str, language: str, channel: str
    ) -> NotificationTemplate | None:
        row = self._activeQuery(tenantId, templateKey, language, channel).first()
        return self._templateFromRow(row) if row else None

    def listVersions(
        self, tenantId: uuid.UUID, templateKey: str, language: str, channel: str
    ) -> list[NotificationTemplate]:
        rows = self._activeQuery(tenantId, templateKey, language, channel).order_by(
            "-version"
        )
        return [self._templateFromRow(row) for row in rows]

    def listAll(self, tenantId: uuid.UUID) -> list[NotificationTemplate]:
        rows = NotificationTemplateModel.objects.filter(
            tenantId=tenantId, isActive=True
        ).order_by("templateKey", "language", "channel")
        return [self._templateFromRow(row) for row in rows]

    @staticmethod
    def _templateFromRow(row: NotificationTemplateModel) -> NotificationTemplate:
        return NotificationTemplate(
            id=row.id,
            tenantId=row.tenantId,
            templateKey=row.templateKey,
            language=row.language,
            channel=row.channel,
            version=row.version,
            title=row.title,
            subject=row.subject,
            body=row.body,
            isActive=row.isActive,
            createdAt=row.createdAt,
            createdBy=row.createdBy,
        )


class NotificationPolicyRepositoryDjango:
    def create(self, policy: NotificationPolicy) -> None:
        row = NotificationPolicyModel.objects.create(
            id=policy.id,
            tenantId=policy.tenantId,
            policyKey=policy.policyKey,
            notificationType=policy.notificationType,
            category=policy.category,
            enabled=policy.enabled,
            priority=policy.priority,
            templateKey=policy.templateKey,
            maxAttempts=policy.maxAttempts,
            cooldownSeconds=policy.cooldownSeconds,
            digestible=policy.digestible,
            escalation=policy.escalation,
            allowPreferenceBypass=policy.allowPreferenceBypass,
            description=policy.description,
        )
        self._syncChannels(row, policy)

    def update(self, policy: NotificationPolicy) -> None:
        row = NotificationPolicyModel.objects.get(id=policy.id)
        row.policyKey = policy.policyKey
        row.notificationType = policy.notificationType
        row.category = policy.category
        row.enabled = policy.enabled
        row.priority = policy.priority
        row.templateKey = policy.templateKey
        row.maxAttempts = policy.maxAttempts
        row.cooldownSeconds = policy.cooldownSeconds
        row.digestible = policy.digestible
        row.escalation = policy.escalation
        row.allowPreferenceBypass = policy.allowPreferenceBypass
        row.description = policy.description
        row.save()
        self._syncChannels(row, policy)

    @staticmethod
    def _syncChannels(row: NotificationPolicyModel, policy: NotificationPolicy) -> None:
        from apps.notifications.infrastructure.models import (
            NotificationPolicyChannelModel,
        )

        NotificationPolicyChannelModel.objects.filter(policyId=row.id).delete()
        for channel in policy.channels:
            NotificationPolicyChannelModel.objects.create(
                tenantId=row.tenantId, policyId=row.id, channel=channel, enabled=True
            )

    def getById(self, policyId: uuid.UUID) -> NotificationPolicy | None:
        row = NotificationPolicyModel.objects.filter(id=policyId).first()
        return self._policyFromRow(row) if row else None

    def findByKey(self, tenantId: uuid.UUID, policyKey: str) -> NotificationPolicy | None:
        row = NotificationPolicyModel.objects.filter(
            tenantId=tenantId, policyKey=policyKey
        ).first()
        return self._policyFromRow(row) if row else None

    def findApplicable(
        self, tenantId: uuid.UUID, notificationType: str, category: str
    ) -> NotificationPolicy | None:
        """§8 — type match beats category match (most specific wins)."""
        rows = NotificationPolicyModel.objects.filter(
            tenantId=tenantId, enabled=True
        ).order_by("policyKey")
        typeRow = rows.filter(notificationType=notificationType).first()
        if typeRow is not None:
            return self._policyFromRow(typeRow)
        categoryRow = rows.filter(
            notificationType="", category=category
        ).first()
        if categoryRow is not None:
            return self._policyFromRow(categoryRow)
        return None

    def listAll(self, tenantId: uuid.UUID) -> list[NotificationPolicy]:
        rows = NotificationPolicyModel.objects.filter(tenantId=tenantId).order_by(
            "policyKey"
        )
        return [self._policyFromRow(row) for row in rows]

    def delete(self, policyId: uuid.UUID) -> bool:
        deleted, _ = NotificationPolicyModel.objects.filter(id=policyId).delete()
        return deleted > 0

    def _policyFromRow(self, row: NotificationPolicyModel) -> NotificationPolicy:
        channels = tuple(
            sorted(
                NotificationPolicyChannelModel.objects.filter(
                    policyId=row.id, enabled=True
                ).values_list("channel", flat=True)
            )
        )
        return NotificationPolicy(
            id=row.id,
            tenantId=row.tenantId,
            policyKey=row.policyKey,
            notificationType=row.notificationType,
            category=row.category,
            enabled=row.enabled,
            priority=row.priority,
            channels=channels or ("IN_APP",),
            templateKey=row.templateKey,
            maxAttempts=row.maxAttempts,
            cooldownSeconds=row.cooldownSeconds,
            digestible=row.digestible,
            escalation=list(row.escalation or []),
            allowPreferenceBypass=row.allowPreferenceBypass,
            description=row.description,
        )


class NotificationDeviceRepositoryDjango:
    def create(self, device: NotificationDevice) -> None:
        NotificationDeviceModel.objects.create(
            id=device.id,
            tenantId=device.tenantId,
            userId=device.userId,
            platform=device.platform,
            deviceIdentifier=device.deviceIdentifier,
            pushToken=device.pushToken,
            provider=device.provider,
            isActive=device.isActive,
            createdAt=device.createdAt,
            lastSeenAt=device.lastSeenAt,
            revokedAt=device.revokedAt,
        )

    def update(self, device: NotificationDevice) -> None:
        NotificationDeviceModel.objects.filter(id=device.id).update(
            pushToken=device.pushToken,
            provider=device.provider,
            isActive=device.isActive,
            lastSeenAt=device.lastSeenAt,
            revokedAt=device.revokedAt,
        )

    def getById(self, deviceId: uuid.UUID) -> NotificationDevice | None:
        row = NotificationDeviceModel.objects.filter(id=deviceId).first()
        return self._deviceFromRow(row) if row else None

    def findByIdentifier(
        self, tenantId: uuid.UUID, userId: uuid.UUID, deviceIdentifier: str
    ) -> NotificationDevice | None:
        row = NotificationDeviceModel.objects.filter(
            tenantId=tenantId, userId=userId, deviceIdentifier=deviceIdentifier
        ).first()
        return self._deviceFromRow(row) if row else None

    def listForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID, *, activeOnly: bool = False
    ) -> list[NotificationDevice]:
        query = NotificationDeviceModel.objects.filter(tenantId=tenantId, userId=userId)
        if activeOnly:
            query = query.filter(isActive=True, revokedAt__isnull=True)
        rows = query.order_by("-createdAt")
        return [self._deviceFromRow(row) for row in rows]

    def activeForUser(self, tenantId: uuid.UUID, userId: uuid.UUID) -> list[NotificationDevice]:
        return self.listForUser(tenantId, userId, activeOnly=True)

    @staticmethod
    def _deviceFromRow(row: NotificationDeviceModel) -> NotificationDevice:
        return NotificationDevice(
            id=row.id,
            tenantId=row.tenantId,
            userId=row.userId,
            platform=row.platform,
            deviceIdentifier=row.deviceIdentifier,
            pushToken=row.pushToken,
            provider=row.provider,
            createdAt=row.createdAt,
            lastSeenAt=row.lastSeenAt,
            revokedAt=row.revokedAt,
            isActive=row.isActive,
        )


class NotificationDigestRepositoryDjango:
    def create(self, digest: NotificationDigest) -> None:
        NotificationDigestModel.objects.create(
            id=digest.id,
            tenantId=digest.tenantId,
            userId=digest.userId,
            kind=digest.kind,
            status=digest.status,
            itemCount=digest.itemCount,
            periodStart=digest.periodStart,
            periodEnd=digest.periodEnd,
            sentAt=digest.sentAt,
        )

    def update(self, digest: NotificationDigest) -> None:
        NotificationDigestModel.objects.filter(id=digest.id).update(
            status=digest.status,
            itemCount=digest.itemCount,
            sentAt=digest.sentAt,
        )

    def openDigest(
        self, tenantId: uuid.UUID, userId: uuid.UUID, kind: str
    ) -> NotificationDigest | None:
        from apps.notifications.domain.valueObjects.notificationTypes import (
            DIGEST_STATUS_OPEN,
        )

        row = NotificationDigestModel.objects.filter(
            tenantId=tenantId, userId=userId, kind=kind, status=DIGEST_STATUS_OPEN
        ).first()
        return digestFromRow(row) if row else None

    def addItem(self, digestId: uuid.UUID, notificationId: uuid.UUID) -> None:
        digestRow = NotificationDigestModel.objects.filter(id=digestId).first()
        if digestRow is None:
            return
        NotificationDigestItemModel.objects.get_or_create(
            digestId=digestId,
            notificationId=notificationId,
            defaults={"tenantId": digestRow.tenantId},
        )

    def itemsOf(self, digestId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            NotificationDigestItemModel.objects.filter(digestId=digestId)
            .order_by("addedAt")
            .values_list("notificationId", flat=True)
        )


def dueOpenDigests(kind: str, now: datetime) -> list[NotificationDigest]:
    """§21 — open digests whose window elapsed (kind filter optional)."""
    from apps.notifications.domain.valueObjects.notificationTypes import (
        DIGEST_STATUS_OPEN,
    )

    query = NotificationDigestModel.objects.filter(
        status=DIGEST_STATUS_OPEN, periodEnd__lte=now
    )
    if kind:
        query = query.filter(kind=kind)
    rows = query.order_by("periodEnd")[:200]
    return [digestFromRow(row) for row in rows]


class NotificationScheduleRepositoryDjango:
    def create(self, schedule: NotificationSchedule) -> None:
        NotificationScheduleModel.objects.create(
            id=schedule.id,
            tenantId=schedule.tenantId,
            kind=schedule.kind,
            status=schedule.status,
            recipientSpec=schedule.recipientSpec,
            notificationType=schedule.notificationType,
            category=schedule.category,
            priority=schedule.priority,
            title=schedule.title,
            body=schedule.body,
            sourceType=schedule.sourceType,
            sourceId=schedule.sourceId,
            payload=schedule.payload,
            correlationId=schedule.correlationId,
            scheduledAt=schedule.scheduledAt,
            nextRunAt=schedule.nextRunAt,
            recurEverySeconds=schedule.recurEverySeconds,
            expiresAt=schedule.expiresAt,
        )

    def update(self, schedule: NotificationSchedule) -> None:
        NotificationScheduleModel.objects.filter(id=schedule.id).update(
            status=schedule.status,
            nextRunAt=schedule.nextRunAt,
            lastRunAt=schedule.lastRunAt,
        )

    def getById(self, scheduleId: uuid.UUID) -> NotificationSchedule | None:
        row = NotificationScheduleModel.objects.filter(id=scheduleId).first()
        return scheduleFromRow(row) if row else None

    def listDue(self, now: datetime, *, limit: int = 100) -> list[NotificationSchedule]:
        from apps.notifications.domain.valueObjects.notificationTypes import (
            SCHEDULE_PENDING,
        )

        rows = NotificationScheduleModel.objects.filter(
            status=SCHEDULE_PENDING, nextRunAt__lte=now
        ).order_by("nextRunAt")[:limit]
        return [scheduleFromRow(row) for row in rows]

    def listAll(self, tenantId: uuid.UUID) -> list[NotificationSchedule]:
        rows = NotificationScheduleModel.objects.filter(tenantId=tenantId).order_by(
            "-createdAt"
        )[:200]
        return [scheduleFromRow(row) for row in rows]
