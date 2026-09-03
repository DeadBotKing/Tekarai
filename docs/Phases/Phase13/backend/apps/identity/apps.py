from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "apps.identity"
    label = "identity"
    verbose_name = "Tekarai Identity"

    def ready(self) -> None:
        # Models live in the infrastructure layer (§27); register them
        # explicitly so Django discovers them outside the default path.
        from importlib import import_module

        import_module("apps.identity.infrastructure.models")
