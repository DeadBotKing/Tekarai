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
        # Celery's default autodiscovery only imports top-level tasks.py, which
        # this layered context deliberately forbids. Register infrastructure
        # tasks explicitly while the app is initialized.
        import_module("apps.maintenance.infrastructure.tasks")
