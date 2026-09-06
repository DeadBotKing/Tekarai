"""Run or preview the Phase 14 communication retention sweep."""

from __future__ import annotations

import json
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.communication.application.commands.phase14Commands import RunRetentionCommand
from apps.communication.infrastructure import container
from apps.sharedKernel.application.requestContext import RequestContext, requestScope


class Command(BaseCommand):
    help = "Preview or execute tenant-scoped communication retention with legal-hold exclusions."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tenant-id", required=True)
        parser.add_argument("--actor-id", required=True)
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Physically purge eligible metadata; without this flag only preview.",
        )

    def handle(self, *args, **options) -> None:
        try:
            tenantId = uuid.UUID(options["tenant_id"])
            actorId = uuid.UUID(options["actor_id"])
        except (TypeError, ValueError) as exc:
            raise CommandError("--tenant-id and --actor-id must be valid UUIDs.") from exc
        with requestScope(
            RequestContext(
                actorId=str(actorId),
                tenantId=str(tenantId),
                actorTenantId=str(tenantId),
            )
        ):
            result = container.runRetentionUseCase().execute(
                RunRetentionCommand(retentionDays=options["days"], dryRun=not options["execute"])
            )
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
