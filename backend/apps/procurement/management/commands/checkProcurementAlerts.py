"""Scheduled procurement alerts — purchase requests nobody has bought yet.

Emits ``purchaseRequisitionStale`` for every open requisition that has waited
past the limit for its priority (critical 2 days, high 4, normal 7, low 14,
counted from submission). The notification engine fans these out to the
buyers via the §30 route table.

Weekly-idempotent: every event carries a deterministic ``eventId`` scoped to
the ISO week, so running this daily raises each late request once a week
rather than every morning (§29).

Usage:
    python manage.py checkProcurementAlerts [--tenant <uuid>]
                                            [--loop] [--interval 86400]

Production wiring (daily is the right cadence):

    # cron — هر روز ساعت ۰۷:۳۰ به وقت سرور
    30 7 * * * cd /srv/tekarai/backend && \\
               .venv/bin/python manage.py checkProcurementAlerts >> /var/log/tekarai-alerts.log 2>&1

    # زمان‌بند ویندوز — اجرای روزانه ساعت ۰۷:۳۰
    schtasks /create /tn "Tekarai Procurement Alerts" /sc daily /st 07:30 \\
      /tr "\\"C:\\tekarai\\backend\\.venv\\Scripts\\python.exe\\" C:\\tekarai\\backend\\manage.py checkProcurementAlerts"
"""

from __future__ import annotations

import logging
import time
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def scanTenants(tenantId: str = "") -> list[dict]:
    """One staleness pass over one tenant, or every tenant with requisitions."""
    from apps.procurement.application.services.requisitionAlertScan import (
        scanStaleRequisitions,
    )
    from apps.procurement.infrastructure.models import PurchaseRequisitionModel

    if tenantId:
        tenantIds = [uuid.UUID(tenantId)]
    else:
        # order_by() is load-bearing: the model's Meta.ordering is
        # ["-createdAt"], and Django adds every ordering column to a DISTINCT
        # SELECT. Without clearing it the query de-duplicates on
        # (tenantId, createdAt) and returns one row per requisition, so a
        # tenant with 200 requests would be scanned 200 times.
        tenantIds = list(
            PurchaseRequisitionModel.objects.order_by()
            .values_list("tenantId", flat=True)
            .distinct()
        )

    summaries: list[dict] = []
    for currentTenantId in tenantIds:
        dto = scanStaleRequisitions(currentTenantId)
        summaries.append(
            {
                "tenantId": str(currentTenantId),
                "asOf": dto.asOf,
                "isoWeek": dto.isoWeek,
                "staleRequisitions": dto.staleRequisitions,
            }
        )
    return summaries


class Command(BaseCommand):
    help = (
        "Alert on purchase requisitions waiting longer than their priority "
        "allows (weekly-idempotent; safe to run daily)."
    )

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument("--tenant", default="", help="Tenant id (default: all tenants).")
        parser.add_argument("--loop", action="store_true", help="Keep running on an interval.")
        parser.add_argument(
            "--interval",
            type=int,
            default=86400,
            help="Seconds between scans when --loop is set (default 86400 — daily).",
        )

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003 — Django contract
        if not options["loop"]:
            self.stdout.write(str(scanTenants(options["tenant"])))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Procurement alert scheduler looping every {options['interval']}s "
                "(Ctrl+C to stop)."
            )
        )
        try:
            while True:
                startedAt = time.monotonic()
                summaries = scanTenants(options["tenant"])
                logger.info("Procurement alert scan", extra={"summaries": summaries})
                elapsed = time.monotonic() - startedAt
                time.sleep(max(0.0, options["interval"] - elapsed))
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Procurement alert scheduler stopped."))
