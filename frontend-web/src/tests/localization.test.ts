import { describe, expect, it } from "vitest";
import { translate, localeMeta } from "../core/localization/i18n";

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
});
