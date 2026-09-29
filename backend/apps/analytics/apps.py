"""Reporting/Analytics bounded-context configuration."""

from __future__ import annotations

from importlib import import_module

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Django registration for the layered Analytics context."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    label = "analytics"
    verbose_name = "Tekarai Analytics"

    def ready(self) -> None:
        # Persistence models deliberately live below infrastructure/.
        import_module("apps.analytics.infrastructure.models")
