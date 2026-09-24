"""PM reminder scheduler — scan devices and notify technicians/managers.

Emits ``devicePmDueSoon`` / ``devicePmOverdue`` domain events, which the
notification engine (§30 route table) fans out to the ``maintenanceTechnician``
and ``maintenanceManager`` roles. Idempotent per PM cycle: re-running within
the same cycle creates no duplicate notifications (§29 idempotency key).

Usage:
    python manage.py sendPmReminders [--tenant <uuid>] [--lead-days 3]
                                     [--loop] [--interval 3600]

Development runs ``--loop``; production wires the same scan into any
scheduler (cron, Celery beat, Kubernetes CronJob) — one run per day is
typically enough.
"""

from __future__ import annotations

import logging
import time
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def scanTenants(tenantId: str = "", leadDays: int = 3) -> list[dict]:
    """One full reminder pass over one tenant (or every tenant with devices)."""
    from apps.maintenance.application.commands.maintenanceCommands import (
        SendPmRemindersCommand,
    )
    from apps.maintenance.infrastructure import container
    from apps.maintenance.infrastructure.models import DeviceModel

    if tenantId:
        tenantIds = [uuid.UUID(tenantId)]
    else:
        tenantIds = list(
            DeviceModel.objects.filter(deletedAt__isnull=True)
            .values_list("tenantId", flat=True)
            .distinct()
        )

    summaries: list[dict] = []
    for currentTenantId in tenantIds:
        dto = container.sendPmRemindersUseCase().execute(
            SendPmRemindersCommand(tenantId=str(currentTenantId), leadDays=leadDays)
        )
        summaries.append(
            {
                "tenantId": str(currentTenantId),
                "asOf": dto.asOf,
                "scanned": dto.scannedCount,
                "dueSoon": dto.dueSoonCount,
                "overdue": dto.overdueCount,
            }
        )
    return summaries


class Command(BaseCommand):
    help = (
        "Scan PM schedules and notify maintenance roles about due-soon / "
        "overdue devices (idempotent per PM cycle)."
    )

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument("--tenant", default="", help="Tenant id (default: all tenants).")
        parser.add_argument(
            "--lead-days",
            type=int,
            default=3,
            help="Look-ahead window in days for due-soon reminders (default 3).",
        )
        parser.add_argument("--loop", action="store_true", help="Keep running on an interval.")
        parser.add_argument(
            "--interval",
            type=int,
            default=3600,
            help="Seconds between scans when --loop is set (default 3600).",
        )

    def handle(self, *args, **options) -> None:  # noqa: ANN002/ANN003 — Django contract
        if not options["loop"]:
            self.stdout.write(str(scanTenants(options["tenant"], options["lead_days"])))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"PM reminder scheduler looping every {options['interval']}s (Ctrl+C to stop)."
            )
        )
        try:
            while True:
                startedAt = time.monotonic()
                summaries = scanTenants(options["tenant"], options["lead_days"])
                logger.info("PM reminder scan", extra={"summaries": summaries})
                elapsed = time.monotonic() - startedAt
                time.sleep(max(0.0, options["interval"] - elapsed))
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("PM reminder scheduler stopped."))
