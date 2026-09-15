"""Tasks context configuration (Phase 18b)."""

from __future__ import annotations

from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tasks"
    label = "tasks"
    verbose_name = "Tekarai Tasks"

    def ready(self) -> None:
        # Models live in the infrastructure layer; register them explicitly
        # so Django discovers them outside the default models.py path.
        from importlib import import_module

        import_module("apps.tasks.infrastructure.models")
