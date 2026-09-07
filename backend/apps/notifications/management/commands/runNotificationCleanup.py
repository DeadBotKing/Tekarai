"""Preview or execute Phase 15 notification retention cleanup."""

from __future__ import annotations

import json
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.notifications.application.commands.phase15Commands import (
    RunNotificationCleanupCommand,
)
from apps.notifications.infrastructure import container
from apps.sharedKernel.application.requestContext import RequestContext, requestScope


class Command(BaseCommand):
    help = "Preview or execute tenant notification cleanup; audit data is retained."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tenant-id", required=True)
        parser.add_argument("--actor-id", required=True)
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            tenantId = uuid.UUID(options["tenant_id"])
            actorId = uuid.UUID(options["actor_id"])
        except (TypeError, ValueError) as exc:
            raise CommandError("tenant and actor IDs must be valid UUIDs") from exc
        with requestScope(
            RequestContext(
                actorId=str(actorId),
                tenantId=str(tenantId),
                actorTenantId=str(tenantId),
            )
        ):
            result = container.phase15CleanupService().execute(
                RunNotificationCleanupCommand(
                    retentionDays=options["days"], dryRun=not options["execute"]
                )
            )
        self.stdout.write(json.dumps(result, sort_keys=True))
