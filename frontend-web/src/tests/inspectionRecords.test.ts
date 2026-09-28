import { beforeEach, describe, expect, it } from "vitest";
import { buildInspectionRecord, type InspectionRunItem, type InspectionTemplate } from "../features/maintenance/wave1";
import {
  listInspectionRecords,
  newRecordId,
  saveInspectionRecord,
  syncInspectionRecordsFromServer,
} from "../features/maintenance/inspectionRecordsStore";

const template: InspectionTemplate = {
  id: "itpl-1",
  title: "بازرسی هفتگی",
  deviceCode: "DEV-01",
  items: [
    { id: "i1", text: "روغن کافی است" },
    { id: "i2", text: "نشتی ندارد" },
    { id: "i3", text: "پیچ‌ها سفت‌اند" },
  ],
};

describe("ساخت رکورد بازرسی (منطق)", () => {
  it("مورد پاس/رد بر اساس تیک‌ها از هم تفکیک می‌شوند", () => {
    const runItems: InspectionRunItem[] = [
      { itemId: "i1", ok: true },
      { itemId: "i2", ok: false },
      { itemId: "i3", ok: true },
    ];
    const record = buildInspectionRecord("rec-1", template, runItems, "dev-uuid-1", "DEV-01", "علی");
    expect(record.failedChecks).toEqual(["نشتی ندارد"]);
    expect(record.passedChecks).toEqual(["روغن کافی است", "پیچ‌ها سفت‌اند"]);
    expect(record.templateTitle).toBe("بازرسی هفتگی");
    expect(record.deviceCode).toBe("DEV-01");
  });

  it("بدون مورد رد → همه پاس", () => {
    const allOk: InspectionRunItem[] = [
      { itemId: "i1", ok: true },
      { itemId: "i2", ok: true },
      { itemId: "i3", ok: true },
    ];
    const record = buildInspectionRecord("rec-2", template, allOk, "dev-uuid-1", "DEV-01", "");
    expect(record.failedChecks).toEqual([]);
    expect(record.passedChecks).toHaveLength(3);
  });
});

describe("ذخیره‌ی سابقه (مرورگر)", () => {
  beforeEach(() => {
    try { localStorage.clear(); } catch { /* بدون مرورگر */ }
  });

  it("ثبت و گردش سابقه", () => {
    const record = buildInspectionRecord(
      newRecordId(), template,
      [{ itemId: "i1", ok: true }, { itemId: "i2", ok: false }, { itemId: "i3", ok: true }],
      "dev-1", "DEV-01", "تیم",
    );
    saveInspectionRecord(record);
    const stored = listInspectionRecords();
    expect(stored).toHaveLength(1);
    expect(stored[0].failedChecks).toEqual(["نشتی ندارد"]);
  });

  it("هم‌گام‌سازی بدون نشست → false و داده‌ی محلی کماکان", async () => {
    saveInspectionRecord(buildInspectionRecord("rec-x", template, [], "dev-1", "DEV-01", ""));
    const ok = await syncInspectionRecordsFromServer();
    expect(ok).toBe(false);
    expect(listInspectionRecords()).toHaveLength(1);
  });
});
