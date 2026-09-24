import { describe, expect, it } from "vitest";
import {
  formatJalali,
  gregorianToJalali,
  isJalaliLeapYear,
  isoToJalaliParts,
  jalaliMonthLength,
  jalaliPartsToIso,
  jalaliToGregorian,
  toPersianDigits,
} from "../core/localization/jalali";

describe("jalali conversion", () => {
  it("converts known Gregorian dates to Jalali", () => {
    expect(gregorianToJalali(2026, 9, 24)).toEqual([1405, 7, 2]);
    expect(gregorianToJalali(2024, 3, 20)).toEqual([1403, 1, 1]); // Nowruz 1403
    expect(gregorianToJalali(1979, 2, 11)).toEqual([1357, 11, 22]);
  });

  it("round-trips Jalali -> Gregorian -> Jalali", () => {
    const samples: [number, number, number][] = [
      [1403, 1, 1],
      [1405, 7, 2],
      [1357, 11, 22],
      [1399, 12, 30], // 1399 is a leap year
    ];
    for (const [jy, jm, jd] of samples) {
      const [gy, gm, gd] = jalaliToGregorian(jy, jm, jd);
      expect(gregorianToJalali(gy, gm, gd)).toEqual([jy, jm, jd]);
    }
  });

  it("computes month lengths and leap years", () => {
    expect(jalaliMonthLength(1403, 1)).toBe(31);
    expect(jalaliMonthLength(1403, 7)).toBe(30);
    expect(isJalaliLeapYear(1399)).toBe(true);
    expect(jalaliMonthLength(1399, 12)).toBe(30);
    expect(isJalaliLeapYear(1400)).toBe(false);
    expect(jalaliMonthLength(1400, 12)).toBe(29);
  });

  it("converts ISO <-> Jalali parts", () => {
    expect(isoToJalaliParts("2024-03-20")).toEqual([1403, 1, 1]);
    expect(jalaliPartsToIso(1403, 1, 1)).toBe("2024-03-20");
    expect(isoToJalaliParts("not-a-date")).toBeNull();
  });

  it("formats Jalali dates in Persian", () => {
    expect(formatJalali("2024-03-20", { style: "long" })).toBe("۱ فروردین ۱۴۰۳");
    expect(formatJalali("2024-03-20", { style: "short" })).toBe("۱۴۰۳/۰۱/۰۱");
    expect(formatJalali("2024-03-20", { style: "short", persianDigits: false })).toBe("1403/01/01");
    expect(formatJalali("")).toBe("");
  });

  it("converts digits to Persian", () => {
    expect(toPersianDigits("1403/07/02")).toBe("۱۴۰۳/۰۷/۰۲");
  });
});
