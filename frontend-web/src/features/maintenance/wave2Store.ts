// ذخیره‌ی رزروهای قطعات — هم‌گام با بک‌اند (تیمی) با fallback داده‌ی محلی مرورگر
// در حالت آفلاین/دمو. کش سرور وقتی پر می‌شود که sync از API موفق بوده باشد.
import type { PartReservation } from "./wave2";
import { pushCloseReservation, pushReservation, pullReservations } from "./teamSyncStore";

const RESERVATIONS_KEY = "tekarai.cmms.reservations.v1";

const readLocal = (): PartReservation[] => {
  try {
    const raw = localStorage.getItem(RESERVATIONS_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as PartReservation[];
  } catch {
    return [];
  }
};

const writeLocal = (value: PartReservation[]): void => {
  try {
    localStorage.setItem(RESERVATIONS_KEY, JSON.stringify(value));
  } catch {
    // مرورگر خصوصی یا پر — state فعلی صفحه جریان می‌یابد.
  }
};

let serverReservations: PartReservation[] | null = null;

/** خواندن سریع برای رندر — سرور اول غالب است، بعد localStorage */
export const listReservations = (): PartReservation[] => serverReservations ?? readLocal();

const mirrorAll = (reservations: PartReservation[]): void => {
  if (serverReservations !== null) serverReservations = reservations;
  writeLocal(reservations);
};

export const newId = (prefix: string): string =>
  `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e5).toString(36)}`;

export const saveReservation = (reservation: PartReservation): void => {
  mirrorAll([...listReservations().filter((item) => item.id !== reservation.id), reservation]);
  // ارسال پس‌زمینه‌ای به بک‌اند — خطا شود فقط محلی می‌ماند (آفلاین مداوم)
  void pushReservation(reservation).catch(() => undefined);
};

export const closeReservation = (id: string, status: "consumed" | "released"): void => {
  mirrorAll(
    listReservations().map((item) => (item.id === id ? { ...item, status } : item)),
  );
  void pushCloseReservation(id, status).catch(() => undefined);
};

/** کشیدن صادقانه از بک‌اند — همه‌ی تیم — و بازنویسی کش محلی. */
export const syncReservationsFromServer = async (): Promise<boolean> => {
  try {
    const reservations = await pullReservations();
    serverReservations = reservations;
    writeLocal(reservations);
    return true;
  } catch {
    return false;
  }
};
