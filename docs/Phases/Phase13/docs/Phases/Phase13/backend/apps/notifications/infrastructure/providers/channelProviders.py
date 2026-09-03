"""Provider adapters (Phase 09 §13/§48).

Every external system (SMTP, Firebase, APNs, web push, SMS gateway,
Graph) hides behind ``NotificationProviderPort``. The default adapters
are log-backed — the platform stays fully functional and testable with
zero external dependencies, and production swaps them via configuration
(``NOTIFICATION_PROVIDERS`` setting) without touching the domain.

§48 — each provider is a chain; on failure the next provider is tried.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.notifications.domain.repositories.notificationRepositories import (
    DeliveryResult,
    NotificationProviderPort,
)
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

logger = logging.getLogger(__name__)


class LoggingEmailProvider:
    """Development SMTP stand-in — logs the envelope, never the secrets."""

    providerName = "logging-email"

    def send(
        self,
        *,
        tenantId: Any,
        recipientAddress: str,
        title: str,
        subject: str,
        body: str,
        meta: dict[str, Any],
    ) -> DeliveryResult:
        logger.info(
            "EMAIL dispatch",
            extra={
                "tenantId": str(tenantId),
                "channel": "EMAIL",
                "provider": self.providerName,
                "recipientAddressHash": _mask(recipientAddress),
            },
        )
        return DeliveryResult(ok=True)


class SmtpEmailProvider:
    """Real SMTP adapter (production). Emails are async-only (§16)."""

    providerName = "smtp"

    def __init__(self, host: str = "", port: int = 587, sender: str = "") -> None:
        self.host = host
        self.port = port
        self.sender = sender

    def send(
        self,
        *,
        tenantId: Any,
        recipientAddress: str,
        title: str,
        subject: str,
        body: str,
        meta: dict[str, Any],
    ) -> DeliveryResult:
        import smtplib
        from email.message import EmailMessage

        if not self.host or not self.sender:
            return DeliveryResult(
                ok=False, errorCode="PROVIDER_UNCONFIGURED",
                errorMessage="SMTP host/sender not configured",
            )
        try:
            message = EmailMessage()
            message["From"] = self.sender
            message["To"] = recipientAddress
            message["Subject"] = subject or title
            message.set_content(body or title)
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.send_message(message)
            return DeliveryResult(ok=True)
        except Exception as exc:  # noqa: BLE001 — provider boundary
            return DeliveryResult(
                ok=False, errorCode="PROVIDER_ERROR", errorMessage=str(exc)[:200]
            )


class LoggingSmsProvider:
    """§17 — SMS is expensive; the default adapter only logs."""

    providerName = "logging-sms"

    def send(
        self,
        *,
        tenantId: Any,
        recipientAddress: str,
        title: str,
        subject: str,
        body: str,
        meta: dict[str, Any],
    ) -> DeliveryResult:
        logger.info(
            "SMS dispatch",
            extra={
                "tenantId": str(tenantId),
                "channel": "SMS",
                "provider": self.providerName,
                "recipientAddressHash": _mask(recipientAddress),
            },
        )
        return DeliveryResult(ok=True)


class LoggingPushProvider:
    """FCM/APNs stand-in — logs per-device dispatch without tokens."""

    providerName = "logging-push"

    def send(
        self,
        *,
        tenantId: Any,
        recipientAddress: str,
        title: str,
        subject: str,
        body: str,
        meta: dict[str, Any],
    ) -> DeliveryResult:
        logger.info(
            "PUSH dispatch",
            extra={
                "tenantId": str(tenantId),
                "channel": str(meta.get("channel", "PUSH")),
                "provider": self.providerName,
                "deviceHash": _mask(recipientAddress),
            },
        )
        return DeliveryResult(ok=True)


def _mask(address: str) -> str:
    """§33 — PII never reaches the logs in clear text."""
    if len(address) <= 4:
        return "***"
    return address[:2] + "***" + address[-2:]


class ProviderPool:
    """§48 — configurable failover chain for one channel."""

    def __init__(self, providers: list[NotificationProviderPort]) -> None:
        self.providers = providers or []

    @property
    def primaryName(self) -> str:
        return getattr(self.providers[0], "providerName", "unconfigured") if self.providers else "unconfigured"

    def sendWithFailover(self, **kwargs: Any) -> tuple[DeliveryResult, str]:
        """Tries providers in order; returns (result, providerUsed)."""
        lastResult = DeliveryResult(
            ok=False, errorCode="PROVIDER_UNCONFIGURED",
            errorMessage="no provider configured",
        )
        for provider in self.providers:
            try:
                result = provider.send(**kwargs)
            except Exception as exc:  # noqa: BLE001 — §48 failover
                result = DeliveryResult(
                    ok=False, errorCode="PROVIDER_ERROR", errorMessage=str(exc)[:200]
                )
            if result.ok:
                return result, getattr(provider, "providerName", "")
            lastResult = result
        return lastResult, self.primaryName


def emailProviderPool() -> ProviderPool:
    """Configuration seam (§48): swap chains via settings, not code."""
    from django.conf import settings

    chain: list[NotificationProviderPort] = []
    configured = getattr(settings, "NOTIFICATION_EMAIL_PROVIDERS", [])
    for dottedPath in configured:
        factory = sharedKernelProvider  # settings carry dotted paths
        try:
            from apps.sharedKernel.infrastructure.wiring import importFromDottedPath

            chain.append(importFromDottedPath(dottedPath)())
        except Exception:  # noqa: BLE001 — fall back to the safe default
            logger.exception("Cannot load email provider %s", dottedPath)
    if not chain:
        chain = [LoggingEmailProvider()]
    return ProviderPool(chain)


def smsProviderPool() -> ProviderPool:
    from django.conf import settings

    chain: list[NotificationProviderPort] = []
    for dottedPath in getattr(settings, "NOTIFICATION_SMS_PROVIDERS", []):
        try:
            from apps.sharedKernel.infrastructure.wiring import importFromDottedPath

            chain.append(importFromDottedPath(dottedPath)())
        except Exception:  # noqa: BLE001
            logger.exception("Cannot load sms provider %s", dottedPath)
    if not chain:
        chain = [LoggingSmsProvider()]
    return ProviderPool(chain)


def pushProviderPool() -> ProviderPool:
    from django.conf import settings

    chain: list[NotificationProviderPort] = []
    for dottedPath in getattr(settings, "NOTIFICATION_PUSH_PROVIDERS", []):
        try:
            from apps.sharedKernel.infrastructure.wiring import importFromDottedPath

            chain.append(importFromDottedPath(dottedPath)())
        except Exception:  # noqa: BLE001
            logger.exception("Cannot load push provider %s", dottedPath)
    if not chain:
        chain = [LoggingPushProvider()]
    return ProviderPool(chain)
