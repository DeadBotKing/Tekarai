// ذخیره‌ی موجودیت‌های موج ۲ در مرورگر — کنتورها، تأمین‌کننده‌ها، تاریخچه قیمت،
// متا اطلاعات نسخه‌ی اسناد و رزروهای قطعات.
import type {
  DocumentMeta,
  MeterReading,
  PartReservation,
  PriceHistoryEntry,
  Supplier,
} from "./wave2";

const KEYS = {
  meters: "tekarai.cmms.meters.v1",
  suppliers: "tekarai.cmms.suppliers.v1",
  prices: "tekarai.cmms.price-history.v1",
  docMeta: "tekarai.cmms.doc-meta.v1",
  reservations: "tekarai.cmms.reservations.v1",
} as const;

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
    // مرورگر خصوصی یا پر را رها می‌کنیم — state فعلی صفحه جریان می‌یابد.
  }
};

export const newId = (prefix: string): string =>
  `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e5).toString(36)}`;

/* --- کنتورها --- */
const SEED_METERS: MeterReading[] = [
  { id: "m1", deviceId: "dev-1", kind: "hours", value: 420, at: "2026-09-20T08:00:00Z", note: "داده‌ی نمایشی" },
  { id: "m2", deviceId: "dev-1", kind: "temperature", value: 71, at: "2026-09-20T08:00:00Z", note: "" },
  { id: "m3", deviceId: "dev-1", kind: "vibration", value: 4.2, at: "2026-09-20T08:00:00Z", note: "" },
];

export const listMeterReadings = (deviceId = ""): MeterReading[] => {
  const all = read<MeterReading[]>(KEYS.meters, SEED_METERS);
  return deviceId ? all.filter((reading) => reading.deviceId === deviceId) : all;
};

export const addMeterReading = (reading: MeterReading): void => {
  write(KEYS.meters, [...read<MeterReading[]>(KEYS.meters, SEED_METERS), reading]);
};

/* --- تأمین‌کننده‌ها --- */
const SEED_SUPPLIERS: Supplier[] = [
  { id: "sup-1", name: "قطعه‌باران", phone: "021-33445566", email: "" },
  { id: "sup-2", name: "تجهیزات صنعت", phone: "", email: "sales@tejarat.example" },
];

export const listSuppliers = (): Supplier[] => read<Supplier[]>(KEYS.suppliers, SEED_SUPPLIERS);

export const saveSupplier = (supplier: Supplier): void => {
  const others = read<Supplier[]>(KEYS.suppliers, SEED_SUPPLIERS).filter((item) => item.id !== supplier.id);
  write(KEYS.suppliers, [...others, supplier]);
};

/* --- تاریخچه قیمت --- */
export const listPriceHistory = (partCode = ""): PriceHistoryEntry[] => {
  const all = read<PriceHistoryEntry[]>(KEYS.prices, []);
  return partCode ? all.filter((entry) => entry.partCode === partCode) : all;
};

export const addPriceHistory = (entry: PriceHistoryEntry): void => {
  write(KEYS.prices, [entry, ...read<PriceHistoryEntry[]>(KEYS.prices, [])]);
};

/* --- متا نسخه‌ی اسناد --- */
export const getDocumentMeta = (documentId: string): DocumentMeta | undefined =>
  read<DocumentMeta[]>(KEYS.docMeta, []).find((meta) => meta.documentId === documentId);

export const saveDocumentMeta = (meta: DocumentMeta): void => {
  const others = read<DocumentMeta[]>(KEYS.docMeta, []).filter((item) => item.documentId !== meta.documentId);
  write(KEYS.docMeta, [...others, meta]);
};

export const listDocumentMeta = (): DocumentMeta[] => read<DocumentMeta[]>(KEYS.docMeta, []);

/* --- رزروها --- */
const SEED_RESERVATIONS: PartReservation[] = [];

export const listReservations = (): PartReservation[] => read<PartReservation[]>(KEYS.reservations, SEED_RESERVATIONS);

export const saveReservation = (reservation: PartReservation): void => {
  const others = read<PartReservation[]>(KEYS.reservations, SEED_RESERVATIONS).filter((item) => item.id !== reservation.id);
  write(KEYS.reservations, [...others, reservation]);
};

export const closeReservation = (id: string, status: "consumed" | "released"): void => {
  const all = read<PartReservation[]>(KEYS.reservations, SEED_RESERVATIONS).map((item) =>
    item.id === id ? { ...item, status } : item,
  );
  write(KEYS.reservations, all);
};

/* --- تنظیمات PM مصرفی بر حسب ساعت (برای هر دستگاه) --- */
export interface MeterConfigEntry {
  deviceId: string;
  /** مقدار کنتور (ساعت) هنگام آخرین PM انجام‌شده */
  lastPmHoursAt: number;
  /** بازه‌ی PM بر اساس ساعت‌کار */
  intervalHours: number;
}

const METER_CONFIG_KEY = "tekarai.cmms.meter-config.v1";

export const getMeterConfig = (deviceId: string): MeterConfigEntry =>
  read<MeterConfigEntry[]>(METER_CONFIG_KEY, []).find((entry) => entry.deviceId === deviceId) ?? {
    deviceId,
    lastPmHoursAt: 0,
    intervalHours: 500,
  };

export const saveMeterConfig = (entry: MeterConfigEntry): void => {
  const others = read<MeterConfigEntry[]>(METER_CONFIG_KEY, []).filter((item) => item.deviceId !== entry.deviceId);
  write(METER_CONFIG_KEY, [...others, entry]);
};

/* --- پیوند قطعه ↔ تأمین‌کننده و فیلد «تامین‌کننده» روی کارت --- */
const PART_SUPPLIER_KEY = "tekarai.cmms.part-supplier.v1";

export const getPartSupplierMap = (): Record<string, string> =>
  read<Record<string, string>>(PART_SUPPLIER_KEY, {});

export const setPartSupplier = (partCode: string, supplierId: string): void => {
  write(PART_SUPPLIER_KEY, { ...getPartSupplierMap(), [partCode]: supplierId });
};
