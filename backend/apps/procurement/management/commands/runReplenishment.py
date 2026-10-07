"""Scheduled stock→purchase loop — raise draft purchase requests from low stock.

Reads every tenant's warehouse, works out what has fallen to or below its
minimum once goods already on order are counted, and (with ``--apply``)
raises one draft purchase requisition per supplier.

**Dry run is the default.** Writing purchase documents is not something a
cron line should start doing because somebody mistyped a command, so the
bare invocation prints what it would do and changes nothing. ``--apply`` is
the explicit opt-in.

Running this daily is safe and is the intended cadence. The scan counts open
requisitions and undelivered order balances as incoming stock, so once a
draft exists for a part the part stops qualifying — a second run the same
day proposes nothing, and no notification is repeated.

Usage:
    python manage.py runReplenishment                     # پیش‌نمایش، بدون تغییر
    python manage.py runReplenishment --apply             # ساخت پیش‌نویس‌ها
    python manage.py runReplenishment --tenant <uuid> --apply

Production wiring:

    # cron — هر روز ساعت ۰۶:۰۰ به وقت سرور
    0 6 * * * cd /srv/tekarai/backend && \\
              .venv/bin/python manage.py runReplenishment --apply >> /var/log/tekarai-replenish.log 2>&1

    # زمان‌بند ویندوز — اجرای روزانه ساعت ۰۶:۰۰
    schtasks /create /tn "Tekarai Replenishment" /sc daily /st 06:00 \\
      /tr "\\"C:\\tekarai\\backend\\.venv\\Scripts\\python.exe\\" C:\\tekarai\\backend\\manage.py runReplenishment --apply"
"""

from __future__ import annotations

import logging
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def runScan(tenantId: str = "", *, apply: bool = False) -> list[dict]:
    """One replenishment pass over one tenant, or every tenant holding stock."""
    from apps.maintenance.application.services.inventoryContract import tenantIdsWithStock
    from apps.procurement.application.services.replenishmentScan import scanReplenishment

    # Which tenants hold stock is the warehouse's question, so it is asked
    # through maintenance's public contract rather than by reaching into
    # its tables.
    tenantIds = [uuid.UUID(tenantId)] if tenantId else tenantIdsWithStock()

    summaries: list[dict] = []
    for currentTenantId in tenantIds:
        dto = scanReplenishment(currentTenantId, apply=apply)
        summaries.append(
            {
                "tenantId": str(currentTenantId),
                "asOf": dto.asOf,
                "suggested": dto.suggestedCount,
                "estimatedTotal": str(dto.estimatedTotal),
                "createdRequisitions": dto.createdRequisitions,
                "applied": apply,
            }
        )
    return summaries


class Command(BaseCommand):
    help = (
        "Raise draft purchase requisitions for spare parts at or below minimum "
        "stock, counting goods already on order. Dry run unless --apply."
    )

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument("--tenant", default="", help="Tenant id (default: all tenants).")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually create the draft requisitions (default: preview only).",
        )

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003 — Django contract
        summaries = runScan(options["tenant"], apply=options["apply"])
        for summary in summaries:
            self.stdout.write(str(summary))
        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("پیش‌نمایش بود؛ برای ساخت درخواست‌ها --apply را اضافه کنید.")
            )
        else:
            created = sum(len(x["createdRequisitions"]) for x in summaries)
            self.stdout.write(self.style.SUCCESS(f"{created} پیش‌نویس درخواست خرید ساخته شد."))
