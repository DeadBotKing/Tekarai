"""Phase 15 completion services for search, web push, callbacks and cleanup."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from apps.notifications.application.commands.phase15Commands import (
    ProcessProviderWebhookCommand,
    RegisterPushSubscriptionCommand,
    RevokePushSubscriptionCommand,
    RunNotificationCleanupCommand,
    SaveProviderConfigurationCommand,
    SearchNotificationsQuery,
)
from apps.notifications.application.services.notificationSupport import NotificationUseCase
from apps.notifications.domain.repositories.phase15Repositories import (
    NotificationPlatformStore,
    WebhookSecretProvider,
)
from apps.notifications.domain.valueObjects.phase15Types import (
    NOTIFICATION_STATUSES,
    PROVIDER_CALLBACK_STATUSES,
    PROVIDER_CHANNELS,
    canonicalPayloadHash,
    sanitizedMetadata,
    validateIsoDateRange,
    verifyWebhookSignature,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError
from apps.sharedKernel.domain.valueObjects import asUuid


def actor() -> tuple[uuid.UUID, uuid.UUID]:
    context = currentContext()
    return asUuid(context.actorId), asUuid(context.actorTenantId)


class SearchNotificationsService(NotificationUseCase):
    requiredAction = ""

    def __init__(self, store: NotificationPlatformStore, **kernel: Any) -> None:
        super().__init__(**kernel)
        self.store = store

    def perform(self, command: SearchNotificationsQuery) -> tuple[dict[str, Any], ...]:
        actorId, tenantId = actor()
        if command.limit < 1 or command.limit > 200:
            raise ValidationFailedError("Search limit must be between 1 and 200.")
        text = command.query.strip()
        if text and len(text) < 2:
            raise ValidationFailedError("Search text must be empty or at least 2 characters.")
        status = command.status.strip().upper()
        if status and status not in NOTIFICATION_STATUSES:
            raise ValidationFailedError("Notification status filter is invalid.")
        readState = command.readState.strip().upper()
        if readState and readState not in ("READ", "UNREAD", "ARCHIVED", "DISMISSED"):
            raise ValidationFailedError("Notification read-state filter is invalid.")
        channel = command.channel.strip().upper()
        if channel and channel not in (*PROVIDER_CHANNELS, "IN_APP", "WEBSOCKET"):
            raise ValidationFailedError("Notification channel filter is invalid.")
        validateIsoDateRange(command.dateFrom, command.dateTo)
        return self.store.search(
            tenantId,
            actorId,
            query=text,
            notificationType=command.notificationType.strip(),
            status=status,
            readState=readState,
            channel=channel,
            dateFrom=command.dateFrom,
            dateTo=command.dateTo,
            beforeId=asUuid(command.beforeId) if command.beforeId else None,
            limit=command.limit,
        )


class PushSubscriptionService(NotificationUseCase):
    requiredAction = ""

    def __init__(self, store: NotificationPlatformStore, **kernel: Any) -> None:
        super().__init__(**kernel)
        self.store = store

    def perform(self, command: Any) -> Any:
        actorId, tenantId = actor()
        if isinstance(command, RegisterPushSubscriptionCommand):
            endpoint = command.endpoint.strip()
            if not endpoint.startswith("https://") or len(endpoint) > 2000:
                raise ValidationFailedError("Web Push endpoint must be an HTTPS URL.")
            if not command.publicKey.strip() or not command.authSecret.strip():
                raise ValidationFailedError("Web Push keys are required.")
            if command.expiresAt is not None and command.expiresAt <= self.clock.nowUtc():
                raise ValidationFailedError("Web Push expiration must be in the future.")
            result = self.store.registerSubscription(
                tenantId,
                actorId,
                endpoint,
                command.publicKey,
                command.authSecret,
                command.expiresAt,
            )
            self.audit(
                "CREATE",
                "PushSubscription",
                result["id"],
                tenantId,
                after={"endpointHash": result["endpointHash"]},
            )
            return result
        if isinstance(command, RevokePushSubscriptionCommand):
            identifier = asUuid(command.subscriptionId)
            if not self.store.revokeSubscription(
                tenantId, actorId, identifier, self.clock.nowUtc()
            ):
                raise EntityNotFoundError("PushSubscription", command.subscriptionId)
            self.audit("DELETE", "PushSubscription", str(identifier), tenantId)
            return {"revoked": True}
        return self.store.listSubscriptions(tenantId, actorId)


class ProviderWebhookService:
    """Public callback entry authenticated by provider HMAC, not a user token."""

    def __init__(
        self,
        store: NotificationPlatformStore,
        secrets: WebhookSecretProvider,
        clock: Any,
        toleranceSeconds: int = 300,
    ) -> None:
        self.store = store
        self.secrets = secrets
        self.clock = clock
        self.toleranceSeconds = toleranceSeconds

    def execute(self, command: ProcessProviderWebhookCommand) -> dict[str, Any]:
        tenantId = asUuid(command.tenantId)
        provider = command.provider.strip().upper()
        if not provider or not command.providerEventId.strip() or not command.providerMessageId.strip():
            raise ValidationFailedError("Provider callback identifiers are required.")
        status = command.status.strip().upper()
        if status not in PROVIDER_CALLBACK_STATUSES:
            raise ValidationFailedError("Provider callback status is invalid.")
        verifyWebhookSignature(
            command.rawBody,
            signature=command.signature,
            timestamp=command.timestamp,
            secret=self.secrets.secretFor(tenantId, provider),
            nowEpoch=int(self.clock.nowUtc().timestamp()),
            toleranceSeconds=self.toleranceSeconds,
        )
        safeMetadata = sanitizedMetadata(dict(command.metadata))
        return self.store.processWebhook(
            tenantId,
            provider,
            command.providerEventId.strip(),
            command.providerMessageId.strip(),
            status,
            canonicalPayloadHash(
                {
                    "providerMessageId": command.providerMessageId.strip(),
                    "status": status,
                    "errorCode": command.errorCode[:48],
                    "metadata": safeMetadata,
                }
            ),
            command.errorCode[:48],
            safeMetadata,
            self.clock.nowUtc(),
        )


class ProviderConfigurationService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(self, store: NotificationPlatformStore, **kernel: Any) -> None:
        super().__init__(**kernel)
        self.store = store

    def perform(self, command: SaveProviderConfigurationCommand | None) -> Any:
        actorId, tenantId = actor()
        if command is None:
            return self.store.listProviderConfigurations(tenantId)
        channel = command.channel.strip().upper()
        if channel not in PROVIDER_CHANNELS:
            raise ValidationFailedError("Provider channel is invalid.")
        provider = command.provider.strip().upper()
        if not provider:
            raise ValidationFailedError("Provider name is required.")
        config = sanitizedMetadata(dict(command.configuration))
        credentialRef = command.credentialRef.strip()
        allowedRefPrefixes = ("vault://", "env://", "aws-sm://", "gcp-sm://", "azure-kv://")
        if credentialRef and not credentialRef.startswith(allowedRefPrefixes):
            raise ValidationFailedError(
                "credentialRef must point to an approved secret manager."
            )
        # Secret-like values are redacted by domain policy; credentials are
        # represented only by a vault/secret-manager reference.
        result = self.store.saveProviderConfiguration(
            tenantId,
            actorId,
            channel,
            provider,
            credentialRef,
            config,
            command.isActive,
        )
        self.audit("UPDATE", "NotificationProvider", result["id"], tenantId)
        return result


class NotificationCleanupService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        store: NotificationPlatformStore,
        *,
        defaultRetentionDays: int = 365,
        **kernel: Any,
    ) -> None:
        super().__init__(**kernel)
        self.store = store
        self.defaultRetentionDays = defaultRetentionDays

    def perform(self, command: RunNotificationCleanupCommand) -> dict[str, Any]:
        actorId, tenantId = actor()
        days = command.retentionDays or self.defaultRetentionDays
        if days < 1 or days > 36500:
            raise ValidationFailedError("Retention days must be between 1 and 36500.")
        cutoff = self.clock.nowUtc() - timedelta(days=days)
        counts = self.store.cleanup(
            tenantId, actorId, cutoff, dryRun=bool(command.dryRun)
        )
        self.audit(
            "CLEANUP_PREVIEW" if command.dryRun else "CLEANUP_EXECUTE",
            "NotificationRetention",
            str(tenantId),
            tenantId,
            after={"cutoff": cutoff.isoformat(), "counts": counts},
        )
        return {
            "dryRun": bool(command.dryRun),
            "retentionDays": days,
            "cutoff": cutoff.isoformat(),
            "counts": counts,
        }


__all__ = [
    "NotificationCleanupService",
    "ProviderConfigurationService",
    "ProviderWebhookService",
    "PushSubscriptionService",
    "SearchNotificationsService",
]
