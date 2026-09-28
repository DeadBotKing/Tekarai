// موج ۱ CMMM حرفه‌ای — منطق خالص و قابل‌تست (هم دمو هم واقعی):
// ۱) درخت مکان/تجهیزات  ۲) کد و علت خرابی (RCA)  ۳) نقطه‌ی سفارش قطعات
// ۴) SLA و عقب‌ماندگی  ۵) چک‌لیست بازرسی → دستور کار خودکار

/* ------------------------------------------------------------------ */
/* ساختارهای ساخت‌‌یافته‌ی سبک بدون وابستگی سفت به مدل‌ها                */
/* ------------------------------------------------------------------ */

export interface DeviceLike {
  id: string;
  code: string;
  name: string;
  location?: string;
  department?: string;
  locationPath?: string;
}

export interface WorkOrderLike {
  id: string;
  deviceId: string;
  status: string;
  slaDueAt?: string;
}

/* ------------------------------------------------------------------ */
/* ۱) سلسله‌مراتب مکان (سایت/سالن/خط به تفکیک locationPath یا واحد)     */
/* ------------------------------------------------------------------ */

export interface DeviceTreeNode {
  key: string;
  label: string;
  devices: DeviceLike[];
  openWorkOrders: number;
  children: DeviceTreeNode[];
}

const TERMINAL_STATUSES = new Set(["completed", "cancelled", "closed"]);

export const isOpenStatus = (status: string): boolean => !TERMINAL_STATUSES.has(status);

const pathSegments = (device: DeviceLike): string[] => {
  const raw = device.locationPath?.trim() || device.location?.trim() || device.department?.trim() || "سایر";
  const segments = raw.split(/[\/›»|]/).map((part) => part.trim()).filter(Boolean);
  return segments.length ? segments : ["سایر"];
};

const insertNode = (tree: DeviceTreeNode[], segments: string[], device: DeviceLike): void => {
  const head = segments[0];
  let node = tree.find((item) => item.label === head);
  if (!node) {
    node = { key: head, label: head, devices: [], openWorkOrders: 0, children: [] };
    tree.push(node);
  }
  if (segments.length === 1) {
    node.devices.push(device);
    return;
  }
  insertNode(node.children, segments.slice(1), device);
};

const tallyOpen = (node: DeviceTreeNode, openDevices: Set<string>): void => {
  node.openWorkOrders =
    node.devices.filter((device) => openDevices.has(device.id)).length +
    node.children.reduce((sum, child) => {
      tallyOpen(child, openDevices);
      return sum + child.openWorkOrders;
    }, 0);
};

export const buildDeviceTree = (
  devices: DeviceLike[],
  openWorkOrders: WorkOrderLike[],
): DeviceTreeNode[] => {
  const tree: DeviceTreeNode[] = [];
  for (const device of devices) insertNode(tree, pathSegments(device), device);
  const openDevices = new Set(openWorkOrders.filter((order) => isOpenStatus(order.status)).map((order) => order.deviceId));
  for (const node of tree) tallyOpen(node, openDevices);
  return tree;
};

/* ------------------------------------------------------------------ */
/* ۲) کد و علت خرابی — درخت تعریف‌پذیر (RCA)                            */
/* ------------------------------------------------------------------ */

export interface FailureReason {
  code: string;
  title: string;
}

export interface FailureCategory {
  code: string;
  title: string;
  reasons: FailureReason[];
}

export const FAILURE_TREE: FailureCategory[] = [
  { code: "ele", title: "برق و الکترونیک", reasons: [
    { code: "ele-power", title: "نوسان یا قطع برق" },
    { code: "ele-motor", title: "سوختن سیم‌پیچ موتور" },
    { code: "ele-panel", title: "خرابی تابلو و کنتاکتور" },
    { code: "ele-sensor", title: "خطای سنسور یا رله" },
  ] },
  { code: "mec", title: "مکانیکی", reasons: [
    { code: "mec-bearing", title: "خرابی بلبرینگ یا بوش" },
    { code: "mec-shaft", title: "عدم تراز یا آسیب شفت" },
    { code: "mec-wear", title: "فرسایش قطعات متحرک" },
    { code: "mec-lube", title: "کمبود روغنکاری" },
  ] },
  { code: "ins", title: "ابزاردقیق و کنترل", reasons: [
    { code: "ins-plc", title: "خطای PLC یا کنترلر" },
    { code: "ins-cal", title: "نیاز به کالیبراسیون" },
    { code: "ins-valve", title: "خرابی شیر پنوماتیک یا کلاپ" },
  ] },
  { code: "opr", title: "بهره‌برداری", reasons: [
    { code: "opr-misuse", title: "خطای اپراتور" },
    { code: "opr-overload", title: "بار اضافه یا تغییر رژیم تولید" },
  ] },
  { code: "env", title: "محیط و استهلاک طبیعی", reasons: [
    { code: "env-heat", title: "گرمای محیط یا بیش‌ازحد" },
    { code: "env-dust", title: "گرد و رطوبت" },
    { code: "env-age", title: "پایان عمر مفید قطعه" },
  ] },
];

