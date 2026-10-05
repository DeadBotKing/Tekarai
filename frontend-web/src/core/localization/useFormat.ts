import { useMemo } from "react";
import { useLocaleOrDefault } from "./localizationContext";
import {
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatTime,
  localizeDigits,
  type FormatDateOptions,
  type FormatNumberOptions,
} from "./format";

export interface Formatters {
  number: (value: number | null | undefined, options?: FormatNumberOptions) => string;
  percent: (value: number | null | undefined, options?: FormatNumberOptions) => string;
  date: (value: string | Date | null | undefined, options?: FormatDateOptions) => string;
  dateTime: (
    value: string | Date | null | undefined,
    options?: Omit<FormatDateOptions, "withTime">,
  ) => string;
  time: (value: string | Date | null | undefined, fallback?: string) => string;
  digits: (text: string | number) => string;
}

/**
 * Locale-bound number and date formatters.
 *
 * Components should reach for this instead of calling `toLocaleString` or
 * `toLocaleDateString` directly — those pick up the *browser's* locale, not
 * the one the user selected in the app, which is how a Persian page ended up
 * printing US-format dates.
 */
export function useFormat(): Formatters {
  const locale = useLocaleOrDefault();
  return useMemo<Formatters>(
    () => ({
      number: (value, options) => formatNumber(value, locale, options),
      percent: (value, options) => formatPercent(value, locale, options),
      date: (value, options) => formatDate(value, locale, options),
      dateTime: (value, options) => formatDateTime(value, locale, options),
      time: (value, fallback) => formatTime(value, locale, fallback),
      digits: (text) => localizeDigits(text, locale),
    }),
    [locale],
  );
}
