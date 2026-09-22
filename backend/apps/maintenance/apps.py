"""Maintenance context configuration (Phase 21 — CMMS)."""

from __future__ import annotations

from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maintenance"
    label = "maintenance"
    verbose_name = "Tekarai Maintenance"

    def ready(self) -> None:
        # Models live in the infrastructure layer; register them explicitly
        # so Django discovers them outside the default models.py path.
        from importlib import import_module

        import_module("apps.maintenance.infrastructure.models")
