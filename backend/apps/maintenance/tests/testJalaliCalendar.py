"""Jalali conversion and recurring-holiday expansion (Phase 28.1).

The anchors are real Iranian dates, not values read back out of the
implementation — a converter that agrees with itself proves nothing.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest import TestCase

from apps.maintenance.domain.services.iranHolidays import IRAN_OFFICIAL_SOLAR_HOLIDAYS
from apps.maintenance.domain.services.jalaliCalendar import (
    dateToJalali,
    expandRecurringDates,
    gregorianToJalali,
    isJalaliLeapYear,
    jalaliMonthLength,
    jalaliToDate,
    jalaliToGregorian,
)


class JalaliConversionTests(TestCase):
    """Known Iranian dates, independently sourced."""

    ANCHORS = [
        ((1405, 1, 1), (2026, 3, 21)),  # نوروز ۱۴۰۵
        ((1405, 1, 13), (2026, 4, 2)),  # روز طبیعت
        ((1405, 11, 22), (2027, 2, 11)),  # پیروزی انقلاب
        ((1405, 12, 29), (2027, 3, 20)),  # ملی‌شدن صنعت نفت
        ((1403, 1, 1), (2024, 3, 20)),  # نوروز ۱۴۰۳ (leap year)
        ((1399, 1, 1), (2020, 3, 20)),
        ((1357, 11, 22), (1979, 2, 11)),  # پیروزی انقلاب اسلامی
    ]

    def testJalaliToGregorianMatchesKnownDates(self) -> None:
        for jalali, gregorian in self.ANCHORS:
            with self.subTest(jalali=jalali):
                self.assertEqual(jalaliToGregorian(*jalali), gregorian)

    def testGregorianToJalaliMatchesKnownDates(self) -> None:
        for jalali, gregorian in self.ANCHORS:
            with self.subTest(gregorian=gregorian):
                self.assertEqual(gregorianToJalali(*gregorian), jalali)

    def testEveryDayRoundTripsAcrossSevenYears(self) -> None:
        cursor = date(2024, 1, 1)
        end = date(2030, 12, 31)
        while cursor <= end:
            parts = dateToJalali(cursor)
            self.assertEqual(jalaliToDate(*parts), cursor, f"round trip failed on {cursor}")
            cursor += timedelta(days=1)

    def testNowruzDriftsAgainstTheGregorianCalendar(self) -> None:
        """The whole reason recurrence cannot reuse a Gregorian date.

        ۱ فروردین is 21 March in 1405 and 1406 but 20 March in 1407 — so a
        holiday "repeated" by keeping its Gregorian date would be a day wrong
        in roughly half these years.
        """
        self.assertEqual(jalaliToGregorian(1405, 1, 1), (2026, 3, 21))
        self.assertEqual(jalaliToGregorian(1406, 1, 1), (2027, 3, 21))
        self.assertEqual(jalaliToGregorian(1407, 1, 1), (2028, 3, 20))
        self.assertEqual(jalaliToGregorian(1408, 1, 1), (2029, 3, 20))

    def testLeapYearsHaveThirtyDayEsfand(self) -> None:
        self.assertTrue(isJalaliLeapYear(1403))
        self.assertTrue(isJalaliLeapYear(1408))
        self.assertFalse(isJalaliLeapYear(1405))
        self.assertEqual(jalaliMonthLength(1403, 12), 30)
        self.assertEqual(jalaliMonthLength(1405, 12), 29)

    def testMonthLengths(self) -> None:
        for month in range(1, 7):
            self.assertEqual(jalaliMonthLength(1405, month), 31)
        for month in range(7, 12):
            self.assertEqual(jalaliMonthLength(1405, month), 30)


class ExpandRecurringDatesTests(TestCase):
    def testProjectsOneHolidayAcrossEveryYearInTheWindow(self) -> None:
        found = expandRecurringDates(1, 1, date(2026, 1, 1), date(2029, 12, 31))
        self.assertEqual(
            found,
            [date(2026, 3, 21), date(2027, 3, 21), date(2028, 3, 20), date(2029, 3, 20)],
        )

    def testHonoursWindowEdgesInclusively(self) -> None:
        self.assertEqual(
            expandRecurringDates(1, 1, date(2026, 3, 21), date(2026, 3, 21)),
            [date(2026, 3, 21)],
        )

    def testExcludesAnOccurrenceJustOutsideTheWindow(self) -> None:
        self.assertEqual(expandRecurringDates(1, 1, date(2026, 3, 22), date(2026, 12, 31)), [])

    def testWindowStraddlingNowruzStillFindsIt(self) -> None:
        """A Gregorian window spans two Jalali years around نوروز."""
        found = expandRecurringDates(1, 1, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(found, [date(2026, 3, 21)])

    def testSkipsThirtiethOfEsfandInOrdinaryYears(self) -> None:
        """۳۰ اسفند is not a date in a 365-day Jalali year.

        Clamping it onto ۲۹ would close the plant on a day that is not a
        holiday, so the occurrence is dropped instead.
        """
        found = expandRecurringDates(12, 30, date(2026, 1, 1), date(2031, 12, 31))
        self.assertEqual(found, [date(2030, 3, 20)])
        self.assertEqual(dateToJalali(date(2030, 3, 20)), (1408, 12, 30))

    def testRejectsNonsenseInputRatherThanGuessing(self) -> None:
        self.assertEqual(expandRecurringDates(0, 1, date(2026, 1, 1), date(2027, 1, 1)), [])
        self.assertEqual(expandRecurringDates(13, 1, date(2026, 1, 1), date(2027, 1, 1)), [])
        self.assertEqual(expandRecurringDates(1, 0, date(2026, 1, 1), date(2027, 1, 1)), [])

    def testInvertedWindowYieldsNothing(self) -> None:
        self.assertEqual(expandRecurringDates(1, 1, date(2029, 1, 1), date(2026, 1, 1)), [])


class IranOfficialHolidayTableTests(TestCase):
    def testTableIsTheSolarSetOnly(self) -> None:
        self.assertEqual(len(IRAN_OFFICIAL_SOLAR_HOLIDAYS), 10)
        for month, day, name in IRAN_OFFICIAL_SOLAR_HOLIDAYS:
            self.assertTrue(1 <= month <= 12)
            self.assertTrue(1 <= day <= 31)
            self.assertTrue(name.strip())

    def testEveryEntryResolvesToARealDateIn1405(self) -> None:
        for month, day, _name in IRAN_OFFICIAL_SOLAR_HOLIDAYS:
            self.assertLessEqual(day, jalaliMonthLength(1405, month))
            self.assertIsInstance(jalaliToDate(1405, month, day), date)

    def testMatchesTheDatesSeededForYear1405(self) -> None:
        """Guards the refactor that moved this table out of `seedDemo`."""
        expected = {
            (1, 1): date(2026, 3, 21),
            (1, 12): date(2026, 4, 1),
            (1, 13): date(2026, 4, 2),
            (3, 14): date(2026, 6, 4),
            (3, 15): date(2026, 6, 5),
            (11, 22): date(2027, 2, 11),
            (12, 29): date(2027, 3, 20),
        }
        for (month, day), gregorian in expected.items():
            self.assertEqual(jalaliToDate(1405, month, day), gregorian)
