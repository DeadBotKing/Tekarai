/** QR روی تجهیز — ساخت نشانی نمایه و تجزیه‌ی خروجی اسکنر. */

/** مسیر داخلی نمایه‌ی دستگاه (همان کاری که مسیریاب انجام می‌دهد). */
export const deviceProfilePath = (deviceId: string): string =>
  `/app/maintenance/devices/${deviceId}/profile`;

/**
 * محتوای کد QR: نشانی مطلق تا گوشیِ اسکن‌کننده بتواند مستقیم باز کند؛
 * در محیط بدون مرورگر (تست/SSR) همان مسیر نسبی برمی‌گردد.
 */
export const deviceQrPayload = (deviceId: string): string => {
  const path = deviceProfilePath(deviceId);
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${path}`;
  }
  return path;
};

const DEVICE_PROFILE_RE =
  /\/(?:app\/)?maintenance\/devices\/([0-9A-Za-z-]{4,})(?:\/profile)?(?:[/?#]|$)/;
const RAW_ID_RE = /^[0-9a-fA-F-]{8,}$/;

/**
 * متن خروجی اسکنر یا ورودی دستی کاربر → شناسه‌ی دستگاه.
 * نشانی مطلق، مسیر نسبی یا شناسه‌ی خام همه پذیرفته می‌شوند؛ در غیر این صورت null.
 */
export function parseDeviceScan(text: string): string | null {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return null;
  const match = DEVICE_PROFILE_RE.exec(trimmed);
  if (match) return match[1];
  if (RAW_ID_RE.test(trimmed)) return trimmed.toLowerCase();
  return null;
}
