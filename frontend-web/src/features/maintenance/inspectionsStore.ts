// ذخیره‌ی قالب‌های چک‌لیست بازرسی — هم‌گام با بک‌اند (تیمی) + fallback محلی مرورگر.
import type { InspectionTemplate } from "./wave1";
import {
  pushDeleteInspectionTemplate,
  pushInspectionTemplate,
  pullInspectionTemplates,
} from "./teamSyncStore";

const KEY = "tekarai.cmms.inspections.v1";

const SEED: InspectionTemplate[] = [
  {
    id: "insp-seed-1",
    title: "بازرسی هفتگی تجهیزات دوار",
    deviceCode: "",
    items: [
      { id: "i1", text: "صدای غیرعادی بلبرینگ بررسی شد" },
      { id: "i2", text: "سطح روغن در محدوده‌ی نرمال است" },
      { id: "i3", text: "داغی بیش‌ازحد بدنه وجود ندارد" },
      { id: "i4", text: "اتصالات و پیچ‌های کفشک سفت‌اند" },
    ],
  },
];

const readLocal = (): InspectionTemplate[] => {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return SEED;
    const parsed = JSON.parse(raw) as InspectionTemplate[];
    return Array.isArray(parsed) ? parsed : SEED;
  } catch {
    return SEED;
  }
};

const writeLocal = (templates: InspectionTemplate[]): void => {
  try {
    localStorage.setItem(KEY, JSON.stringify(templates));
  } catch {
    // مرورگر خصوصی/حافظه‌ی پر — صفحه با state فعلی کارش ادامه دارد.
  }
};

let serverTemplates: InspectionTemplate[] | null = null;

export const listInspectionTemplates = (): InspectionTemplate[] => serverTemplates ?? readLocal();

const mirrorAll = (templates: InspectionTemplate[]): void => {
  if (serverTemplates !== null) serverTemplates = templates;
  writeLocal(templates);
};

export const saveInspectionTemplate = (template: InspectionTemplate): void => {
  mirrorAll([
    ...listInspectionTemplates().filter((item) => item.id !== template.id),
    template,
  ]);
  void pushInspectionTemplate(template).catch(() => undefined);
};

export const deleteInspectionTemplate = (id: string): void => {
  mirrorAll(listInspectionTemplates().filter((item) => item.id !== id));
  void pushDeleteInspectionTemplate(id).catch(() => undefined);
};

export const newTemplateId = (): string =>
  `insp-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e4).toString(36)}`;

/** کشیدن همه‌ی قالب‌های تیمی از بک‌اند و بازنویسی کش محلی. */
export const syncInspectionTemplatesFromServer = async (): Promise<boolean> => {
  try {
    const templates = await pullInspectionTemplates();
    serverTemplates = templates;
    writeLocal(templates);
    return true;
  } catch {
    return false;
  }
};
