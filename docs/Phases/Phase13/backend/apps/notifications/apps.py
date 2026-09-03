"""Notification context configuration (Phase 09)."""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class NotificationsConfig(AppConfig):
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Tekarai Notifications"

    def ready(self) -> None:
        # Models live in the infrastructure layer; register them explicitly
        # so Django discovers them outside the default models.py path.
        from importlib import import_module

        import_module("apps.notifications.infrastructure.models")
        # §30 — subscribe the notification consumer to outbox events.
        # Guarded: a subscription failure must never block boot.
        try:
            from apps.notifications.infrastructure.eventConsumer import (
                registerNotificationSubscriptions,
            )

            registerNotificationSubscriptions()
        except Exception:  # noqa: BLE001 — boot isolation
            logger.exception("Notification event subscriptions skipped")
