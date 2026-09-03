"""Channel adapters (Phase 09 §12/§14/§15/§47).

Each channel owns its provider pool (§13/§48) and its precondition
checks. One channel failing never touches the others (§47).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.notifications.domain.entities.notification import Notification
from apps.notifications.domain.repositories.notificationRepositories import (
    DeliveryResult,
    NotificationChannelPort,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    PUSH_LIKE_CHANNELS,
)
from apps.notifications.infrastructure.providers.channelProviders import (
    ProviderPool,
    emailProviderPool,
    pushProviderPool,
    smsProviderPool,
)

logger = logging.getLogger(__name__)


class InAppDeliveryChannel(NotificationChannelPort):
    """§14 — the notification row IS the in-app inbox item; delivery is
    proven by persistence. The WebSocket push (§41) is only an
    optimization and happens after the commit."""

    channelName = "IN_APP"
    providerName = "tekarai-inapp"

    def deliver(
        self,
        *,
        tenantId: Any,
        notification: Notification,
        renderedTitle: str,
        renderedSubject: str,
        renderedBody: str,
    ) -> DeliveryResult:
        return DeliveryResult(ok=True)


class EmailDeliveryChannel(NotificationChannelPort):
    """§16 — email is always dispatched through the async worker."""

    channelName = "EMAIL"
    providerName = "logging-email"

    def __init__(
        self,
        pool: ProviderPool | None = None,
        contactSource: Any = None,
    ) -> None:
        self.pool = pool or emailProviderPool()
        self.contactSource = contactSource

    def deliver(
        self,
        *,
        tenantId: Any,
        notification: Notification,
        renderedTitle: str,
        renderedSubject: str,
        renderedBody: str,
    ) -> DeliveryResult:
        address = self._addressOf(tenantId, notification)
        if not address:
            return DeliveryResult(
                ok=False, errorCode="INVALID_ADDRESS",
                errorMessage="recipient has no email address",
            )
        result, providerUsed = self.pool.sendWithFailover(
            tenantId=tenantId,
            recipientAddress=address,
            title=renderedTitle,
            subject=renderedSubject,
            body=renderedBody,
            meta={"notificationId": str(notification.id), "channel": self.channelName},
        )
        self.providerName = providerUsed or self.providerName
        return result

    def _addressOf(self, tenantId: Any, notification: Notification) -> str:
        external = str(notification.payload.get("externalAddress", "") or "")
        if external:
            return external
        if self.contactSource is None:
            return ""
        return self.contactSource.emailOf(tenantId, notification.recipientId)


class SmsDeliveryChannel(NotificationChannelPort):
    """§17 — expensive channel; used sparingly, default provider only logs."""

    channelName = "SMS"
    providerName = "logging-sms"

    def __init__(
        self,
        pool: ProviderPool | None = None,
        contactSource: Any = None,
    ) -> None:
        self.pool = pool or smsProviderPool()
        self.contactSource = contactSource

    def deliver(
        self,
        *,
        tenantId: Any,
        notification: Notification,
        renderedTitle: str,
        renderedSubject: str,
        renderedBody: str,
    ) -> DeliveryResult:
        address = ""
        external = str(notification.payload.get("externalAddress", "") or "")
        if external:
            address = external
        elif self.contactSource is not None:
            address = self.contactSource.phoneOf(tenantId, notification.recipientId)
        if not address:
            return DeliveryResult(
                ok=False, errorCode="INVALID_ADDRESS",
                errorMessage="recipient has no phone number",
            )
        result, providerUsed = self.pool.sendWithFailover(
            tenantId=tenantId,
            recipientAddress=address,
            title=renderedTitle,
            subject=renderedSubject,
            body=renderedBody or renderedTitle,
            meta={"notificationId": str(notification.id), "channel": self.channelName},
        )
        self.providerName = providerUsed or self.providerName
        return result


class PushDeliveryChannel(NotificationChannelPort):
    """§15 — one user may own many devices; only ACTIVE registrations
    receive pushes (revoked devices are skipped immediately §49)."""

    channelName = "PUSH"
    providerName = "logging-push"

    def __init__(
        self,
        pool: ProviderPool | None = None,
        deviceSource: Any = None,
        channel: str = "PUSH",
    ) -> None:
        self.pool = pool or pushProviderPool()
        self.deviceSource = deviceSource
        self.channelName = channel

    def deliver(
        self,
        *,
        tenantId: Any,
        notification: Notification,
        renderedTitle: str,
        renderedSubject: str,
        renderedBody: str,
    ) -> DeliveryResult:
        if self.deviceSource is None:
            return DeliveryResult(
                ok=False, errorCode="PROVIDER_UNCONFIGURED",
                errorMessage="device registry unavailable",
            )
        devices = self.deviceSource.activeForUser(tenantId, notification.recipientId)
        if not devices:
            return DeliveryResult(
                ok=False, errorCode="NO_ACTIVE_DEVICE",
                errorMessage="recipient has no active device",
            )
        failures = 0
        lastError = ""
        providerUsed = ""
        for device in devices:
            if device.platform not in self._supportedPlatforms():
                continue
            result, providerUsed = self.pool.sendWithFailover(
                tenantId=tenantId,
                recipientAddress=device.pushToken,  # §33 — token stays in-process
                title=renderedTitle,
                subject=renderedSubject,
                body=renderedBody or renderedTitle,
                meta={
                    "notificationId": str(notification.id),
                    "channel": self.channelName,
                    "platform": device.platform,
                },
            )
            if not result.ok:
                failures += 1
                lastError = result.errorMessage
        self.providerName = providerUsed or self.providerName
        if failures == len(devices):
            return DeliveryResult(
                ok=False, errorCode="PROVIDER_ERROR",
                errorMessage=lastError or "all device pushes failed",
            )
        return DeliveryResult(ok=True)

    def _supportedPlatforms(self) -> tuple[str, ...]:
        if self.channelName == "PUSH":
            return ("IOS", "ANDROID")
        if self.channelName == "DESKTOP":
            return ("DESKTOP", "OTHER")
        return ("WEB", "OTHER")


class ChannelRegistry:
    """§12/§13 — name → adapter; the services' only channel doorway."""

    def __init__(self, contactSource: Any = None, deviceSource: Any = None) -> None:
        self.contactSource = contactSource
        self.deviceSource = deviceSource
        adapters: list[NotificationChannelPort] = [
            InAppDeliveryChannel(),
            EmailDeliveryChannel(contactSource=contactSource),
            SmsDeliveryChannel(contactSource=contactSource),
        ]
        for pushLike in PUSH_LIKE_CHANNELS:
            adapters.append(
                PushDeliveryChannel(
                    deviceSource=deviceSource, channel=pushLike
                )
            )
        self._adapters = {adapter.channelName: adapter for adapter in adapters}

    def channelFor(self, channel: str) -> NotificationChannelPort | None:
        return self._adapters.get(channel)

    def availableChannels(self) -> list[str]:
        return list(self._adapters)

    def channelStatus(self) -> list[dict[str, str]]:
        """§40 admin 'manage channels' — catalog with provider names."""
        return [
            {
                "channel": name,
                "provider": getattr(adapter, "providerName", ""),
            }
            for name, adapter in sorted(self._adapters.items())
        ]
