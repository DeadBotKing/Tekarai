// هم‌گام‌سازی تیمی با بک‌اند — رزرو قطعات + قالب‌های چک‌لیست بازرسی.
// الگو: «آفلاین-دوستانه» — بدون نشست، فقط localStorage؛ با نشست، API بک‌اند
// منبع حقیقت است و localStorage یک کش ترمیم‌پذیر می‌ماند.
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { sessionStore } from "../../core/auth/sessionStore";
import type { InspectionRecord, InspectionTemplate } from "./wave1";
import type { PartReservation } from "./wave2";

const TENANT_KEY = "tekarai.gui.tenant.v1";

interface Envelope<T> {
  success?: boolean;
  data?: T;
}

/** آیا نشست فعالی برای هم‌گام‌سازی سرور وجود دارد؟ */
export const hasSyncSession = (): boolean => Boolean(sessionStore.get());

const apiFetch = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const session = sessionStore.get();
  if (!session) throw new Error("no-session");
  const tenantId = (() => {
    try {
      return localStorage.getItem(TENANT_KEY) ?? "";
    } catch {
      return "";
    }
  })();
  const response = await fetch(
    `${runtimeConfig.apiBaseUrl}/api/${runtimeConfig.apiVersion}/${path}`,
    {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.accessToken}`,
        ...(tenantId ? { "X-Tenant-ID": tenantId } : {}),
        ...(init?.headers ?? {}),
      },
    },
  );
  if (!response.ok) throw new Error(`http-${response.status}`);
  const payload = (await response.json()) as Envelope<T>;
  return (payload.data ?? payload) as T;
};

// ---------------------------------------------------------------- reservations

/** نگاشت DTO بک‌اند به مدل فرانت */
const toReservation = (dto: {
  id: string;
  orderId: string;
  partCode: string;
  quantity: string | number;
  status: string;
  at: string;
}): PartReservation => ({
  id: dto.id,
  orderId: dto.orderId,
  partCode: dto.partCode,
  quantity: Number(dto.quantity),
  status: dto.status as PartReservation["status"],
  at: dto.at,
});

export const pullReservations = (): Promise<PartReservation[]> =>
  apiFetch<Array<Parameters<typeof toReservation>[0]>>(
    "maintenance/team/reservations",
  ).then((items) => items.map(toReservation));

export const pushReservation = (reservation: PartReservation): Promise<void> =>
  apiFetch("maintenance/team/reservations", {
    method: "POST",
    body: JSON.stringify({
      id: reservation.id,
      orderId: reservation.orderId,
      partCode: reservation.partCode,
      quantity: String(reservation.quantity),
      status: reservation.status,
    }),
  }).then(() => undefined);

export const pushCloseReservation = (
  id: string,
  status: "consumed" | "released",
): Promise<void> =>
  apiFetch(`maintenance/team/reservations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  }).then(() => undefined);

// ----------------------------------------------------------------- inspections

/** نگاشت DTO بک‌اند به قالب فرانت */
const toTemplate = (dto: {
  id: string;
  name: string;
  checks: string[];
  description: string;
  deviceCode: string;
}): InspectionTemplate => ({
  id: dto.id,
  title: dto.name,
  deviceCode: dto.deviceCode,
  items: (dto.checks ?? []).map((text, index) => ({ id: `i-${index + 1}`, text })),
});

export const pullInspectionTemplates = (): Promise<InspectionTemplate[]> =>
  apiFetch<Array<Parameters<typeof toTemplate>[0]>>(
    "maintenance/team/inspection-templates",
  ).then((items) => items.map(toTemplate));

export const pushInspectionTemplate = (template: InspectionTemplate): Promise<void> =>
  apiFetch("maintenance/team/inspection-templates", {
    method: "POST",
    body: JSON.stringify({
      id: template.id,
      name: template.title,
      description: "",
      deviceCode: template.deviceCode,
      checks: template.items.map((item) => item.text),
    }),
  }).then(() => undefined);

export const pushDeleteInspectionTemplate = (id: string): Promise<void> =>
  apiFetch(`maintenance/team/inspection-templates/${id}`, { method: "DELETE" }).then(
    () => undefined,
  );

// ------------------------------------------------------------- inspection records

/** نگاشت DTO بک‌اند به رکورد فرانت */
const toRecord = (dto: {
  id: string;
  templateId: string;
  deviceId: string;
  passedChecks: string[];
  failedChecks: string[];
  performedByName: string;
  at: string;
}): InspectionRecord => ({
  id: dto.id,
  templateId: dto.templateId,
  deviceId: dto.deviceId,
  deviceCode: "", // کد در گیرنده از روی فهرست دستگاه‌ها بدست می‌آید
  templateTitle: "",
  performedByName: dto.performedByName,
  at: dto.at,
  passedChecks: dto.passedChecks ?? [],
  failedChecks: dto.failedChecks ?? [],
});

export const pullInspectionRecords = (): Promise<InspectionRecord[]> =>
  apiFetch<Array<Parameters<typeof toRecord>[0]>>(
    "maintenance/team/inspection-records",
  ).then((items) => items.map(toRecord));

export const pushInspectionRecord = (record: InspectionRecord): Promise<void> =>
  apiFetch("maintenance/team/inspection-records", {
    method: "POST",
    body: JSON.stringify({
      id: record.id,
      templateId: record.templateId,
      workOrderId: "",
      deviceId: record.deviceId,
      passedChecks: record.passedChecks,
      failedChecks: record.failedChecks,
      performedByName: record.performedByName,
    }),
  }).then(() => undefined);
