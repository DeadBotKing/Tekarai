from django.apps import AppConfig


class OrganizationConfig(AppConfig):
    """Organisation structure: departments, positions and who sits where."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organization"
    label = "organization"

    def ready(self) -> None:
        from importlib import import_module

        import_module("apps.organization.infrastructure.models")
