"""The production-safe official-holiday loader (Phase 28.1).

`seedDemo` also inserts demo devices, locations and cost centres, so it is not
a safe way for a real plant to obtain the official calendar. This command is,
and these tests hold it to that promise.
"""

from __future__ import annotations

import uuid
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone as djtz

from apps.maintenance.infrastructure.models import (
    CalendarHolidayModel,
    DeviceModel,
    MaintenanceLocationModel,
    WorkCalendarModel,
)

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")


class SeedIranHolidaysTests(TestCase):
    def _calendar(self, code: str, *, isDefault: bool = False) -> WorkCalendarModel:
        return WorkCalendarModel.objects.create(
            tenantId=TENANT,
            code=code,
            name=f"تقویم {code}",
            timezone="Asia/Tehran",
            weekendDays="4",
            rollPolicy="forward",
            isDefault=isDefault,
            active=True,
            createdAt=djtz.now(),
        )

    def _run(self, **kwargs) -> str:
        out = StringIO()
        call_command("seedIranHolidays", stdout=out, **kwargs)
        return out.getvalue()

    def _holidays(self, calendar) -> list[CalendarHolidayModel]:
        return list(
            CalendarHolidayModel.objects.filter(
                calendarId=calendar.id, deletedAt__isnull=True
            ).order_by("onDate")
        )

    def testLoadsTheSolarHolidaysOntoTheDefaultCalendar(self) -> None:
        calendar = self._calendar("CAL-MAIN", isDefault=True)
        self._run(year=1405)
        rows = self._holidays(calendar)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0].onDate, date(2026, 3, 21))
        self.assertEqual(rows[0].name, "نوروز")

    def testEveryRowIsMarkedRecurringAndPinnedToItsJalaliDate(self) -> None:
        """Without this the rows would need re-entering every year."""
        calendar = self._calendar("CAL-MAIN", isDefault=True)
        self._run(year=1405)
        for row in self._holidays(calendar):
            self.assertTrue(row.recursAnnually)
            self.assertGreaterEqual(row.jalaliMonth, 1)
            self.assertGreaterEqual(row.jalaliDay, 1)

    def testRunningTwiceAddsNothingTheSecondTime(self) -> None:
        calendar = self._calendar("CAL-MAIN", isDefault=True)
        self._run(year=1405)
        output = self._run(year=1405)
        self.assertEqual(len(self._holidays(calendar)), 10)
        self.assertIn("10 already present", output)

    def testTouchesNoDemoDataAtAll(self) -> None:
        """The whole reason this exists instead of `seedDemo`."""
        self._calendar("CAL-MAIN", isDefault=True)
        self._run(year=1405)
        self.assertEqual(DeviceModel.objects.count(), 0)
        self.assertEqual(MaintenanceLocationModel.objects.count(), 0)

    def testTargetsANamedCalendar(self) -> None:
        default = self._calendar("CAL-MAIN", isDefault=True)
        north = self._calendar("CAL-NORTH")
        self._run(calendar="CAL-NORTH", year=1405)
        self.assertEqual(len(self._holidays(north)), 10)
        self.assertEqual(len(self._holidays(default)), 0)

    def testAllCalendarsOptionCoversEveryCalendar(self) -> None:
        default = self._calendar("CAL-MAIN", isDefault=True)
        north = self._calendar("CAL-NORTH")
        self._run(all_calendars=True, year=1405)
        self.assertEqual(len(self._holidays(default)), 10)
        self.assertEqual(len(self._holidays(north)), 10)

    def testDryRunReportsWithoutWriting(self) -> None:
        calendar = self._calendar("CAL-MAIN", isDefault=True)
        output = self._run(year=1405, dry_run=True)
        self.assertEqual(len(self._holidays(calendar)), 0)
        self.assertIn("would add 10", output)

    def testDifferentJalaliYearsLandOnDifferentGregorianDates(self) -> None:
        """Proof the command converts rather than hardcoding 1405."""
        calendar = self._calendar("CAL-MAIN", isDefault=True)
        self._run(year=1407)
        dates = {row.onDate for row in self._holidays(calendar)}
        self.assertIn(date(2028, 3, 20), dates)  # نوروز ۱۴۰۷
        self.assertNotIn(date(2026, 3, 21), dates)

    def testFailsLoudlyWhenNoCalendarExists(self) -> None:
        with self.assertRaises(CommandError) as caught:
            self._run(year=1405)
        self.assertIn("No work calendar", str(caught.exception))

    def testFailsOnAnUnknownCalendarCode(self) -> None:
        self._calendar("CAL-MAIN", isDefault=True)
        with self.assertRaises(CommandError):
            self._run(calendar="CAL-NOPE", year=1405)

    def testRejectsANonsenseYear(self) -> None:
        self._calendar("CAL-MAIN", isDefault=True)
        with self.assertRaises(CommandError):
            self._run(year=2026)  # a Gregorian year slipped in by mistake

    def testSkipsThirtiethOfEsfandInAnOrdinaryYear(self) -> None:
        calendar = self._calendar("CAL-MAIN", isDefault=True)
        self._run(year=1405)
        # 1405 is not a leap year, so ۲۹ اسفند is the last day; nothing in the
        # table should have produced a 30th.
        for row in self._holidays(calendar):
            self.assertLessEqual(row.jalaliDay, 29 if row.jalaliMonth == 12 else 31)
