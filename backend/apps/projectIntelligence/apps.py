"""Project Intelligence Platform registration (Phase 17)."""

from importlib import import_module

from django.apps import AppConfig


class ProjectIntelligenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.projectIntelligence"
    label = "projectIntelligence"
    verbose_name = "Tekarai Project Intelligence Platform"

    def ready(self) -> None:
        import_module("apps.projectIntelligence.infrastructure.persistence.models")
        import_module("apps.projectIntelligence.infrastructure.queue.intelligenceJobs")
