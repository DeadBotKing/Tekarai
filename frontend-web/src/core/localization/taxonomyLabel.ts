import type { TranslationKey } from "./i18n";

type Translate = (key: TranslationKey, variables?: Record<string, string | number>) => string;

/**
 * Label an open-vocabulary value (Phase 26.1).
 *
 * Canonical codes (`mechanical`, `site`, `vital`, …) have a Persian label in the
 * dictionary. A value the plant added at run time («جوشکاری», «سوله») has none —
 * and it is already written in the operator's own words, so it is shown as it
 * was typed instead of leaking a dictionary key into the UI.
 */
export function taxonomyLabel(t: Translate, prefix: string, value: string): string {
  if (!value) return "";
  const key = `${prefix}${value}`;
  const label = t(key as TranslationKey);
  return label === key ? value : label;
}
