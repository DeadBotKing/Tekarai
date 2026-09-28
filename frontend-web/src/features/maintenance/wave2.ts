// موج ۲ CMMS حرفه‌ای — منطق خالص و قابل‌تست:
// ۱) خوانش کنتور + PM مصرفی  ۲) تأمین‌کننده/پیش‌فاکتور/تاریخچه قیمت
// ۳) نسخه‌بندی اسناد + پیوند به دستگاه  ۴) رزرو قطعات روی درخواست کار

/* ----------------------------------- */
/* ۱) کنتورها و PM مصرفی                */
/* ----------------------------------- */

export type MeterKind = "hours" | "temperature" | "vibration";

export interface MeterKindMeta {
  kind: MeterKind;
  title: string;
  unit: string;
  /** آستانه‌ی هشدار (برای دما/لرزش) */
  alarmAt?: number;
}

export const METER_KINDS: MeterKindMeta[] = [
  { kind: "hours", title: "ساعت‌کار", unit: "ساعت" },
  { kind: "temperature", title: "دمای کارکرد", unit: "°C", alarmAt: 85 },
  { kind: "vibration", title: "لرزش", unit: "mm/s", alarmAt: 7.1 },
];

export interface MeterReading {
  id: string;
  deviceId: string;
  kind: MeterKind;
  value: number;
  at: string; // ISO
  note: string;
}

export const meterKindMeta = (kind: MeterKind): MeterKindMeta =>
  METER_KINDS.find((meta) => meta.kind === kind)!;

export const latestReading = (
  readings: MeterReading[],
  deviceId: string,
  kind: MeterKind,
): MeterReading | undefined =>
  readings
    .filter((reading) => reading.deviceId === deviceId && reading.kind === kind)
    .sort((a, b) => b.at.localeCompare(a.at))[0];

export const isMeterAlarmed = (reading: MeterReading | undefined): boolean => {
  if (!reading) return false;
  const alarm = meterKindMeta(reading.kind).alarmAt;
  return alarm != null && reading.value >= alarm;
};

/**
 * PM مصرفی: از آخرین ساعتی که PM انجام شده به بعد، اگر مصرف ≥ بازه‌ی ساعتی
 * دستگاه باشد، PM لازم است. `lastPmHoursAt` = مقدار کنتور هنگام آخرین PM.
 */
export const usagePmDue = (
  currentHours: number | undefined,
  lastPmHoursAt: number,
  intervalHours: number,
): boolean =>
  currentHours != null && intervalHours > 0 && currentHours - lastPmHoursAt >= intervalHours;

/** پیش‌بینی: با نرخ مصرف فعلی، چند ساعت دیگر به PM می‌رسد (منفی = دیر). */
export const usagePmRemaining = (
  currentHours: number | undefined,
  lastPmHoursAt: number,
  intervalHours: number,
): number | undefined =>
  currentHours == null ? undefined : intervalHours - (currentHours - lastPmHoursAt);

/* ----------------------------------- */
/* ۲) تأمین‌کننده, تاریخچه قیمت, پیش‌فاکتور  */
/* ----------------------------------- */

export interface Supplier {
  id: string;
  name: string;
  phone: string;
  email: string;
}

export interface PriceHistoryEntry {
  partCode: string;
  oldPrice: number;
  newPrice: number;
  at: string; // ISO
}

/** تغییر قیمت واقعی یا نه (صفر → صفر خیر). */
export const priceChanged = (oldPrice: number, newPrice: number): boolean =>
  Number(newPrice) !== Number(oldPrice);

export interface ProformaLine {
  partCode: string;
  partName: string;
  unit: string;
  quantity: number;
  unitCost: number;
  lineTotal: number;
}

export interface Proforma {
  supplierName: string;
  lines: ProformaLine[];
  grandTotal: number;
}

export interface ReorderLike {
  partCode: string;
  partName: string;
  unit: string;
  suggestedOrder: number;
  unitCost: number;
  supplierId?: string;
}

/** خطوط پیش‌فاکتور به تفکیک تأمین‌کننده؛ ترتیب‌ورودی حفظ می‌شود. */
export const buildProformas = (
  lines: ReorderLike[],
  suppliersById: Record<string, Supplier>,
): Proforma[] => {
  const groups = new Map<string, ProformaLine[]>();
  for (const line of lines) {
    const supplier = line.supplierId ? suppliersById[line.supplierId]?.name ?? "بدون تأمین‌کننده" : "بدون تأمین‌کننده";
    const bucket = groups.get(supplier) ?? [];
    bucket.push({
      partCode: line.partCode,
      partName: line.partName,
      unit: line.unit,
      quantity: line.suggestedOrder,
      unitCost: line.unitCost,
      lineTotal: line.suggestedOrder * line.unitCost,
    });
    groups.set(supplier, bucket);
  }
  return [...groups.entries()].map(([supplierName, items]) => ({
    supplierName,
    lines: items,
    grandTotal: items.reduce((sum, item) => sum + item.lineTotal, 0),
  }));
};

/* ----------------------------------- */
/* ۳) نسخه‌بندی اسناد                    */
/* ----------------------------------- */

export interface DocumentVersionEntry {
  version: number;
  at: string; // ISO
  sizeLabel: string;
  note: string;
}

export interface DocumentMeta {
  documentId: string;
  currentVersion: number;
  deviceCode: string; // خالی = بدون پیوند
  history: DocumentVersionEntry[];
}

export const nextDocumentVersion = (meta: DocumentMeta | undefined, entry: Omit<DocumentVersionEntry, "version">): DocumentMeta =>
  !meta
    ? { documentId: "", currentVersion: 1, deviceCode: "", history: [{ ...entry, version: 1 }] }
    : {
        ...meta,
        currentVersion: meta.currentVersion + 1,
        history: [...meta.history, { ...entry, version: meta.currentVersion + 1 }],
      };

/* ----------------------------------- */
/* ۴) رزرو قطعات                         */
/* ----------------------------------- */

export interface PartReservation {
  id: string;
  orderId: string;
  partCode: string;
  quantity: number;
  /** active = رزرو فعال، consumed = مصرف شد، released = آزاد شد */
  status: "active" | "consumed" | "released";
  at: string; // ISO
}

export const activeReservedForPart = (reservations: PartReservation[], partCode: string): number =>
  reservations
    .filter((reservation) => reservation.partCode === partCode && reservation.status === "active")
    .reduce((sum, reservation) => sum + reservation.quantity, 0);

export const availableStock = (quantityOnHand: number, reserved: number): number =>
  Math.max(0, quantityOnHand - reserved);

export const reservationsForOrder = (reservations: PartReservation[], orderId: string): PartReservation[] =>
  reservations.filter((reservation) => reservation.orderId === orderId && reservation.status === "active");
