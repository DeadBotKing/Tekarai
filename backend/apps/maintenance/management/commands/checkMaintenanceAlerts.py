"""Scheduled maintenance alerts — SLA breach + low-stock notification scan.

Emits ``workOrderOverdue`` (open order past its priority SLA, BR-WO-SLA) and
``sparePartLowStock`` domain events, which the notification engine (§30 route
table) fans out to the maintenance roles. Weekly-idempotent: every event
carries a deterministic ``eventId`` scoped to the ISO week, so re-running
within the same week creates no duplicate notifications (§29).

PM schedule reminders remain in ``sendPmReminders``; run both from cron.

Usage:
    python manage.py checkMaintenanceAlerts [--tenant <uuid>]
                                            [--no-work-orders] [--no-stock]
                                            [--loop] [--interval 86400]

Production wiring (one run per day is enough):

    # cron — هر روز ساعت ۰۷:۰۰ به وقت سرور
    0 7 * * * cd /srv/tekarai/backend && \\
              .venv/bin/python manage.py checkMaintenanceAlerts >> /var/log/tekarai-alerts.log 2>&1

    # زمان‌بند ویندوز — اجرای روزانه ساعت ۰۷:۰۰
    # (از ابزار زمان‌بندی ویندوز: schtasks)
    schtasks /create /tn "Tekarai Maintenance Alerts" /sc daily /st 07:00 \\
      /tr "\"C:\\tekarai\\backend\\.venv\\Scripts\\python.exe\" C:\\tekarai\\backend\\manage.py checkMaintenanceAlerts"

Development runs ``--loop``; production typically wires the same scan into a
scheduler (cron, Celery beat, Kubernetes CronJob).
"""

from __future__ import annotations

import logging
import time
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def scanTenants(
    tenantId: str = "",
    includeWorkOrders: bool = True,
    includeLowStock: bool = True,
) -> list[dict]:
    """One full alert pass over one tenant (or every tenant with activity)."""
    from apps.maintenance.application.commands.maintenanceCommands import (
        RunMaintenanceAlertScanCommand,
    )
    from apps.maintenance.infrastructure import container
    from apps.maintenance.infrastructure.models import WorkOrderModel

    if tenantId:
        tenantIds = [uuid.UUID(tenantId)]
    else:
        tenantIds = list(
            WorkOrderModel.objects.filter(deletedAt__isnull=True)
            .values_list("tenantId", flat=True)
            .distinct()
        )

    summaries: list[dict] = []
    for currentTenantId in tenantIds:
        dto = container.runMaintenanceAlertScanUseCase().execute(
            RunMaintenanceAlertScanCommand(
                tenantId=str(currentTenantId),
                includeWorkOrders=includeWorkOrders,
                includeLowStock=includeLowStock,
            )
        )
        summaries.append(
            {
                "tenantId": str(currentTenantId),
                "asOf": dto.asOf,
                "isoWeek": dto.isoWeek,
                "overdueWorkOrders": dto.overdueWorkOrders,
                "lowStockParts": dto.lowStockParts,
            }
        )
    return summaries


class Command(BaseCommand):
    help = (
        "Scan open work orders past SLA and low-stock parts and notify "
        "maintenance roles (weekly-idempotent; safe to run daily)."
    )

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument(
            "--tenant", default="", help="Tenant id (default: all tenants)."
        )
        parser.add_argument(
            "--no-work-orders",
            action="store_true",
            help="Skip the overdue work-order (SLA) scan.",
        )
        parser.add_argument(
            "--no-stock",
            action="store_true",
            help="Skip the low-stock scan.",
        )
        parser.add_argument(
            "--loop", action="store_true", help="Keep running on an interval."
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=86400,
            help="Seconds between scans when --loop is set (default 86400 — daily).",
        )

    def handle(self, *args, **options) -> None:  # noqa: ANN002/ANN003 — Django contract
        kwargs = {
            "includeWorkOrders": not options["no_work_orders"],
            "includeLowStock": not options["no_stock"],
        }
        if not options["loop"]:
            self.stdout.write(str(scanTenants(options["tenant"], **kwargs)))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Maintenance alert scheduler looping every {options['interval']}s (Ctrl+C to stop)."
            )
        )
        try:
            while True:
                startedAt = time.monotonic()
                summaries = scanTenants(options["tenant"], **kwargs)
                logger.info("Maintenance alert scan", extra={"summaries": summaries})
                elapsed = time.monotonic() - startedAt
                time.sleep(max(0.0, options["interval"] - elapsed))
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Maintenance alert scheduler stopped."))