export const findFailureLabel = (categoryCode: string, reasonCode: string): string => {
  const category = FAILURE_TREE.find((item) => item.code === categoryCode);
  const reason = category?.reasons.find((item) => item.code === reasonCode);
  return category && reason ? `${category.title} / ${reason.title}` : "";
};

/**
 * پیشوند ساخت‌یافته روی یادداشت تأیید — بدون تغییر بک‌اند، در تاریخچه‌ی
 * درخواست ثبت می‌شود و گزارش RCA روی آن سوار خواهد شد.
 */
export const formatFailureNote = (categoryCode: string, reasonCode: string, note: string): string => {
  const tag = findFailureLabel(categoryCode, reasonCode);
  const prefix = tag ? `کد/علت خرابی: [${tag}]` : "";
  return [prefix, note.trim()].filter(Boolean).join("\n");
};

/* ------------------------------------------------------------------ */
/* ۳) نقطه‌ی سفارش قطعات                                                */
/* ------------------------------------------------------------------ */

export interface PartLike {
  code: string;
  name: string;
  unit: string;
  quantityOnHand: number;
  minimumStock: number;
}

export interface ReorderSuggestion {
  partCode: string;
  partName: string;
  unit: string;
  quantityOnHand: number;
  minimumStock: number;
  /** مقدار پیشنهادی سفارش = دو برابر حداقل منها موجودی */
  suggestedOrder: number;
}

export const buildReorderSuggestions = (parts: PartLike[]): ReorderSuggestion[] =>
  parts
    .filter((part) => part.minimumStock > 0 && part.quantityOnHand < part.minimumStock)
    .map((part) => ({
      partCode: part.code,
      partName: part.name,
      unit: part.unit,
      quantityOnHand: part.quantityOnHand,
      minimumStock: part.minimumStock,
      suggestedOrder: part.minimumStock * 2 - part.quantityOnHand,
    }))
    .sort(
      (a, b) =>
        b.minimumStock - b.quantityOnHand - (a.minimumStock - a.quantityOnHand) ||
        a.partCode.localeCompare(b.partCode),
    );

/* ------------------------------------------------------------------ */
/* ۴) SLA و عقب‌ماندگی                                                  */
/* ------------------------------------------------------------------ */

export const isSlaBreached = (order: WorkOrderLike, now: Date = new Date()): boolean => {
  if (!order.slaDueAt || !isOpenStatus(order.status)) return false;
  const due = new Date(order.slaDueAt).getTime();
  return Number.isFinite(due) && due < now.getTime();
};

export const slaBreachedOrders = <T extends WorkOrderLike>(orders: T[], now: Date = new Date()): T[] =>
  orders.filter((order) => isSlaBreached(order, now));

/* ------------------------------------------------------------------ */
/* ۵) چک‌لیست بازرسی → دستور کار خودکار                                 */
/* ------------------------------------------------------------------ */

export interface InspectionTemplateItem {
  id: string;
  text: string;
}

export interface InspectionTemplate {
  id: string;
  title: string;
  /** کد دستگاه؛ خالی یعنی عمومی برای هر دستگاه */
  deviceCode: string;
  items: InspectionTemplateItem[];
}

export interface InspectionRunItem {
  itemId: string;
  ok: boolean;
}

export const failedTemplateItems = (
  template: InspectionTemplate,
  runItems: InspectionRunItem[],
): InspectionTemplateItem[] =>
  template.items.filter((item) => runItems.find((run) => run.itemId === item.id)?.ok === false);

export interface InspectionWorkOrderDraft {
  deviceId: string;
  title: string;
  description: string;
  priority: "high" | "normal";
}

export const buildInspectionWorkOrderDraft = (
  device: DeviceLike,
  template: InspectionTemplate,
  failed: InspectionTemplateItem[],
): InspectionWorkOrderDraft => ({
  deviceId: device.id,
  title: `چک‌لیست بازرسی — ${template.title}`,
  description: [
    `بازرسی دوره‌ای «${template.title}» روی دستگاه ${device.code} انجام شد و ${failed.length} مورد نامقبول داشت:`,
    ...failed.map((item) => `• ${item.text}`),
  ].join("\n"),
  priority: failed.length >= 3 ? "high" : "normal",
});

/* --------------------------- سابقه‌ی اجرای بازرسی (تیمی) --------------------------- */

export interface InspectionRecord {
  id: string;
  templateId: string;
  templateTitle: string;
  deviceId: string;
  deviceCode: string;
  at: string; // ISO
  performedByName: string;
  passedChecks: string[];
  failedChecks: string[];
}

/** تشکیل رکورد از روی قالب + وضعیت تیک‌ها — فانکشن خالص و قابل آزمون. */
export const buildInspectionRecord = (
  id: string,
  template: InspectionTemplate,
  runItems: InspectionRunItem[],
  deviceId: string,
  deviceCode: string,
  performedByName: string,
  at: string = new Date().toISOString(),
): InspectionRecord => {
  const failed = failedTemplateItems(template, runItems).map((item) => item.text);
  const failedSet = new Set(failed);
  return {
    id,
    templateId: template.id,
    templateTitle: template.title,
    deviceId,
    deviceCode,
    at,
    performedByName,
    failedChecks: failed,
    passedChecks: template.items
      .map((item) => item.text)
      .filter((text) => !failedSet.has(text)),
  };
};

