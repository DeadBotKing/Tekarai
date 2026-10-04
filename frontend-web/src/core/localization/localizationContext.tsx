import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { localeMeta, translate, type Direction, type Locale, type TranslationKey } from "./i18n";

// v4: Persian is the product default and the frame now follows the locale —
// Persian renders right-to-left, English and German left-to-right. Bumping
// the key drops stale persisted values from the earlier experimental builds.
const LOCALE_KEY = "tekarai.gui.locale.v4";

const initialLocale = (): Locale => {
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored === "en" || stored === "fa" || stored === "de") return stored;
  } catch {
    // Use the stable default when storage is unavailable.
  }
  // فارسی برای همه — متن و قالب، هر دو.
  return "fa";
};

interface LocalizationContextValue {
  locale: Locale;
  direction: Direction;
  setLocale: (locale: Locale) => void;
  cycleLocale: () => void;
  t: (key: TranslationKey, variables?: Record<string, string | number>) => string;
}

const LocalizationContext = createContext<LocalizationContextValue | null>(null);

export function LocalizationProvider({ children }: { children: ReactNode }): JSX.Element {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  // The layout mirrors with the language: Persian is read right-to-left, so
  // the frame is too. Elements holding Latin content (codes, ids, URLs,
  // charts) pin their own direction and stay readable either way.
  const direction: Direction = localeMeta[locale].direction;

  useEffect(() => {
    const root = document.documentElement;
    root.lang = locale;
    root.dir = direction;
    root.dataset.direction = direction;
    try {
      localStorage.setItem(LOCALE_KEY, locale);
    } catch {
      // Localized state still applies to the current session.
    }
  }, [direction, locale]);

  const setLocale = (nextLocale: Locale): void => setLocaleState(nextLocale);
  const cycleLocale = (): void => {
    const locales: Locale[] = ["en", "fa", "de"];
    const next = locales[(locales.indexOf(locale) + 1) % locales.length];
    setLocaleState(next);
  };
  const value = useMemo<LocalizationContextValue>(() => ({
    locale,
    direction,
    setLocale,
    cycleLocale,
    t: (key, variables) => translate(locale, key, variables),
  }), [direction, locale]);
  return <LocalizationContext.Provider value={value}>{children}</LocalizationContext.Provider>;
}

export const useLocalization = (): LocalizationContextValue => {
  const context = useContext(LocalizationContext);
  if (!context) throw new Error("useLocalization must be used inside LocalizationProvider");
  return context;
};
