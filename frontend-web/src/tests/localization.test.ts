import { describe, expect, it } from "vitest";
import { translate, translations, localeMeta, type TranslationKey } from "../core/localization/i18n";

describe("localization contract", () => {
  it("has explicit direction metadata", () => {
    expect(localeMeta.en.direction).toBe("ltr");
    expect(localeMeta.fa.direction).toBe("rtl");
    expect(localeMeta.de.direction).toBe("ltr");
  });

  it("falls back to English and interpolates variables", () => {
    expect(translate("fa", "dashboard.title")).toBe("نمای کلی محیط کار");
    expect(translate("de", "dashboard.activeProjects")).toBe("Aktive Projekte");
    expect(translate("en", "app.name")).toBe("Tekarai");
  });

  it("interpolates single-brace placeholders", () => {
    // These shipped broken: the dashboard printed "{critical} مورد بحرانی باز".
    expect(translate("fa", "cmms.dash.openWoHint", { critical: 3 })).toBe("3 مورد بحرانی باز");
    expect(translate("fa", "cmms.costDash.items", { count: 12 })).toBe("12 سطر هزینه");
    expect(translate("fa", "cmms.dash.completionHint", { done: 2, total: 5 })).toBe(
      "2 از 5 درخواست",
    );
  });

  it("interpolates double-brace placeholders", () => {
    expect(translate("fa", "timer.stopped", { hours: "1.5" })).toContain("1.5");
    expect(translate("fa", "timer.stopped", { hours: "1.5" })).not.toContain("{");
  });

  it("leaves an unbound placeholder visible instead of blanking it", () => {
    expect(translate("fa", "cmms.dash.openWoHint")).toBe("{critical} مورد بحرانی باز");
  });

  it("does not re-scan substituted values for placeholders", () => {
    expect(translate("fa", "cmms.timeline.by", { actor: "{count}" })).toBe("توسط {count}");
  });

  it("leaves no placeholder unresolved anywhere in the catalogue", () => {
    // Every placeholder name in every catalogue entry is bound to a probe
    // value; nothing may survive the substitution pass.
    const offenders: string[] = [];
    for (const [locale, table] of Object.entries(translations)) {
      for (const [key, template] of Object.entries(table)) {
        const names = [...String(template).matchAll(/\{\{?(\w+)\}?\}/g)].map((m) => m[1]);
        if (names.length === 0) continue;
        const bound = Object.fromEntries(names.map((name) => [name, "X"]));
        const rendered = translate(locale as never, key as TranslationKey, bound);
        if (/[{}]/.test(rendered)) offenders.push(`${locale}:${key} -> ${rendered}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the English catalogue actually English", () => {
    // 622 of 1542 `en` entries (41%) once held Persian text. Because `fa` is
    // composed as { ...en, ...fa }, the Persian UI resolved them through the
    // English fallback and nothing ever looked wrong in testing -- only an
    // English reader saw it. Those values now live in `fa`; this guard stops
    // the shortcut from being taken again.
    const persian = /[\u0600-\u06FF]/;
    const offenders = Object.entries(translations.en)
      .filter(([, value]) => persian.test(String(value)))
      .map(([key]) => key);
    expect(offenders).toEqual([]);
  });

  it("resolves every English key in Persian without falling back", () => {
    // A key that is absent from `fa` silently renders its English value in a
    // right-to-left UI. Only locale-independent glyphs may be shared.
    // Locale-independent values: an em dash and a sample URL.
    const shared = new Set([
      "cmms.common.none",
      "registry.common.none",
      "registry.scan.placeholder",
    ]);
    const fallingBack = Object.keys(translations.en).filter(
      (key) =>
        !shared.has(key) &&
        translations.fa[key as TranslationKey] === translations.en[key as TranslationKey],
    );
    expect(fallingBack).toEqual([]);
  });

  it("has no English value that is merely its own key", () => {
    // 24 `cmms.wave1.*` entries shipped with the key segment lowercased as
    // the value, so the English inspections screen rendered literal words
    // like "coltitle" and "failnotice" as column headings. A camelCase key
    // whose value is that key lowercased is never a real translation.
    const offenders = Object.entries(translations.en)
      .filter(([key, value]) => {
        const tail = key.split(".").pop() ?? "";
        return /[a-z][A-Z]/.test(tail) && String(value) === tail.toLowerCase();
      })
      .map(([key]) => key);
    expect(offenders).toEqual([]);
  });

  it("keeps placeholder names identical across locales", () => {
    // A translation that renames or drops a placeholder breaks interpolation
    // for that locale alone, which is exactly the class of bug that hides
    // until a non-default language is selected.
    const names = (template: string) =>
      [...template.matchAll(/\{\{?(\w+)\}?\}/g)].map((match) => match[1]).sort();
    const offenders: string[] = [];
    for (const [locale, table] of Object.entries(translations)) {
      if (locale === "en") continue;
      for (const [key, template] of Object.entries(table)) {
        const english = translations.en[key as TranslationKey];
        if (english === undefined) continue;
        const expected = names(String(english)).join(",");
        const actual = names(String(template)).join(",");
        if (expected !== actual) offenders.push(`${locale}:${key} (${expected} vs ${actual})`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
