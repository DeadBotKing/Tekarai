from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = "apps.tenancy"
    label = "tenancy"
    verbose_name = "Tekarai Tenancy"

    def ready(self) -> None:
        # Models live in the infrastructure layer (§27); register them
        # explicitly so Django discovers them outside the default path.
        from importlib import import_module

        import_module("apps.tenancy.infrastructure.models")
