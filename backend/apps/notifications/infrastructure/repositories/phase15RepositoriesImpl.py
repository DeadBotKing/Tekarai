"""Django implementation of Phase 15 notification completion ports."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q

from apps.notifications.infrastructure.models import (
    NotificationAttemptModel,
    NotificationAuditModel,
    NotificationCleanupRunModel,
    NotificationDeliveryModel,
    NotificationDeviceModel,
    NotificationDigestItemModel,
    NotificationDigestModel,
    NotificationEventModel,
    NotificationModel,
    NotificationProviderConfigurationModel,
    NotificationPushSubscriptionModel,
    NotificationRecipientDeliveryModel,
    NotificationRecipientModel,
    NotificationRecordModel,
    NotificationScheduleModel,
    NotificationWebhookReceiptModel,
)
from apps.notifications.infrastructure.repositories.phase12RepositoriesImpl import (
    RecipientDeliveryRepositoryDjango,
)
from apps.notifications.infrastructure.security.secretBox import seal
from apps.sharedKernel.domain.errors import ConflictError, EntityNotFoundError


class NotificationPlatformStoreDjango:
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
    ) -> tuple[dict[str, Any], ...]:
        recipients = NotificationRecipientModel.objects.filter(tenantId=tenantId, userId=userId)
        if readState:
            recipients = recipients.filter(recipientState=readState)
        notificationIds = recipients.values("notificationId")
        rows = NotificationModel.objects.filter(tenantId=tenantId, id__in=notificationIds)
        if query:
            rows = rows.filter(Q(title__icontains=query) | Q(body__icontains=query))
        if notificationType:
            rows = rows.filter(notificationType=notificationType)
        if status:
            rows = rows.filter(status=status)
        if dateFrom:
            rows = rows.filter(createdAt__gte=dateFrom)
        if dateTo:
            rows = rows.filter(createdAt__lte=dateTo)
        if channel:
            deliveredIds = NotificationRecipientDeliveryModel.objects.filter(
                tenantId=tenantId, recipientId=userId, channel=channel
            ).values("notificationId")
            rows = rows.filter(id__in=deliveredIds)
        beforeCreated = None
        if beforeId:
            beforeCreated = (
                NotificationModel.objects.filter(
                    tenantId=tenantId, id=beforeId, id__in=notificationIds
                )
                .values_list("createdAt", flat=True)
                .first()
            )
            if beforeCreated is None:
                beforeCreated = (
                    NotificationRecordModel.objects.filter(
                        tenantId=tenantId, recipientId=userId, id=beforeId
                    )
                    .values_list("createdAt", flat=True)
                    .first()
                )
            if beforeCreated is not None:
                rows = rows.filter(createdAt__lt=beforeCreated)
        selected = list(rows.order_by("-createdAt")[:limit])
        stateMap = {
            row.notificationId: row
            for row in NotificationRecipientModel.objects.filter(
                tenantId=tenantId,
                userId=userId,
                notificationId__in=[item.id for item in selected],
            )
        }
        results = [
            {
                "id": str(item.id),
                "notificationType": item.notificationType,
                "status": item.status,
                "priority": item.priority,
                "title": item.title,
                "body": item.body,
                "deepLink": item.deepLink,
                "payloadVersion": item.payloadVersion,
                "readState": stateMap[item.id].recipientState,
                "readAt": stateMap[item.id].readAt.isoformat()
                if stateMap[item.id].readAt
                else None,
                "createdAt": item.createdAt.isoformat(),
            }
            for item in selected
        ]
        # Phase 9 single-recipient rows remain readable during the canonical
        # Phase 12/15 convergence; search therefore spans both stores.
        legacy = NotificationRecordModel.objects.filter(
            tenantId=tenantId, recipientId=userId, deletedAt__isnull=True
        )
        if query:
            legacy = legacy.filter(Q(title__icontains=query) | Q(body__icontains=query))
        if notificationType:
            legacy = legacy.filter(notificationType=notificationType)
        if status:
            legacy = legacy.filter(status=status)
        if readState == "READ":
            legacy = legacy.filter(readAt__isnull=False)
        elif readState == "UNREAD":
            legacy = legacy.filter(readAt__isnull=True)
        elif readState in ("ARCHIVED", "DISMISSED"):
            legacy = legacy.none()
        if dateFrom:
            legacy = legacy.filter(createdAt__gte=dateFrom)
        if dateTo:
            legacy = legacy.filter(createdAt__lte=dateTo)
        if beforeCreated is not None:
            legacy = legacy.filter(createdAt__lt=beforeCreated)
        if channel:
            legacyDeliveryIds = NotificationDeliveryModel.objects.filter(
                tenantId=tenantId, channel=channel
            ).values("notificationId")
            legacy = legacy.filter(id__in=legacyDeliveryIds)
        results.extend(
            {
                "id": str(item.id),
                "notificationType": item.notificationType,
                "status": item.status,
                "priority": item.priority,
                "title": item.title,
                "body": item.body,
                "deepLink": str((item.payload or {}).get("actionUrl", "")),
                "payloadVersion": int((item.payload or {}).get("version", 1)),
                "readState": "READ" if item.readAt else "UNREAD",
                "readAt": item.readAt.isoformat() if item.readAt else None,
                "createdAt": item.createdAt.isoformat(),
            }
            for item in legacy.order_by("-createdAt")[:limit]
        )
        results.sort(key=lambda item: (item["createdAt"], item["id"]), reverse=True)
        return tuple(results[:limit])

    @transaction.atomic
    def registerSubscription(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        endpoint: str,
        publicKey: str,
        authSecret: str,
        expiresAt: datetime | None,
    ) -> dict[str, Any]:
        endpointHash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        encrypted = seal(
            json.dumps(
                {"endpoint": endpoint, "publicKey": publicKey, "authSecret": authSecret},
                separators=(",", ":"),
            )
        )
        row, _created = NotificationPushSubscriptionModel.objects.update_or_create(
            tenantId=tenantId,
            userId=userId,
            endpointHash=endpointHash,
            defaults={
                "encryptedSubscription": encrypted,
                "expiresAt": expiresAt,
                "isActive": True,
                "revokedAt": None,
            },
        )
        NotificationAuditModel.objects.create(
            tenantId=tenantId,
            eventType="PUSH_SUBSCRIPTION_REGISTERED",
            resourceType="PushSubscription",
            resourceId=str(row.id),
            actorId=userId,
            metadata={"endpointHash": endpointHash},
        )
        return self._subscriptionDto(row)

    def listSubscriptions(
        self, tenantId: uuid.UUID, userId: uuid.UUID
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._subscriptionDto(row)
            for row in NotificationPushSubscriptionModel.objects.filter(
                tenantId=tenantId, userId=userId
            ).order_by("-createdAt")
        )

    def revokeSubscription(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        subscriptionId: uuid.UUID,
        now: datetime,
    ) -> bool:
        updated = NotificationPushSubscriptionModel.objects.filter(
            tenantId=tenantId, userId=userId, id=subscriptionId
        ).update(isActive=False, revokedAt=now)
        if updated:
            NotificationAuditModel.objects.create(
                tenantId=tenantId,
                eventType="PUSH_SUBSCRIPTION_REVOKED",
                resourceType="PushSubscription",
                resourceId=str(subscriptionId),
                actorId=userId,
            )
        return bool(updated)

    @staticmethod
    def _subscriptionDto(row: NotificationPushSubscriptionModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "endpointHash": row.endpointHash,
            "isActive": row.isActive,
            "expiresAt": row.expiresAt.isoformat() if row.expiresAt else None,
            "createdAt": row.createdAt.isoformat(),
        }

    @transaction.atomic
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
    ) -> dict[str, Any]:
        existing = NotificationWebhookReceiptModel.objects.filter(
            tenantId=tenantId, provider=provider, providerEventId=providerEventId
        ).first()
        if existing is not None:
            if existing.payloadHash != payloadHash:
                raise ConflictError("Provider event id is already bound to another payload.")
            return {"processed": False, "duplicate": True, "outcome": existing.outcome}
        repository = RecipientDeliveryRepositoryDjango()
        delivery = repository.findByProviderMessageId(tenantId, provider, providerMessageId)
        if delivery is None:
            raise EntityNotFoundError("NotificationDelivery", providerMessageId)
        delivery.applyProviderCallback(status, now, errorCode=errorCode)
        repository.save(delivery)
        NotificationWebhookReceiptModel.objects.create(
            tenantId=tenantId,
            provider=provider,
            providerEventId=providerEventId,
            payloadHash=payloadHash,
            outcome=status,
        )
        NotificationAuditModel.objects.create(
            tenantId=tenantId,
            eventType=f"NOTIFICATION_{status}",
            resourceType="NotificationDelivery",
            resourceId=str(delivery.id),
            metadata={
                "provider": provider,
                "providerEventId": providerEventId,
                "callback": metadata,
            },
        )
        return {
            "processed": True,
            "duplicate": False,
            "deliveryId": str(delivery.id),
            "outcome": status,
        }

    def saveProviderConfiguration(
        self,
        tenantId: uuid.UUID,
        actorId: uuid.UUID,
        channel: str,
        provider: str,
        credentialRef: str,
        configuration: dict[str, Any],
        isActive: bool,
    ) -> dict[str, Any]:
        row, _created = NotificationProviderConfigurationModel.objects.update_or_create(
            tenantId=tenantId,
            channel=channel,
            provider=provider,
            defaults={
                "credentialRef": credentialRef,
                "configuration": configuration,
                "isActive": isActive,
                "createdById": actorId,
            },
        )
        NotificationAuditModel.objects.create(
            tenantId=tenantId,
            eventType="PROVIDER_CHANGED",
            resourceType="NotificationProvider",
            resourceId=str(row.id),
            actorId=actorId,
            metadata={"channel": channel, "provider": provider, "active": isActive},
        )
        return self._providerDto(row)

    def listProviderConfigurations(self, tenantId: uuid.UUID) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._providerDto(row)
            for row in NotificationProviderConfigurationModel.objects.filter(
                tenantId=tenantId
            ).order_by("channel", "provider")
        )

    @staticmethod
    def _providerDto(row: NotificationProviderConfigurationModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "channel": row.channel,
            "provider": row.provider,
            "credentialRef": row.credentialRef,
            "configuration": dict(row.configuration or {}),
            "isActive": row.isActive,
        }

    @transaction.atomic
    def cleanup(
        self,
        tenantId: uuid.UUID,
        actorId: uuid.UUID,
        cutoff: datetime,
        *,
        dryRun: bool,
    ) -> dict[str, int]:
        terminal = ("DELIVERED", "READ", "FAILED", "CANCELLED", "EXPIRED")
        oldNotifications = NotificationModel.objects.filter(
            tenantId=tenantId, createdAt__lt=cutoff, status__in=terminal
        )
        notificationIds = list(oldNotifications.values_list("id", flat=True))
        deliveryIds = list(
            NotificationRecipientDeliveryModel.objects.filter(
                tenantId=tenantId, notificationId__in=notificationIds
            ).values_list("id", flat=True)
        )
        oldSingle = NotificationRecordModel.objects.filter(
            tenantId=tenantId, createdAt__lt=cutoff, status__in=terminal
        )
        oldDigests = NotificationDigestModel.objects.filter(
            tenantId=tenantId, periodEnd__lt=cutoff
        ).exclude(status="OPEN")
        digestIds = list(oldDigests.values_list("id", flat=True))
        oldDevices = NotificationDeviceModel.objects.filter(
            tenantId=tenantId, isActive=False, revokedAt__lt=cutoff
        )
        oldSubscriptions = NotificationPushSubscriptionModel.objects.filter(
            tenantId=tenantId, isActive=False, revokedAt__lt=cutoff
        )
        oldSchedules = NotificationScheduleModel.objects.filter(
            tenantId=tenantId, updatedAt__lt=cutoff, status__in=("COMPLETED", "CANCELLED")
        )
        oldEvents = NotificationEventModel.objects.filter(
            tenantId=tenantId, createdAt__lt=cutoff, processed=True
        )
        counts = {
            "notifications": len(notificationIds),
            "recipients": NotificationRecipientModel.objects.filter(
                tenantId=tenantId, notificationId__in=notificationIds
            ).count(),
            "deliveries": len(deliveryIds),
            "attempts": NotificationAttemptModel.objects.filter(
                tenantId=tenantId, deliveryId__in=deliveryIds
            ).count(),
            "legacyNotifications": oldSingle.count(),
            "legacyDeliveries": NotificationDeliveryModel.objects.filter(
                tenantId=tenantId,
                notificationId__in=oldSingle.values("id"),
            ).count(),
            "digests": len(digestIds),
            "revokedDevices": oldDevices.count(),
            "revokedSubscriptions": oldSubscriptions.count(),
            "schedules": oldSchedules.count(),
            "processedEvents": oldEvents.count(),
        }
        if not dryRun:
            NotificationAttemptModel.objects.filter(
                tenantId=tenantId, deliveryId__in=deliveryIds
            ).delete()
            NotificationRecipientDeliveryModel.objects.filter(
                tenantId=tenantId, notificationId__in=notificationIds
            ).delete()
            NotificationRecipientModel.objects.filter(
                tenantId=tenantId, notificationId__in=notificationIds
            ).delete()
            oldNotifications.delete()
            NotificationDeliveryModel.objects.filter(
                tenantId=tenantId, notificationId__in=oldSingle.values("id")
            ).delete()
            oldSingle.delete()
            NotificationDigestItemModel.objects.filter(
                tenantId=tenantId, digestId__in=digestIds
            ).delete()
            oldDigests.delete()
            oldDevices.delete()
            oldSubscriptions.delete()
            oldSchedules.delete()
            oldEvents.delete()
        NotificationCleanupRunModel.objects.create(
            tenantId=tenantId,
            requestedById=actorId,
            dryRun=dryRun,
            cutoff=cutoff,
            counts=counts,
        )
        # NotificationAudit is intentionally retained under its separate policy.
        return counts


class SettingsWebhookSecretProvider:
    def secretFor(self, tenantId: uuid.UUID, provider: str) -> str:
        from django.conf import settings

        mapping = getattr(settings, "NOTIFICATION_WEBHOOK_SECRETS", {})
        return str(mapping.get(f"{tenantId}:{provider}") or mapping.get(provider) or "")


__all__ = ["NotificationPlatformStoreDjango", "SettingsWebhookSecretProvider"]
