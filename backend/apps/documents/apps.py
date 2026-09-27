"""Documents bounded context app configuration (Phase 31 §Documents library)."""

from __future__ import annotations

from importlib import import_module

from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Django app for the generic document library context.

    The big-picture context map lists Documents as a shared capability:
    per-tenant file library with upload / list / download / soft-delete.
    ``ready()`` imports the models module so Django registers them.
    """

    name = "apps.documents"
    label = "documents"
    verbose_name = "Documents"

    def ready(self) -> None:  # noqa: D102
        import_module("apps.documents.infrastructure.models")
