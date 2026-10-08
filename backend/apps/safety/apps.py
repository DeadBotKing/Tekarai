from __future__ import annotations

from django.apps import AppConfig


class SafetyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.safety"
    label = "safety"
    verbose_name = "Tekarai Safety — Permit to Work"

    def ready(self) -> None:
        from importlib import import_module

        import_module("apps.safety.infrastructure.models")
