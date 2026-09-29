from __future__ import annotations

from django.apps import AppConfig


class ProcurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.procurement"
    label = "procurement"
    verbose_name = "Tekarai Procurement"

    def ready(self) -> None:
        from importlib import import_module

        import_module("apps.procurement.infrastructure.models")
