import { describe, expect, it } from "vitest";
import { deviceProfilePath, deviceQrPayload, parseDeviceScan } from "../features/maintenance/deviceQr";

describe("deviceQr — ساخت بار محتوای QR", () => {
  it("مسیر نمایه مطابق مسیریاب است", () => {
    expect(deviceProfilePath("dev-1")).toBe("/app/maintenance/devices/dev-1/profile");
  });
  it("بدون مرورگر مسیر نسبی برمی‌گردد", () => {
    expect(deviceQrPayload("dev-1")).toContain("/maintenance/devices/dev-1/profile");
  });
});

describe("parseDeviceScan — نشانی مطلق، مسیر نسبی یا شناسه‌ی خام", () => {
  it("نشانی مطلق را تجزیه می‌کند", () => {
    expect(
      parseDeviceScan("https://tekarai.example.com/app/maintenance/devices/9f1b2c3d-4e5f/profile?utm=qr"),
    ).toBe("9f1b2c3d-4e5f");
  });
  it("مسیر نسبی را تجزیه می‌کند", () => {
    expect(parseDeviceScan("/app/maintenance/devices/abc-123/profile")).toBe("abc-123");
  });
  it("شناسه‌ی خام پذیرفته می‌شود", () => {
    expect(parseDeviceScan("  9F1B2C3D-4E5F ")).toBe("9f1b2c3d-4e5f");
  });
  it("متن بی‌ربط رد می‌شود", () => {
    expect(parseDeviceScan("سلام دنیا")).toBeNull();
    expect(parseDeviceScan("")).toBeNull();
  });
});
