"""Jalali (Solar Hijri) ↔ Gregorian conversion, and recurring-holiday expansion.

Iran's official solar holidays are fixed in the *Jalali* calendar: نوروز is
always ۱ فروردین, پیروزی انقلاب is always ۲۲ بهمن. Their Gregorian date drifts
by a day depending on leap years, so a holiday marked "recurs annually" cannot
be projected into the next year by simply reusing the same month and day of the
Gregorian calendar — that would be wrong roughly one year in four.

This module is deliberately dependency-free. `jdatetime`, `khayyam` and
`persiantools` are all absent from the virtualenv and adding one for ~60 lines
of integer arithmetic was not worth the supply-chain cost. The algorithm is a
direct port of `frontend-web/src/core/localization/jalali.ts` so the two halves
of the product can never disagree about what day نوروز falls on.

Everything here is pure: no Django, no I/O, no clock.

EVOLUTION NOTE (Phase 28.1): added when `recursAnnually` was found to be a dead
column — stored and returned by the API, but never consulted when deciding
whether a day was closed.
"""

from __future__ import annotations

from datetime import date

__all__ = [
    "GREGORIAN_MONTH_DAYS",
    "expandRecurringDates",
    "gregorianToJalali",
    "isJalaliLeapYear",
    "jalaliMonthLength",
    "jalaliToGregorian",
    "jalaliToDate",
    "dateToJalali",
]

GREGORIAN_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# The Jalali year that `date.min`/`date.max` comfortably bracket. Guards the
# expansion loop against a nonsense window.
_MIN_JALALI_YEAR = 1
_MAX_JALALI_YEAR = 3000


def _div(numerator: int, denominator: int) -> int:
    """Integer division truncating toward zero, matching the JS original.

    Python's `//` floors, which differs from JS for negative numerators. Every
    call site here is non-negative in practice, but keeping the semantics
    identical means the port cannot silently diverge for pre-epoch dates.
    """
    quotient = abs(numerator) // abs(denominator)
    return quotient if (numerator >= 0) == (denominator > 0) else -quotient


def gregorianToJalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to Jalali `(year, month 1-12, day)`."""
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + _div(gy2 + 3, 4)
        - _div(gy2 + 99, 100)
        + _div(gy2 + 399, 400)
        + gd
        + sum(GREGORIAN_MONTH_DAYS[: gm - 1])
    )
    jy = -1595 + 33 * _div(days, 12053)
    days %= 12053
    jy += 4 * _div(days, 1461)
    days %= 1461
    if days > 365:
        jy += _div(days - 1, 365)
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + _div(days, 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + _div(days - 186, 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalaliToGregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Convert a Jalali date to Gregorian `(year, month 1-12, day)`."""
    jy2 = jy + 1595
    days = (
        -355668
        + 365 * jy2
        + _div(jy2, 33) * 8
        + _div((jy2 % 33) + 3, 4)
        + jd
        + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    )
    gy = 400 * _div(days, 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * _div(days, 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * _div(days, 1461)
    days %= 1461
    if days > 365:
        gy += _div(days - 1, 365)
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    monthDays = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for gm in range(13):
        if gd <= monthDays[gm]:
            break
        gd -= monthDays[gm]
    return gy, gm, gd


def isJalaliLeapYear(jy: int) -> bool:
    """True when the Jalali year runs to 366 days (اسفند has 30, not 29)."""
    start = jalaliToDate(jy, 1, 1)
    nextStart = jalaliToDate(jy + 1, 1, 1)
    return (nextStart - start).days == 366


def jalaliMonthLength(jy: int, jm: int) -> int:
    """Days in a Jalali month: 31 for فروردین-شهریور, 30 for مهر-بهمن, 29/30 اسفند."""
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if isJalaliLeapYear(jy) else 29


def jalaliToDate(jy: int, jm: int, jd: int) -> date:
    """Jalali parts as a `datetime.date`."""
    gy, gm, gd = jalaliToGregorian(jy, jm, jd)
    return date(gy, gm, gd)


def dateToJalali(value: date) -> tuple[int, int, int]:
    """A `datetime.date` as Jalali parts."""
    return gregorianToJalali(value.year, value.month, value.day)


def expandRecurringDates(jalaliMonth: int, jalaliDay: int, start: date, end: date) -> list[date]:
    """Every Gregorian date on which a fixed Jalali month/day falls in a window.

    A holiday pinned to ۱ فروردین recurs on a different Gregorian date each
    year, and a window can straddle نوروز, so the Jalali years overlapping
    `[start, end]` are walked rather than assuming one.

    ۳۰ اسفند only exists in a leap Jalali year; in an ordinary year the date is
    simply absent and is skipped rather than being silently clamped onto ۲۹,
    which would close the plant on a day that is not a holiday.
    """
    if not (1 <= jalaliMonth <= 12) or not (1 <= jalaliDay <= 31):
        return []
    if end < start:
        return []

    firstYear = dateToJalali(start)[0]
    lastYear = dateToJalali(end)[0]
    if firstYear < _MIN_JALALI_YEAR or lastYear > _MAX_JALALI_YEAR:
        return []

    out: list[date] = []
    for jy in range(firstYear, lastYear + 1):
        if jalaliDay > jalaliMonthLength(jy, jalaliMonth):
            continue
        occurrence = jalaliToDate(jy, jalaliMonth, jalaliDay)
        if start <= occurrence <= end:
            out.append(occurrence)
    return out
