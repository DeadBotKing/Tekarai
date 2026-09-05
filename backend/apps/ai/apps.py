"""AI context configuration (Phase 13).

EVOLUTION NOTE (Phase 13-L): the context followed the Phase 09 registration
pattern — models live in the infrastructure layer and are imported from
``AppConfig.ready`` so Django discovers them outside the default
``models.py`` path. The Phase 06 structure guard
(``tests/architecture/testDependencyRules.py``) requires exactly
``__init__.py`` + ``apps.py`` at the context top level.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "Tekarai AI Platform"

    def ready(self) -> None:
        # Models live in the infrastructure layer; register them explicitly
        # so Django discovers them outside the default models.py path.
        import_module("apps.ai.infrastructure.models")
