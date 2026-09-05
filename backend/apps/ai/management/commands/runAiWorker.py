"""Phase 13-P — async AI job worker tick (contract §P.5).

Development runs this as a loop; production wires the same ``tick()``
call into any scheduler (cron, beat, Kubernetes job) — the transport
stays replaceable because the ``JobStore`` port is the only entry point.

Usage:
    python manage.py runAiWorker [--once] [--interval 5] [--limit 10] [--tenant <uuid>]
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from typing import Any

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def buildQueueService() -> Any:
    """Compose the production worker graph (lazy imports keep startup light)."""

    from django.conf import settings as djangoSettings

    from apps.ai.application.services.auditService import AuditApplicationService
    from apps.ai.application.services.queueService import (
        QueueApplicationService,
        QueueSettings,
    )
    from apps.ai.infrastructure.repositories.auditRepositories import (
        DjangoAuditRecordStore,
        DjangoGovernancePolicyStore,
        DjangoRetentionPurger,
    )
    from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore

    queueSettings = QueueSettings.fromDjangoSettings(djangoSettings)
    auditService = AuditApplicationService(
        DjangoAuditRecordStore(),
        DjangoGovernancePolicyStore(),
        DjangoRetentionPurger(),
    )
    workerId = f"{queueSettings.workerId}-{uuid.uuid4().hex[:8]}"
    return QueueApplicationService(
        DjangoJobStore(),
        auditService=auditService,
        queueSettings=queueSettings,
        workerId=workerId,
    )


def tick(
    limit: int = 10,
    tenantId: Any = None,
    service: Any = None,
) -> dict:
    """One bounded worker pass: claim → execute → settle → audit."""

    worker = service or buildQueueService()
    report = worker.tick(limit=limit, tenantId=tenantId)
    return asdict(report)


class Command(BaseCommand):
    help = "AI async worker (Phase 13-P): claim due jobs, execute, settle, audit."

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument("--once", action="store_true", help="Run one tick and exit.")
        parser.add_argument("--interval", type=int, default=5, help="Seconds between ticks.")
        parser.add_argument("--limit", type=int, default=10, help="Jobs claimed per tick.")
        parser.add_argument("--tenant", type=str, default="", help="Restrict ticks to one tenant.")

    def handle(self, *args, **options) -> None:  # noqa: ANN002/ANN003 — Django contract
        tenantId = options["tenant"] or None
        service = buildQueueService()
        if options["once"]:
            self.stdout.write(str(tick(limit=options["limit"], tenantId=tenantId, service=service)))
            return
        self.stdout.write(
            self.style.SUCCESS(f"AI worker looping every {options['interval']}s (Ctrl+C to stop).")
        )
        try:
            while True:
                startedAt = time.monotonic()
                summary = tick(limit=options["limit"], tenantId=tenantId, service=service)
                logger.info("AI worker tick", extra={"summary": summary})
                elapsed = time.monotonic() - startedAt
                time.sleep(max(0.0, options["interval"] - elapsed))
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("AI worker stopped."))
