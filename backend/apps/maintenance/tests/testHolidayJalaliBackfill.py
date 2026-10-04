"""Migration 0019 repairs holidays saved before the Jalali parts were derived.

The data migration itself is a single `RunPython` around `backfillJalaliParts`,
so the function is exercised directly here against real rows rather than
driving the migration executor.
"""

from __future__ import annotations

import uuid
from datetime import date

from django.apps import apps as djangoApps
from django.test import TestCase
from django.utils import timezone as djtz

TENANT = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _loadBackfill():
    import importlib

    module = importlib.import_module(
        "apps.maintenance.infrastructure.migrations.0019_backfillHolidayJalaliParts"
    )
    return module.backfillJalaliParts


class HolidayJalaliBackfillTests(TestCase):
    def _holiday(self, onDate: date, *, month: int = 0, day: int = 0, recurs: bool = True):
        Holiday = djangoApps.get_model("maintenance", "CalendarHolidayModel")
        return Holiday.objects.create(
            tenantId=TENANT,
            calendarId=uuid.uuid4(),
            onDate=onDate,
            name="نوروز",
            kind="official",
            recursAnnually=recurs,
            jalaliMonth=month,
            jalaliDay=day,
            createdAt=djtz.now(),
        )

    def _run(self) -> None:
        _loadBackfill()(djangoApps, None)

    def _reload(self, row):
        row.refresh_from_db()
        return row

    def testFillsTheMissingPartsFromTheStoredDate(self) -> None:
        row = self._holiday(date(2026, 3, 21))
        self._run()
        row = self._reload(row)
        self.assertEqual((row.jalaliMonth, row.jalaliDay), (1, 1))

    def testRepairsARowThatWasAlreadyFlaggedRecurring(self) -> None:
        """These are the rows the old UI produced: ticked, but unprojectable."""
        row = self._holiday(date(2027, 2, 11), recurs=True)
        self._run()
        row = self._reload(row)
        self.assertTrue(row.recursAnnually)
        self.assertEqual((row.jalaliMonth, row.jalaliDay), (11, 22))

    def testLeavesCorrectRowsAlone(self) -> None:
        row = self._holiday(date(2026, 4, 2), month=1, day=13)
        self._run()
        row = self._reload(row)
        self.assertEqual((row.jalaliMonth, row.jalaliDay), (1, 13))

    def testDoesNotInventPartsForANonRecurringRow(self) -> None:
        """A one-off shutdown gets its parts too — harmless, and correct."""
        row = self._holiday(date(2026, 8, 10), recurs=False)
        self._run()
        row = self._reload(row)
        self.assertFalse(row.recursAnnually)
        self.assertEqual(row.jalaliMonth, 5)

    def testIsIdempotent(self) -> None:
        row = self._holiday(date(2026, 3, 21))
        self._run()
        self._run()
        row = self._reload(row)
        self.assertEqual((row.jalaliMonth, row.jalaliDay), (1, 1))

    def testRepairedRowsBecomeProjectable(self) -> None:
        """The point of the exercise: recurrence works afterwards."""
        from apps.maintenance.domain.services.jalaliCalendar import expandRecurringDates

        row = self._holiday(date(2026, 3, 21))
        self._run()
        row = self._reload(row)
        occurrences = expandRecurringDates(
            row.jalaliMonth, row.jalaliDay, date(2028, 1, 1), date(2028, 12, 31)
        )
        self.assertEqual(occurrences, [date(2028, 3, 20)])
