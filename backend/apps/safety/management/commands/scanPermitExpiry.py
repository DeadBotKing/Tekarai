"""Scheduled check on permit validity windows.

What it does, and the asymmetry that matters:

* **Approved but never started**, past its window → expired automatically.
  Nobody is on the job. Leaving a dead authorisation sitting in the
  approved list is how somebody picks it up the next morning and works
  under a permit whose conditions were assessed for yesterday.
* **Active or suspended**, past its window → **never auto-expired**, only
  alarmed. People may be inside a vessel right now. Flipping their permit
  to ``expired`` does not get them out; it only deletes the record that
  they are there and removes them from the live board the control room is
  watching. A human has to go and close it.
* **Within the last hour** → a heads-up, while there is still time to
  extend in an orderly way rather than stopping work mid-task.

**Dry run is the default.** A cron line that expires permits should only do
so because someone explicitly asked for ``--apply``.

Usage:
    python manage.py scanPermitExpiry                  # پیش‌نمایش، بدون تغییر
    python manage.py scanPermitExpiry --apply          # اعمال انقضا و ارسال هشدار
    python manage.py scanPermitExpiry --tenant <uuid> --apply

Production wiring — run this **often**, not daily. A permit window is
measured in hours, so an hourly scan is the sensible floor and every
fifteen minutes is better:

    # cron — هر ۱۵ دقیقه
    */15 * * * * cd /srv/tekarai/backend && \\
                 .venv/bin/python manage.py scanPermitExpiry --apply >> /var/log/tekarai-permits.log 2>&1

    # زمان‌بند ویندوز — هر ۱۵ دقیقه
    schtasks /create /tn "Tekarai Permit Expiry" /sc minute /mo 15 \\
      /tr "\\"C:\\tekarai\\backend\\.venv\\Scripts\\python.exe\\" C:\\tekarai\\backend\\manage.py scanPermitExpiry --apply"
"""

from __future__ import annotations

import logging
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def runScan(tenantId: str = "", *, apply: bool = False) -> list[dict]:
    """One expiry pass over one tenant, or every tenant holding permits."""
    from apps.safety.application.services.permitService import scanPermitExpiry
    from apps.safety.infrastructure.permitRepository import tenantIdsWithLivePermits

    tenantIds = [uuid.UUID(tenantId)] if tenantId else tenantIdsWithLivePermits()

    summaries: list[dict] = []
    for currentTenantId in tenantIds:
        result = scanPermitExpiry(currentTenantId, apply=apply)
        summaries.append({"tenantId": str(currentTenantId), **result})
    return summaries


class Command(BaseCommand):
    help = "بررسی اعتبار مجوزهای کار: انقضای مجوزهای شروع‌نشده و هشدار برای کارهای در جریان"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="اعمال واقعی: انقضای مجوزهای شروع‌نشده و ارسال هشدارها.",
        )
        parser.add_argument(
            "--tenant", default="", help="محدود کردن بررسی به یک سازمان (UUID)."
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        summaries = runScan(options["tenant"], apply=apply)

        if not summaries:
            self.stdout.write("هیچ مجوز فعالی برای بررسی وجود ندارد.")
            return

        totalExpired = 0
        totalOverdue = 0
        totalSoon = 0

        for summary in summaries:
            expired = summary["expired"]
            overdue = summary["overdueWithWorkInProgress"]
            soon = summary["expiringSoon"]
            totalExpired += len(expired)
            totalOverdue += len(overdue)
            totalSoon += len(soon)

            if not (expired or overdue or soon):
                continue

            self.stdout.write(f"\nسازمان {summary['tenantId']}")
            if expired:
                verb = "منقضی شد" if apply else "منقضی می‌شود"
                self.stdout.write(f"  مجوزهای شروع‌نشده که اعتبارشان گذشته ({verb}):")
                for number in expired:
                    self.stdout.write(f"    - {number}")
            if overdue:
                # The loudest line in the output on purpose: this is the one
                # that means someone may still be on the job.
                self.stdout.write(
                    self.style.ERROR(
                        "  هشدار — کار در جریان با مجوز منقضی‌شده "
                        "(به‌صورت خودکار بسته نمی‌شود، نیاز به بررسی انسانی):"
                    )
                )
                for number in overdue:
                    self.stdout.write(self.style.ERROR(f"    - {number}"))
            if soon:
                self.stdout.write("  نزدیک به پایان اعتبار (کمتر از یک ساعت):")
                for number in soon:
                    self.stdout.write(f"    - {number}")

        self.stdout.write(
            f"\nجمع: {totalExpired} منقضی، {totalOverdue} کار در جریان با مجوز گذشته، "
            f"{totalSoon} نزدیک به انقضا."
        )
        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "این یک پیش‌نمایش بود؛ هیچ تغییری ثبت نشد. برای اعمال، --apply را اضافه کنید."
                )
            )
