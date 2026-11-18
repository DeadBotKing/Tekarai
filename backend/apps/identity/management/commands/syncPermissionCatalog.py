"""syncPermissionCatalog — register production permissions + create productionPlanner role.

Safe (idempotent) to re-run. Run on the server inside the backend virtualenv:
    python manage.py syncPermissionCatalog
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.identity.application.services.permissionCatalog import (
    ACTIONS,
    PRODUCTION_PLANNER_ROLE,
    ROLE_PRESETS,
)
from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
    AccessRepositoryDjango,
)


class Command(BaseCommand):
    help = "Adds production.view/production.manage to the catalogue and creates the productionPlanner role."

    def handle(self, *_args, **_kwargs):
        access = AccessRepositoryDjango()

        # 1) Register all known permission codes (idempotent).
        access.ensureCatalogue(ACTIONS)
        self.stdout.write(self.style.SUCCESS(f"[OK] Registered {len(ACTIONS)} permission codes."))

        # 2) Ensure built-in roles are up to date.
        role_seeds = [
            ("tenantAdmin", "Tenant Administrator", "TENANT"),
            ("member", "Member", "TENANT"),
            (PRODUCTION_PLANNER_ROLE, "مدیر برنامه‌ریزی تولید", "TENANT"),
        ]
        for code, name, scope in role_seeds:
            actions = ROLE_PRESETS.get(code)
            if not actions:
                continue
            access.ensureRole(code, name, actions, scope)
            self.stdout.write(self.style.SUCCESS(f"[OK] Role '{name}' ({code}) synced with {len(actions)} actions."))

        self.stdout.write(self.style.SUCCESS(
            "DONE. Please recycle the IIS application pool (or run iisreset) "
            "and then Ctrl+F5 the browser to pick up the new permissions."
        ))
