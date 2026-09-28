// سابقه‌ی اجراهای چک‌لیست — هم‌گام با بک‌اند (تیمی) + کش محلی مرورگر.
import type { InspectionRecord } from "./wave1";
import { pushInspectionRecord, pullInspectionRecords } from "./teamSyncStore";

const KEY = "tekarai.cmms.inspection-records.v1";

const readLocal = (): InspectionRecord[] => {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as InspectionRecord[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeLocal = (records: InspectionRecord[]): void => {
  try {
    localStorage.setItem(KEY, JSON.stringify(records));
  } catch {
    /* حافظه‌ی پر — مثل همیشه ادامه‌ی state فعلی */
  }
};

let serverRecords: InspectionRecord[] | null = null;

export const listInspectionRecords = (): InspectionRecord[] => serverRecords ?? readLocal();

export const newRecordId = (): string =>
  `rec-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e4).toString(36)}`;

export const saveInspectionRecord = (record: InspectionRecord): void => {
  const others = listInspectionRecords().filter((item) => item.id !== record.id);
  if (serverRecords !== null) serverRecords = [...others, record];
  writeLocal([...others, record]);
  void pushInspectionRecord(record).catch(() => undefined);
};

/** کشیدن سابقه‌ی تیمی از سرور و بازنویسی کش محلی. */
export const syncInspectionRecordsFromServer = async (): Promise<boolean> => {
  try {
    const records = await pullInspectionRecords();
    serverRecords = records;
    writeLocal(records);
    return true;
  } catch {
    return false;
  }
};
