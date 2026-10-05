/**
 * One place that decides how a number, a date or a time is written.
 *
 * Before this module the application mixed four conventions in the same
 * viewport: `toLocaleString("fa-IR")`, `toLocaleString("en-US")`,
 * `toLocaleString()` (whatever the host browser defaults to) and raw ISO
 * strings straight off the wire. The maintenance dashboard showed "۱۰۰%" on a
 * card and "100%" inside the donut next to it; the users table showed
 * "10/5/2026" — a US month/day/year date — in a right-to-left Persian page.
 *
 * Rules encoded here:
 * - Persian renders Jalali dates and Persian digits. That is the product
 *   default and what every Persian-speaking operator expects.
 * - English and German render Gregorian dates and Latin digits.
 * - Everything still travels to and from the backend as ISO Gregorian. These
 *   helpers only change what the user sees.
 */

import { formatJalali, toPersianDigits } from "./jalali";
import type { Locale } from "./i18n";

/** Locales whose numerals are written with Persian (Eastern Arabic) digits. */
const PERSIAN_DIGIT_LOCALES: ReadonlySet<Locale> = new Set<Locale>(["fa"]);

/** The BCP-47 tag used for grouping/decimal separators per product locale. */
const INTL_TAG: Record<Locale, string> = {
  // "fa-IR" would also give Persian digits, but it drags in the Persian
  // thousands separator in some engines and not others. Grouping is done with
  // a stable Latin locale and the digits are transliterated afterwards, so the
  // output is identical in every browser and in jsdom.
  fa: "en-US",
  en: "en-US",
  de: "de-DE",
};

export interface FormatNumberOptions {
  /** Maximum fraction digits (default 0 — counts and currency-less totals). */
  maximumFractionDigits?: number;
  minimumFractionDigits?: number;
  /** Thousands grouping (default true). */
  useGrouping?: boolean;
}

/** Format a number for display: grouped, then localized to the right digits. */
export function formatNumber(
  value: number | null | undefined,
  locale: Locale,
  options: FormatNumberOptions = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const { maximumFractionDigits = 0, minimumFractionDigits, useGrouping = true } = options;
  const text = value.toLocaleString(INTL_TAG[locale], {
    maximumFractionDigits,
    ...(minimumFractionDigits === undefined ? {} : { minimumFractionDigits }),
    useGrouping,
  });
  return PERSIAN_DIGIT_LOCALES.has(locale) ? toPersianDigits(text) : text;
}

/** Format a percentage, including the sign, in the locale's digit shape. */
export function formatPercent(
  value: number | null | undefined,
  locale: Locale,
  options: FormatNumberOptions = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${formatNumber(value, locale, options)}%`;
}

/** Digits only — no grouping, no rounding. For values already stringified. */
export function localizeDigits(text: string | number, locale: Locale): string {
  return PERSIAN_DIGIT_LOCALES.has(locale) ? toPersianDigits(text) : String(text);
}

function parseDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export interface FormatDateOptions {
  /** Append the clock time after the date. */
  withTime?: boolean;
  /** "long" -> "۱۲ مهر ۱۴۰۵"; "short" -> "۱۴۰۵/۰۷/۱۲". */
  style?: "long" | "short";
  /** Rendered when the value is empty or unparsable (default "—"). */
  fallback?: string;
}

/**
 * Format an ISO date/datetime for display.
 *
 * Persian gets the Jalali calendar; the Gregorian locales get an unambiguous
 * ISO-like or month-name form — never the host default, which is how
 * "10/5/2026" ended up in a Persian page.
 */
export function formatDate(
  value: string | Date | null | undefined,
  locale: Locale,
  options: FormatDateOptions = {},
): string {
  const { withTime = false, style = "long", fallback = "—" } = options;
  const date = parseDate(value);
  if (!date) return fallback;

  if (locale === "fa") {
    return formatJalali(date, { withTime, style, persianDigits: true });
  }

  const pad = (n: number): string => String(n).padStart(2, "0");
  let out: string;
  if (style === "short") {
    // ISO order: unambiguous for every reader, unlike M/D/Y vs D/M/Y.
    out = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  } else {
    out = date.toLocaleDateString(INTL_TAG[locale], {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
  if (withTime) out += ` – ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  return out;
}

/** Shorthand for a date plus clock time. */
export function formatDateTime(
  value: string | Date | null | undefined,
  locale: Locale,
  options: Omit<FormatDateOptions, "withTime"> = {},
): string {
  return formatDate(value, locale, { ...options, withTime: true });
}

/** Clock time only (HH:MM), in the locale's digit shape. */
export function formatTime(
  value: string | Date | null | undefined,
  locale: Locale,
  fallback = "—",
): string {
  const date = parseDate(value);
  if (!date) return fallback;
  const pad = (n: number): string => String(n).padStart(2, "0");
  return localizeDigits(`${pad(date.getHours())}:${pad(date.getMinutes())}`, locale);
}
