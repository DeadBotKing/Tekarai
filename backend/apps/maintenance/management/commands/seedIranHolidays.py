"""Load Iran's official solar holidays onto a work calendar.

Unlike `seedDemo` this touches **nothing but holidays** — no demo devices, no
fake locations, no cost centres — so it is safe to run against a real tenant's
database.

Each holiday is written once, marked `recursAnnually` and pinned to its Jalali
month and day, so it closes the plant on the right Gregorian date in every
future year without being re-entered. Lunar holidays (عاشورا, عید فطر, …) move
every year on moon sighting and are deliberately not included; enter them per
year from the holidays screen.

Re-running is safe: a holiday is treated as already present when the calendar
carries a row on the same date **or** a recurring row for the same Jalali day
in any year, so an existing rule is left alone rather than duplicated.

    python manage.py seedIranHolidays
    python manage.py seedIranHolidays --calendar CAL-NORTH --year 1406
    python manage.py seedIranHolidays --all-calendars --dry-run
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.core.management.base import BaseCommand, CommandError

from apps.maintenance.domain.services.iranHolidays import IRAN_OFFICIAL_SOLAR_HOLIDAYS
from apps.maintenance.domain.services.jalaliCalendar import (
    dateToJalali,
    jalaliMonthLength,
    jalaliToDate,
)
from apps.maintenance.infrastructure.models import (
    CalendarHolidayModel,
    WorkCalendarModel,
)


class Command(BaseCommand):
    help = "Load Iran's official solar public holidays onto a work calendar."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--calendar",
            default="",
            help="Calendar code. Defaults to the tenant's default calendar.",
        )
        parser.add_argument(
            "--all-calendars",
            action="store_true",
            help="Apply to every active calendar instead of just one.",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=0,
            help="Jalali year to anchor the rows to. Defaults to the current one.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be written without touching the database.",
        )

    def handle(self, *args, **options) -> None:
        code = (options.get("calendar") or "").strip()
        everyCalendar = bool(options.get("all_calendars"))
        dryRun = bool(options.get("dry_run"))
        jalaliYear = int(options.get("year") or 0)

        if jalaliYear <= 0:
            jalaliYear = dateToJalali(datetime.now(UTC).date())[0]
        if not 1300 <= jalaliYear <= 1500:
            raise CommandError(f"Jalali year {jalaliYear} is outside a sensible range.")

        calendars = self._resolveCalendars(code, everyCalendar)
        if not calendars:
            raise CommandError(
                "No work calendar found. Create one first "
                "(نگهداری و تعمیرات → تقویم کاری), then re-run."
            )

        now = datetime.now(UTC)
        totalWritten = 0
        totalSkipped = 0

        for calendar in calendars:
            written, skipped = self._seedOne(calendar, jalaliYear, now, dryRun)
            totalWritten += written
            totalSkipped += skipped
            self.stdout.write(
                f"  {calendar.code or calendar.id}: {written} added, {skipped} already present"
            )

        verb = "would add" if dryRun else "added"
        self.stdout.write(
            self.style.SUCCESS(
                f"Iran official solar holidays for {jalaliYear}: "
                f"{verb} {totalWritten}, skipped {totalSkipped}."
            )
        )
        self.stdout.write(
            "Lunar holidays (عید فطر, تاسوعا, عاشورا …) shift each year and must "
            "be entered per year from the holidays screen."
        )

    def _resolveCalendars(self, code: str, everyCalendar: bool) -> list:
        rows = WorkCalendarModel.objects.filter(deletedAt__isnull=True, active=True)
        if code:
            found = list(rows.filter(code=code))
            if not found:
                raise CommandError(f"No active calendar with code «{code}».")
            return found
        if everyCalendar:
            return list(rows.order_by("code"))
        default = list(rows.filter(isDefault=True))
        return default or list(rows.order_by("code")[:1])

    def _seedOne(self, calendar, jalaliYear: int, now, dryRun: bool) -> tuple[int, int]:
        written = 0
        skipped = 0
        for jMonth, jDay, title in IRAN_OFFICIAL_SOLAR_HOLIDAYS:
            # ۳۰ اسفند only exists in a leap Jalali year.
            if jDay > jalaliMonthLength(jalaliYear, jMonth):
                continue
            onDate = jalaliToDate(jalaliYear, jMonth, jDay)
            onCalendar = CalendarHolidayModel.objects.filter(
                tenantId=calendar.tenantId,
                calendarId=calendar.id,
                deletedAt__isnull=True,
            )
            # Two different ways this day can already be covered.
            #
            # The obvious one is a row on the very same date. The one that
            # actually bites is a *recurring* row for the same Jalali day
            # stored under a different year: it already projects onto this
            # date and every future one, so adding another would create a
            # second rule that fires identically forever — two «نوروز» lines
            # in the holidays tab, neither of them wrong, both of them noise.
            # Matching on `onDate` alone cannot see it, because the dates
            # differ by year.
            exists = (
                onCalendar.filter(onDate=onDate).exists()
                or onCalendar.filter(
                    recursAnnually=True, jalaliMonth=jMonth, jalaliDay=jDay
                ).exists()
            )
            if exists:
                skipped += 1
                continue
            written += 1
            if dryRun:
                continue
            CalendarHolidayModel.objects.create(
                tenantId=calendar.tenantId,
                calendarId=calendar.id,
                onDate=onDate,
                name=title,
                kind="official",
                recursAnnually=True,
                jalaliMonth=jMonth,
                jalaliDay=jDay,
                createdAt=now,
            )
        return written, skipped
