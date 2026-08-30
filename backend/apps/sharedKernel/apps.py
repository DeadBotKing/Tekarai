from django.apps import AppConfig


class SharedKernelConfig(AppConfig):
    name = "apps.sharedKernel"
    label = "sharedKernel"
    verbose_name = "Tekarai Shared Kernel"

    def ready(self) -> None:
        # Models live in the infrastructure layer (§27); register them
        # explicitly so Django discovers them outside the default path.
        from importlib import import_module

        import_module("apps.sharedKernel.infrastructure.models")
