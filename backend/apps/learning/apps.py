"""Self-Learning Platform application registration (Phase 16)."""

from __future__ import annotations

from importlib import import_module

from django.apps import AppConfig


class LearningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.learning"
    label = "learning"
    verbose_name = "Tekarai Self-Learning Platform"

    def ready(self) -> None:
        # Persistence remains in infrastructure while Django receives explicit
        # model registration (the established Tekarai context convention).
        import_module("apps.learning.infrastructure.persistence.models")
        # Celery jobs are infrastructure and imported explicitly rather than
        # forcing a framework-specific job modules into the context root.
        import_module("apps.learning.infrastructure.queue.learningJobs")
