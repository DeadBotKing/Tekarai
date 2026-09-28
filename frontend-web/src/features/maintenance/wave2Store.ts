// ذخیره‌ی رزروهای قطعات در مرورگر — بخش نگه‌داشته‌شده‌ی موج ۲.
import type { PartReservation } from "./wave2";

const RESERVATIONS_KEY = "tekarai.cmms.reservations.v1";

const read = <T>(key: string, seed: T): T => {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return seed;
    return JSON.parse(raw) as T;
  } catch {
    return seed;
  }
};

const write = <T>(key: string, value: T): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // مرورگر خصوصی یا پر — state فعلی صفحه جریان می‌یابد.
  }
};

export const newId = (prefix: string): string =>
  `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e5).toString(36)}`;

export const listReservations = (): PartReservation[] =>
  read<PartReservation[]>(RESERVATIONS_KEY, []);

export const saveReservation = (reservation: PartReservation): void => {
  const others = listReservations().filter((item) => item.id !== reservation.id);
  write(RESERVATIONS_KEY, [...others, reservation]);
};

export const closeReservation = (id: string, status: "consumed" | "released"): void => {
  write(
    RESERVATIONS_KEY,
    listReservations().map((item) => (item.id === id ? { ...item, status } : item)),
  );
};
