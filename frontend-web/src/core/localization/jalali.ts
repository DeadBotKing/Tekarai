/**
 * Jalali (Persian / Shamsi) calendar utilities.
 *
 * Pure, dependency-free conversion between the Gregorian and Jalali calendars
 * plus Persian-localized display helpers. The whole application stores and
 * exchanges dates with the backend as ISO Gregorian strings (YYYY-MM-DD or full
 * ISO datetimes); these helpers only affect what the Persian-speaking user
 * *sees* and *selects*. Nothing here changes the wire contract.
 *
 * The conversion algorithm is the well-known Birashk/Borkowski implementation
 * (same maths as the widely-used `jalaali-js`), inlined so the build stays
 * self-contained and fully unit-testable.
 */

const PERSIAN_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

export const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

/** Weekday headers for the picker, Saturday-first (Persian week order). */
export const JALALI_WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

/** Replace ASCII digits with Persian digits (for display only). */
export function toPersianDigits(input: string | number): string {
  return String(input).replace(/[0-9]/g, (d) => PERSIAN_DIGITS[Number(d)]);
}

function div(a: number, b: number): number {
  return Math.floor(a / b);
}

/** Convert a Gregorian date (gy, gm 1-12, gd 1-31) to Jalali [jy, jm, jd]. */
export function gregorianToJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const gDaysInMonth = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    355666 +
    365 * gy +
    div(gy2 + 3, 4) -
    div(gy2 + 99, 100) +
    div(gy2 + 399, 400) +
    gd +
    gDaysInMonth.slice(0, gm - 1).reduce((a, b) => a + b, 0);
  let jy = -1595 + 33 * div(days, 12053);
  days %= 12053;
  jy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    jy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  const jm = days < 186 ? 1 + div(days, 31) : 7 + div(days - 186, 30);
  const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
  return [jy, jm, jd];
}

/** Convert a Jalali date (jy, jm 1-12, jd 1-31) to Gregorian [gy, gm, gd]. */
export function jalaliToGregorian(jy: number, jm: number, jd: number): [number, number, number] {
  let jy2 = jy + 1595;
  let days =
    -355668 +
    365 * jy2 +
    div(jy2, 33) * 8 +
    div((jy2 % 33) + 3, 4) +
    jd +
    (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
  let gy = 400 * div(days, 146097);
  days %= 146097;
  if (days > 36524) {
    gy += 100 * div(--days, 36524);
    days %= 36524;
    if (days >= 365) days++;
  }
  gy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    gy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  let gd = days + 1;
  const sal_a = [
    0,
    31,
    (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0 ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ];
  let gm = 0;
  for (gm = 0; gm < 13; gm++) {
    const v = sal_a[gm];
    if (gd <= v) break;
    gd -= v;
  }
  return [gy, gm, gd];
}

/** Number of days in a Jalali month (jm 1-12), accounting for leap years. */
export function jalaliMonthLength(jy: number, jm: number): number {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isJalaliLeapYear(jy) ? 30 : 29;
}

/** True when the given Jalali year is a leap year. */
export function isJalaliLeapYear(jy: number): boolean {
  // Derived by comparing consecutive new-year Gregorian days.
  const [gy1, gm1, gd1] = jalaliToGregorian(jy, 1, 1);
  const [gy2, gm2, gd2] = jalaliToGregorian(jy + 1, 1, 1);
  const a = Date.UTC(gy1, gm1 - 1, gd1);
  const b = Date.UTC(gy2, gm2 - 1, gd2);
  return Math.round((b - a) / 86400000) === 366;
}

/** Parse an ISO date/datetime string into a local Date, or null when invalid. */
function parseIso(value: string): Date | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return null;
  return new Date(time);
}

/** ISO string (or Date) -> Jalali parts [jy, jm, jd], or null when invalid. */
export function isoToJalaliParts(value: string | Date): [number, number, number] | null {
  const date = value instanceof Date ? value : parseIso(value);
  if (!date) return null;
  return gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
}

/** Jalali parts -> ISO date string (YYYY-MM-DD), Gregorian. */
export function jalaliPartsToIso(jy: number, jm: number, jd: number): string {
  const [gy, gm, gd] = jalaliToGregorian(jy, jm, jd);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${gy}-${pad(gm)}-${pad(gd)}`;
}

export interface FormatJalaliOptions {
  /** Append the time (HH:MM) after the date. */
  withTime?: boolean;
  /** Use Persian digits (default true). */
  persianDigits?: boolean;
  /** "long" -> "۱۲ مهر ۱۴۰۳"; "short" -> "۱۴۰۳/۰۷/۱۲" (default "long"). */
  style?: "long" | "short";
}

/**
 * Format an ISO date/datetime as a Jalali Persian string.
 * Returns the raw input when it cannot be parsed, and "" for empty input.
 */
export function formatJalali(value: string | Date, options: FormatJalaliOptions = {}): string {
  const { withTime = false, persianDigits = true, style = "long" } = options;
  if (!value) return "";
  const date = value instanceof Date ? value : parseIso(value);
  if (!date) return typeof value === "string" ? value : "";
  const [jy, jm, jd] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());

  let out: string;
  if (style === "short") {
    const pad = (n: number): string => String(n).padStart(2, "0");
    out = `${jy}/${pad(jm)}/${pad(jd)}`;
  } else {
    out = `${jd} ${JALALI_MONTHS[jm - 1]} ${jy}`;
  }

  if (withTime) {
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    out += ` – ${hh}:${mm}`;
  }

  return persianDigits ? toPersianDigits(out) : out;
}

/** Convenience: today's date as ISO (YYYY-MM-DD) in local time. */
export function todayIso(): string {
  const now = new Date();
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
