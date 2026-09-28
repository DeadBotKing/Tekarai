// ذخیره‌ی قالب‌ها وأجراهای چک‌لیست بازرسی — مرورگر-محور، با fallback داده‌ی نمونه.
import type { InspectionTemplate } from "./wave1";

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

const read = (): InspectionTemplate[] => {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return SEED;
    const parsed = JSON.parse(raw) as InspectionTemplate[];
    return Array.isArray(parsed) ? parsed : SEED;
  } catch {
    return SEED;
  }
};

const write = (templates: InspectionTemplate[]): void => {
  try {
    localStorage.setItem(KEY, JSON.stringify(templates));
  } catch {
    // مرورگر خصوصی/حافظه‌ی پر — صفحه با state فعلی کارش ادامه دارد.
  }
};

export const listInspectionTemplates = (): InspectionTemplate[] => read();

export const saveInspectionTemplate = (template: InspectionTemplate): void => {
  const templates = read().filter((item) => item.id !== template.id);
  templates.push(template);
  write(templates);
};

export const deleteInspectionTemplate = (id: string): void => {
  write(read().filter((item) => item.id !== id));
};

export const newTemplateId = (): string =>
  `insp-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e4).toString(36)}`;
