import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";
const THEME_KEY = "tekarai.gui.theme.v1";

// رنگ اصلی (accent) سایت — برای همه‌ی بخش‌ها اعمال و در localStorage نگه داشته می‌شود.
export type Accent = "blue" | "green" | "purple" | "teal" | "rose";
export const ACCENTS: readonly { id: Accent; primary: string }[] = [
  { id: "blue", primary: "#2878ff" },
  { id: "green", primary: "#0c9a64" },
  { id: "purple", primary: "#7446e8" },
  { id: "teal", primary: "#0d9488" },
  { id: "rose", primary: "#db2777" },
];
const ACCENT_KEY = "tekarai.gui.accent.v1";

const initialTheme = (): Theme => {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Follow the accessible light default when storage is unavailable.
  }
  return "light";
};

const initialAccent = (): Accent => {
  try {
    const stored = localStorage.getItem(ACCENT_KEY);
    if (stored && ACCENTS.some((entry) => entry.id === stored)) return stored as Accent;
  } catch {
    // Fall back to the brand blue when storage is unavailable.
  }
  return "blue";
};

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  accent: Accent;
  setAccent: (accent: Accent) => void;
  /** Hex of the current accent — for SVG chart props that cannot read CSS vars. */
  accentHex: string;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [accent, setAccentState] = useState<Accent>(initialAccent);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Current document is still themed.
    }
  }, [theme]);
  useEffect(() => {
    if (accent === "blue") {
      // Blue is the untouched brand default — no attribute keeps base styles intact.
      delete document.documentElement.dataset.accent;
    } else {
      document.documentElement.dataset.accent = accent;
    }
    try {
      localStorage.setItem(ACCENT_KEY, accent);
    } catch {
      // Current document is still accented.
    }
  }, [accent]);
  const value = useMemo(() => ({
    theme,
    setTheme: (nextTheme: Theme) => setThemeState(nextTheme),
    toggleTheme: () => setThemeState((current) => current === "light" ? "dark" : "light"),
    accent,
    setAccent: (nextAccent: Accent) => setAccentState(nextAccent),
    accentHex: ACCENTS.find((entry) => entry.id === accent)?.primary ?? ACCENTS[0].primary,
  }), [theme, accent]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export const useTheme = (): ThemeContextValue => {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
};
