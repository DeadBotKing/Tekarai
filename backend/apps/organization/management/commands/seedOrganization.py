"""Create the starting organisation chart for a tenant.

Idempotent: safe to run on every deploy. Everything it writes is ordinary
data the plant may rename, retire or delete — the command exists so a fresh
install has a usable chart on day one, not to define structure in code.
"""

from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.organization.application.services import orgService


class Command(BaseCommand):
    help = "Seed default departments, positions and the access matrix for a tenant."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tenant", required=True, help="Tenant UUID")

    def handle(self, *args, **options):
        try:
            tenantId = uuid.UUID(str(options["tenant"]))
        except ValueError:
            self.stdout.write(self.style.ERROR("--tenant must be a UUID."))
            return

        created = orgService.seedDefaults(tenantId, now=timezone.now())
        self.stdout.write(
            self.style.SUCCESS(
                "Organisation seeded: "
                f"{created['departments']} departments, "
                f"{created['positions']} positions, "
                f"{created['rules']} matrix rules created "
                "(existing rows left untouched)."
            )
        )
