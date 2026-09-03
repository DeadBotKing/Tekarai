"""§12.12/§12.13 — Webhook channel adapter (Phase 12 addition).

The Phase 09 channel set covered IN_APP / EMAIL / PUSH / SMS. Phase 12 adds an
outbound WEBHOOK channel so integrations can receive notifications at their own
HTTP endpoint. The core never depends on a concrete transport: this adapter
implements the same port shape as the others and delegates to a provider. The
default provider only logs (no network in tests/dev); a real HTTP provider can
be injected without touching application code.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class WebhookProviderPort(Protocol):
    name: str

    def post(self, *, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST the notification payload; return {'ok': bool, 'providerMessageId': str,
        'errorCode': str, 'errorMessage': str}."""


class LoggingWebhookProvider:
    """Default provider — records the call without performing network I/O.

    Returns success with a deterministic provider message id so the delivery
    pipeline advances to SENT/DELIVERED. Swappable for a real HTTP provider.
    """

    name = "logging-webhook"

    def post(self, *, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "delivered": True,
            "providerMessageId": f"wh-{payload.get('notificationId', 'na')}",
            "errorCode": "",
            "errorMessage": "",
        }


class WebhookDeliveryChannel:
    """§12.13 — adapter for the WEBHOOK channel."""

    channelName = "WEBHOOK"
    providerName = "logging-webhook"

    def __init__(self, provider: WebhookProviderPort | None = None) -> None:
        self.provider = provider or LoggingWebhookProvider()
        self.providerName = getattr(self.provider, "name", self.providerName)

    def send(
        self,
        *,
        tenantId: str,
        notificationId: str,
        recipientId: str,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        url = str(metadata.get("webhookUrl", ""))
        payload = {
            "tenantId": tenantId,
            "notificationId": notificationId,
            "recipientId": recipientId,
            "title": title,
            "body": body,
            "deepLink": metadata.get("deepLink", ""),
            "metadata": metadata,
        }
        if not url:
            # No endpoint configured for this recipient: treat as a permanent
            # configuration error (retries won't help) — the pipeline records
            # a failed attempt and dead-letters after the cap.
            return {
                "ok": False,
                "delivered": False,
                "providerMessageId": "",
                "errorCode": "WEBHOOK_URL_MISSING",
                "errorMessage": "no webhook URL configured",
            }
        return self.provider.post(url=url, payload=payload)
