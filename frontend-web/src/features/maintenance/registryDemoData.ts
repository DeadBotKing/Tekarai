import type {
  DeviceAnalytics,
  DeviceAssignment,
  DeviceBomItem,
  DeviceNameplate,
  DeviceProfile,
  DeviceSpecification,
  FleetAnalytics,
  MaintenanceDevice,
  MaintenanceLocation,
  MaintenancePersonnel,
  PartUsageReport,
  PmExecution,
  PmPlan,
  SparePart,
} from "../../shared/types/domain";
import type { RegistryService } from "./registryService";
import { demoDevices } from "./maintenanceDemoData";

/**
 * Offline registry data + an in-memory implementation of {@link RegistryService}.
 *
 * Demo mode is what the UI falls back to when no API is reachable, so the
 * registry has to behave like a real database there too: writes mutate this
 * store and are visible on the next read, exactly like the server version.
 */

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

const nextId = (prefix: string): string =>
  `${prefix}-${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-4)}`;

export const demoLocations: MaintenanceLocation[] = [
  {
    id: "loc-site-1",
    code: "SITE-ESF",
    name: "سایت اصفهان",
    kind: "site",
    parentId: "",
    path: "سایت اصفهان",
    note: "کارخانه اصلی",
    deviceCount: 0,
  },
  {
    id: "loc-bld-1",
    code: "BLD-A",
    name: "ساختمان تولید A",
    kind: "building",
    parentId: "loc-site-1",
    path: "سایت اصفهان / ساختمان تولید A",
    note: "",
    deviceCount: 0,
  },
  {
    id: "loc-room-1",
    code: "RM-PUMP",
    name: "اتاق پمپ‌خانه",
    kind: "room",
    parentId: "loc-bld-1",
    path: "سایت اصفهان / ساختمان تولید A / اتاق پمپ‌خانه",
    note: "",
    deviceCount: 1,
  },
  {
    id: "loc-area-1",
    code: "AREA-CNC",
    name: "کارگاه ماشین‌کاری",
    kind: "area",
    parentId: "loc-bld-1",
    path: "سایت اصفهان / ساختمان تولید A / کارگاه ماشین‌کاری",
    note: "",
    deviceCount: 1,
  },
  {
    id: "loc-room-2",
    code: "RM-UTIL",
    name: "اتاق تأسیسات",
    kind: "room",
    parentId: "loc-site-1",
    path: "سایت اصفهان / اتاق تأسیسات",
    note: "",
    deviceCount: 1,
  },
];

export const demoPersonnel: MaintenancePersonnel[] = [
  {
    id: "per-1",
    personnelCode: "MT-101",
    fullName: "رضا احمدی",
    specialty: "mechanical",
    unit: "نگهداری مکانیک",
    phone: "0913-1234567",
    shift: "شیفت صبح",
    skills: ["تعویض یاتاقان", "هم‌محوری", "جوشکاری"],
    certifications: ["ایمنی کار در ارتفاع"],
    active: true,
  },
  {
    id: "per-2",
    personnelCode: "MT-102",
    fullName: "مریم کریمی",
    specialty: "instrumentation",
    unit: "ابزار دقیق",
    phone: "0913-2345678",
    shift: "شیفت صبح",
    skills: ["کالیبراسیون ترانسمیتر", "PLC"],
    certifications: ["کالیبراسیون ISO 17025"],
    active: true,
  },
  {
    id: "per-3",
    personnelCode: "MT-103",
    fullName: "حسین محمدی",
    specialty: "electrical",
    unit: "برق صنعتی",
    phone: "0913-3456789",
    shift: "شیفت عصر",
    skills: ["تابلو برق", "درایو"],
    certifications: [],
    active: true,
  },
  {
    id: "per-4",
    personnelCode: "MT-104",
    fullName: "سارا نوری",
    specialty: "hydraulic",
    unit: "هیدرولیک و پنوماتیک",
    phone: "0913-4567890",
    shift: "شیفت صبح",
    skills: ["عیب‌یابی پمپ هیدرولیک", "شیلنگ‌کشی"],
    certifications: [],
    active: true,
  },
  {
    id: "per-5",
    personnelCode: "MT-105",
    fullName: "علی رضایی",
    specialty: "facilities",
    unit: "تأسیسات",
    phone: "0913-5678901",
    shift: "شیفت شب",
    skills: ["چیلر", "دیگ بخار"],
    certifications: ["جوشکاری لوله"],
    active: false,
  },
];

export const demoSpareParts: SparePart[] = [
  {
    id: "part-1",
    code: "BRG-6205",
    name: "بلبرینگ 6205",
    unit: "عدد",
    quantityOnHand: 12,
    minimumStock: 4,
    lowStock: false,
    createdAt: "2026-05-02",
    updatedAt: "",
  },
  {
    id: "part-2",
    code: "OIL-ISO46",
    name: "روغن هیدرولیک ISO 46",
    unit: "لیتر",
    quantityOnHand: 3,
    minimumStock: 20,
    lowStock: true,
    createdAt: "2026-05-02",
    updatedAt: "",
  },
  {
    id: "part-3",
    code: "FLT-AIR-22",
    name: "فیلتر هوای کمپرسور",
    unit: "عدد",
    quantityOnHand: 7,
    minimumStock: 2,
    lowStock: false,
    createdAt: "2026-05-02",
    updatedAt: "",
  },
  {
    id: "part-4",
    code: "BLT-A55",
    name: "تسمه A55",
    unit: "عدد",
    quantityOnHand: 9,
    minimumStock: 3,
    lowStock: false,
    createdAt: "2026-05-02",
    updatedAt: "",
  },
];

const emptyNameplate = (): DeviceNameplate => ({
  manufacturer: "",
  modelNumber: "",
  serialNumber: "",
  assetType: "",
  manufactureYear: "",
  capacity: "",
  powerRating: "",
  electricalSpec: "",
  criticality: "medium",
  parentDeviceId: "",
  locationId: "",
  locationPath: "",
  operatorUnit: "",
  supplier: "",
  purchasedOn: "",
  installedOn: "",
  commissionedOn: "",
  warrantyUntil: "",
  purchaseCost: "0",
  runningHours: "0",
  notes: "",
});

const emptyAnalytics = (deviceId: string): DeviceAnalytics => ({
  deviceId,
  fromDate: "2026-03-26",
  toDate: "2026-09-26",
  windowDays: 184,
  totalOrders: 0,
  repairCount: 0,
  preventiveCount: 0,
  inspectionCount: 0,
  openOrders: 0,
  completedOrders: 0,
  repeatFailures: 0,
  totalDowntimeHours: 0,
  operatingHours: 0,
  mtbfHours: null,
  mttrHours: null,
  availabilityPercent: null,
  pmScheduled: 0,
  pmCompleted: 0,
  pmOnTime: 0,
  pmOverdue: 0,
  pmCompliancePercent: null,
  labourCost: 0,
  partsCost: 0,
  totalCost: 0,
  labourHours: 0,
  partsUsedCount: 0,
  partsUsedQuantity: 0,
  lastFailureAt: "",
  lastRepairAt: "",
  byFailureType: [],
  byFailedComponent: [],
  byRootCause: [],
  byDepartment: [],
  byStatus: {},
  byType: {},
  byPriority: {},
  partConsumption: [],
  technicians: [],
  trend: [],
});

const nameplateFor = (deviceId: string): DeviceNameplate => {
  const presets: Record<string, Partial<DeviceNameplate>> = {
    "dev-1": {
      manufacturer: "گراندفوس",
      modelNumber: "NK 80-250",
      serialNumber: "GF-2019-4471",
      assetType: "پمپ گریز از مرکز",
      manufactureYear: "1398",
      capacity: "120 مترمکعب بر ساعت",
      powerRating: "37 کیلووات",
      electricalSpec: "380 ولت / 50 هرتز",
      criticality: "critical",
      locationId: "loc-room-1",
      locationPath: "سایت اصفهان / ساختمان تولید A / اتاق پمپ‌خانه",
      operatorUnit: "واحد بهره‌برداری تولید",
      supplier: "شرکت تجهیزات صنعتی پارس",
      purchasedOn: "2019-05-12",
      installedOn: "2019-07-01",
      commissionedOn: "2019-07-20",
      warrantyUntil: "2021-07-20",
      purchaseCost: "1850000000",
      runningHours: "24500",
      notes: "پمپ اصلی مدار خنک‌کاری؛ توقف آن خط تولید را متوقف می‌کند.",
    },
    "dev-2": {
      manufacturer: "هاس",
      modelNumber: "ST-20Y",
      serialNumber: "HS-2021-1180",
      assetType: "تراش CNC",
      manufactureYear: "1400",
      capacity: "قطر کار 300 میلی‌متر",
      powerRating: "15 کیلووات",
      electricalSpec: "380 ولت / 50 هرتز",
      criticality: "high",
      locationId: "loc-area-1",
      locationPath: "سایت اصفهان / ساختمان تولید A / کارگاه ماشین‌کاری",
      operatorUnit: "واحد ماشین‌کاری",
      supplier: "ابزار دقیق شرق",
      purchasedOn: "2021-02-10",
      installedOn: "2021-04-01",
      commissionedOn: "2021-04-15",
      warrantyUntil: "2023-04-15",
      purchaseCost: "9400000000",
      runningHours: "11200",
      notes: "",
    },
    "dev-3": {
      manufacturer: "اطلس کوپکو",
      modelNumber: "GA 55",
      serialNumber: "AC-2018-3390",
      assetType: "کمپرسور اسکرو",
      manufactureYear: "1397",
      capacity: "10 بار / 9.4 مترمکعب بر دقیقه",
      powerRating: "55 کیلووات",
      electricalSpec: "380 ولت / 50 هرتز",
      criticality: "high",
      locationId: "loc-room-2",
      locationPath: "سایت اصفهان / اتاق تأسیسات",
      operatorUnit: "واحد تأسیسات",
      supplier: "هوای فشرده ایرانیان",
      purchasedOn: "2018-09-01",
      installedOn: "2018-10-10",
      commissionedOn: "2018-10-20",
      warrantyUntil: "2020-10-20",
      purchaseCost: "4200000000",
      runningHours: "38700",
      notes: "تأمین هوای فشرده کل کارخانه.",
    },
    "dev-4": {
      manufacturer: "کاترپیلار",
      modelNumber: "C15",
      serialNumber: "CT-2016-7788",
      assetType: "ژنراتور دیزلی",
      manufactureYear: "1395",
      capacity: "500 کیلوولت‌آمپر",
      powerRating: "400 کیلووات",
      electricalSpec: "400 ولت / 50 هرتز",
      criticality: "critical",
      locationId: "loc-site-1",
      locationPath: "سایت اصفهان",
      operatorUnit: "واحد برق",
      supplier: "نیرو گستر",
      purchasedOn: "2016-06-01",
      installedOn: "2016-08-01",
      commissionedOn: "2016-08-20",
      warrantyUntil: "2018-08-20",
      purchaseCost: "12500000000",
      runningHours: "4100",
      notes: "برق اضطراری؛ باید همیشه آماده به کار باشد.",
    },
  };
  return { ...emptyNameplate(), ...(presets[deviceId] ?? {}) };
};

const specificationsFor = (deviceId: string): DeviceSpecification[] => {
  const presets: Record<string, [string, string, string][]> = {
    "dev-1": [
      ["دبی اسمی", "120", "m³/h"],
      ["هد", "45", "m"],
      ["قطر پروانه", "250", "mm"],
      ["نوع آب‌بندی", "مکانیکال سیل", ""],
      ["دور موتور", "2950", "rpm"],
    ],
    "dev-2": [
      ["کورس محور X", "560", "mm"],
      ["دور اسپیندل", "4000", "rpm"],
      ["تعداد ابزار", "12", "عدد"],
      ["دقت تکرارپذیری", "0.005", "mm"],
    ],
    "dev-3": [
      ["فشار کاری", "10", "bar"],
      ["دبی هوا", "9.4", "m³/min"],
      ["حجم مخزن", "1000", "L"],
      ["نوع روغن", "Roto-Xtend", ""],
    ],
    "dev-4": [
      ["توان دائم", "400", "kW"],
      ["مصرف سوخت", "95", "L/h"],
      ["ظرفیت باک", "800", "L"],
      ["باتری", "24", "V"],
    ],
  };
  return (presets[deviceId] ?? []).map(([label, value, unit], index) => ({
    id: `${deviceId}-spec-${index + 1}`,
    label,
    value,
    unit,
    sortOrder: index,
  }));
};

const plansFor = (deviceId: string): PmPlan[] => {
  const presets: Record<string, [string, PmPlan["discipline"], number, PmPlan["frequencyUnit"], string, string][]> = {
    "dev-1": [
      ["روانکاری یاتاقان‌ها", "mechanical", 1, "month", "رضا احمدی", "2026-09-01"],
      ["بازرسی ارتعاش و هم‌محوری", "mechanical", 3, "month", "رضا احمدی", "2026-07-15"],
      ["تست عایقی موتور", "electrical", 6, "month", "حسین محمدی", "2026-05-10"],
      ["کالیبراسیون فشارسنج خروجی", "instrumentation", 1, "month", "مریم کریمی", "2026-08-20"],
      ["بازرسی نشتی مدار هیدرولیک", "hydraulic", 2, "month", "سارا نوری", "2026-08-05"],
      ["نظافت و بازرسی عمومی", "general", 1, "week", "", "2026-09-20"],
    ],
    "dev-2": [
      ["گریس‌کاری ریل‌ها", "mechanical", 1, "month", "رضا احمدی", "2026-09-05"],
      ["کالیبراسیون محور Z", "instrumentation", 3, "month", "مریم کریمی", "2026-08-01"],
      ["بازرسی تابلو برق", "electrical", 6, "month", "حسین محمدی", "2026-06-01"],
      ["بررسی سیستم پنوماتیک گیره", "pneumatic", 2, "month", "سارا نوری", "2026-08-10"],
    ],
    "dev-3": [
      ["تعویض فیلتر هوا", "mechanical", 3, "month", "رضا احمدی", "2026-07-01"],
      ["تخلیه کندانس مخزن", "general", 1, "week", "", "2026-09-22"],
      ["بازرسی شیر اطمینان", "facilities", 6, "month", "علی رضایی", "2026-04-15"],
      ["بررسی خط هوای فشرده", "pneumatic", 1, "month", "سارا نوری", "2026-09-10"],
    ],
    "dev-4": [
      ["تست بارگیری هفتگی", "electrical", 1, "week", "حسین محمدی", "2026-09-18"],
      ["تعویض روغن و فیلتر", "mechanical", 6, "month", "رضا احمدی", "2026-03-01"],
      ["بازرسی سیستم سوخت", "facilities", 3, "month", "علی رضایی", "2026-06-20"],
    ],
  };
  const addDays = (iso: string, days: number): string => {
    const date = new Date(`${iso}T00:00:00`);
    if (Number.isNaN(date.getTime())) return "";
    date.setDate(date.getDate() + days);
    return date.toISOString().slice(0, 10);
  };
  const unitDays: Record<PmPlan["frequencyUnit"], number> = {
    day: 1,
    week: 7,
    month: 30,
    runningHour: 0,
  };
  return (presets[deviceId] ?? []).map(([title, discipline, every, unit, responsible, last], index) => {
    const periodDays = unitDays[unit] * every;
    const nextDueOn = periodDays > 0 ? addDays(last, periodDays) : "";
    return {
      id: `${deviceId}-plan-${index + 1}`,
      deviceId,
      title,
      discipline,
      description: "",
      checklist: [],
      frequencyEvery: every,
      frequencyUnit: unit,
      periodDays,
      estimatedMinutes: 30 + index * 15,
      responsibleName: responsible,
      lastExecutedOn: last,
      nextDueOn,
      overdue: Boolean(nextDueOn) && nextDueOn < "2026-09-26",
      active: true,
    };
  });
};

const executionsFor = (deviceId: string, plans: PmPlan[]): PmExecution[] =>
  plans
    .filter((plan) => plan.lastExecutedOn)
    .map((plan, index) => ({
      id: `${deviceId}-exec-${index + 1}`,
      planId: plan.id,
      deviceId,
      discipline: plan.discipline,
      performedOn: plan.lastExecutedOn,
      dueOn: plan.lastExecutedOn,
      onTime: index % 3 !== 0,
      performedByName: plan.responsibleName || "تیم نگهداری",
      durationMinutes: plan.estimatedMinutes,
      findings: "",
    }));

const bomFor = (deviceId: string): DeviceBomItem[] => {
  const presets: Record<string, [string, string, number][]> = {
    "dev-1": [
      ["part-1", "یاتاقان سمت کوپلینگ", 2],
      ["part-2", "مخزن روغن‌کاری", 5],
    ],
    "dev-2": [["part-4", "تسمه محرک اسپیندل", 1]],
    "dev-3": [
      ["part-3", "ورودی هوا", 1],
      ["part-2", "مدار روغن‌کاری", 8],
    ],
    "dev-4": [["part-1", "یاتاقان آلترناتور", 2]],
  };
  return (presets[deviceId] ?? []).map(([partId, position, quantity], index) => {
    const part = demoSpareParts.find((item) => item.id === partId);
    return {
      id: `${deviceId}-bom-${index + 1}`,
      partId,
      partCode: part?.code ?? "",
      partName: part?.name ?? "",
      unit: part?.unit ?? "",
      position,
      standardQuantity: quantity,
      note: "",
      quantityOnHand: part?.quantityOnHand ?? 0,
      minimumStock: part?.minimumStock ?? 0,
      lowStock: part?.lowStock ?? false,
      usageCount: index,
      usedQuantity: index * quantity,
      lastUsedAt: index ? "2026-08-14" : "",
    };
  });
};

const assignmentsFor = (deviceId: string): DeviceAssignment[] => {
  const presets: Record<string, [DeviceAssignment["role"], string][]> = {
    "dev-1": [
      ["operator", "per-5"],
      ["responsible", "per-1"],
      ["technician", "per-2"],
      ["technician", "per-4"],
    ],
    "dev-2": [
      ["operator", "per-1"],
      ["responsible", "per-2"],
    ],
    "dev-3": [
      ["operator", "per-5"],
      ["responsible", "per-4"],
      ["technician", "per-1"],
    ],
    "dev-4": [
      ["responsible", "per-3"],
      ["deputy", "per-1"],
    ],
  };
  return (presets[deviceId] ?? []).map(([role, personnelId], index) => {
    const person = demoPersonnel.find((item) => item.id === personnelId);
    return {
      id: `${deviceId}-assign-${index + 1}`,
      role,
      personnelId,
      personnelName: person?.fullName ?? "",
      unit: person?.unit ?? "",
      fromDate: "2026-01-01",
      toDate: "",
      current: true,
    };
  });
};

const analyticsFor = (deviceId: string): DeviceAnalytics => {
  const presets: Record<string, Partial<DeviceAnalytics>> = {
    "dev-1": {
      totalOrders: 9,
      repairCount: 4,
      preventiveCount: 4,
      inspectionCount: 1,
      openOrders: 1,
      completedOrders: 8,
      repeatFailures: 1,
      totalDowntimeHours: 26.5,
      operatingHours: 4390,
      mtbfHours: 1097.5,
      mttrHours: 3.4,
      availabilityPercent: 99.4,
      pmScheduled: 10,
      pmCompleted: 8,
      pmOnTime: 7,
      pmOverdue: 1,
      pmCompliancePercent: 70,
      labourCost: 48000000,
      partsCost: 92000000,
      totalCost: 140000000,
      labourHours: 31,
      partsUsedCount: 6,
      partsUsedQuantity: 14,
      lastFailureAt: "2026-08-14",
      lastRepairAt: "2026-08-15",
      byFailureType: [
        { label: "mechanical", count: 3 },
        { label: "electrical", count: 1 },
      ],
      byFailedComponent: [
        { label: "یاتاقان", count: 2 },
        { label: "مکانیکال سیل", count: 1 },
        { label: "کوپلینگ", count: 1 },
      ],
      byRootCause: [
        { label: "روانکاری ناکافی", count: 2 },
        { label: "فرسودگی", count: 2 },
      ],
      trend: [
        { label: "1405-03", failures: 1, preventive: 1, downtimeHours: 5, cost: 18000000 },
        { label: "1405-04", failures: 0, preventive: 2, downtimeHours: 0, cost: 6000000 },
        { label: "1405-05", failures: 2, preventive: 1, downtimeHours: 14.5, cost: 82000000 },
        { label: "1405-06", failures: 1, preventive: 0, downtimeHours: 7, cost: 34000000 },
      ],
      technicians: [
        {
          name: "رضا احمدی",
          totalOrders: 6,
          correctiveOrders: 3,
          preventiveOrders: 3,
          completedOrders: 6,
          openOrders: 0,
          labourHours: 21,
          averageRepairHours: 3.1,
        },
        {
          name: "مریم کریمی",
          totalOrders: 3,
          correctiveOrders: 1,
          preventiveOrders: 2,
          completedOrders: 2,
          openOrders: 1,
          labourHours: 10,
          averageRepairHours: 4.2,
        },
      ],
    },
    "dev-4": {
      totalOrders: 5,
      repairCount: 3,
      preventiveCount: 2,
      openOrders: 1,
      completedOrders: 4,
      repeatFailures: 2,
      totalDowntimeHours: 61,
      operatingHours: 4320,
      mtbfHours: 1440,
      mttrHours: 8.2,
      availabilityPercent: 98.6,
      pmScheduled: 6,
      pmCompleted: 3,
      pmOnTime: 2,
      pmOverdue: 2,
      pmCompliancePercent: 33.3,
      labourCost: 22000000,
      partsCost: 150000000,
      totalCost: 172000000,
      labourHours: 25,
      partsUsedCount: 3,
      partsUsedQuantity: 5,
      lastFailureAt: "2026-09-20",
      byFailureType: [{ label: "electrical", count: 3 }],
      byFailedComponent: [{ label: "باتری", count: 2 }, { label: "استارتر", count: 1 }],
      byRootCause: [{ label: "پایان عمر مفید", count: 3 }],
    },
  };
  return { ...emptyAnalytics(deviceId), ...(presets[deviceId] ?? {}) };
};

const buildProfile = (device: MaintenanceDevice): DeviceProfile => {
  const plans = plansFor(device.id);
  const nameplate = nameplateFor(device.id);
  return {
    device: {
      ...device,
      manufacturer: nameplate.manufacturer,
      modelNumber: nameplate.modelNumber,
      serialNumber: nameplate.serialNumber,
      equipmentType: nameplate.assetType,
      criticality: nameplate.criticality,
      locationId: nameplate.locationId,
      locationPath: nameplate.locationPath,
      operatorUnit: nameplate.operatorUnit,
      runningHours: Number(nameplate.runningHours) || 0,
    },
    nameplate,
    specifications: specificationsFor(device.id),
    pmPlans: plans,
    pmExecutions: executionsFor(device.id, plans),
    bom: bomFor(device.id),
    assignments: assignmentsFor(device.id),
    location: demoLocations.find((item) => item.id === nameplate.locationId) ?? null,
    locationPath: nameplate.locationPath || device.location,
    children: [],
    analytics: analyticsFor(device.id),
    generatedAt: "2026-09-26",
  };
};

/** Devices as the registry sees them — master data merged with the nameplate. */
export const demoRegistryDevices: MaintenanceDevice[] = demoDevices.map(
  (device) => buildProfile(device).device,
);

interface DemoStore {
  locations: MaintenanceLocation[];
  personnel: MaintenancePersonnel[];
  profiles: Record<string, DeviceProfile>;
}

const store: DemoStore = {
  locations: clone(demoLocations),
  personnel: clone(demoPersonnel),
  profiles: Object.fromEntries(demoDevices.map((device) => [device.id, buildProfile(device)])),
};

const locationPath = (locationId: string): string =>
  store.locations.find((item) => item.id === locationId)?.path ?? "";

const profileOf = (deviceId: string): DeviceProfile => {
  const existing = store.profiles[deviceId];
  if (existing) return existing;
  const known = demoDevices.find((device) => device.id === deviceId);
  const fallback: MaintenanceDevice = known ?? {
    id: deviceId,
    code: deviceId,
    name: deviceId,
    location: "",
    status: "operational",
    department: "general",
    pmIntervalDays: 0,
    lastPmDate: "",
    nextDueDate: "",
    pmDue: false,
    createdAt: "",
  };
  const created = buildProfile(fallback);
  store.profiles[deviceId] = created;
  return created;
};

/** Registers a device created through the demo UI so its profile page works. */
export const registerDemoDevice = (device: MaintenanceDevice): void => {
  store.profiles[device.id] = {
    ...buildProfile(device),
    device,
    nameplate: { ...emptyNameplate(), criticality: device.criticality ?? "medium" },
    specifications: [],
    pmPlans: [],
    pmExecutions: [],
    bom: [],
    assignments: [],
    location: null,
    locationPath: device.location,
    analytics: emptyAnalytics(device.id),
  };
};

const asFleet = (): FleetAnalytics => {
  const rows = Object.values(store.profiles).map((profile) => {
    const analytics = profile.analytics ?? emptyAnalytics(profile.device.id);
    return {
      deviceId: profile.device.id,
      code: profile.device.code,
      name: profile.device.name,
      department: profile.device.department,
      criticality: profile.nameplate.criticality,
      locationPath: profile.locationPath,
      status: profile.device.status,
      repairCount: analytics.repairCount,
      preventiveCount: analytics.preventiveCount,
      repeatFailures: analytics.repeatFailures,
      downtimeHours: analytics.totalDowntimeHours,
      mtbfHours: analytics.mtbfHours,
      mttrHours: analytics.mttrHours,
      availabilityPercent: analytics.availabilityPercent,
      pmCompliancePercent: analytics.pmCompliancePercent,
      partsUsedQuantity: analytics.partsUsedQuantity,
      totalCost: analytics.totalCost,
    };
  });
  const sum = (pick: (row: (typeof rows)[number]) => number): number =>
    rows.reduce((total, row) => total + pick(row), 0);
  const average = (values: number[]): number | null =>
    values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
  return {
    fromDate: "2026-03-26",
    toDate: "2026-09-26",
    generatedAt: "2026-09-26",
    deviceCount: rows.length,
    totalRepairs: sum((row) => row.repairCount),
    totalPreventive: sum((row) => row.preventiveCount),
    totalDowntimeHours: sum((row) => row.downtimeHours),
    totalCost: sum((row) => row.totalCost),
    fleetMtbfHours: average(rows.map((row) => row.mtbfHours ?? 0).filter(Boolean)),
    fleetMttrHours: average(rows.map((row) => row.mttrHours ?? 0).filter(Boolean)),
    fleetAvailabilityPercent: average(
      rows.map((row) => row.availabilityPercent ?? 0).filter(Boolean),
    ),
    pmCompliancePercent: average(rows.map((row) => row.pmCompliancePercent ?? 0).filter(Boolean)),
    rows,
    topParts: demoSpareParts.slice(0, 3).map((part, index) => ({
      partId: part.id,
      partCode: part.code,
      partName: part.name,
      unit: part.unit,
      usageCount: 6 - index,
      totalQuantity: 14 - index * 3,
      totalCost: 92000000 - index * 21000000,
      lastUsedAt: "2026-08-14",
      deviceCount: 2,
    })),
    topFailureTypes: [
      { label: "mechanical", count: 4 },
      { label: "electrical", count: 4 },
    ],
    technicians: store.profiles["dev-1"]?.analytics?.technicians ?? [],
    trend: store.profiles["dev-1"]?.analytics?.trend ?? [],
  };
};

/** An in-memory {@link RegistryService} used when demo mode is active. */
export const createDemoRegistryService = (): RegistryService => ({
  listLocations: async (search = "") =>
    clone(
      store.locations.filter((item) =>
        `${item.code} ${item.name} ${item.path}`.toLowerCase().includes(search.toLowerCase()),
      ),
    ),
  createLocation: async (input) => {
    const parent = store.locations.find((item) => item.id === input.parentId);
    const created: MaintenanceLocation = {
      id: nextId("loc"),
      code: input.code ?? "",
      name: input.name,
      kind: input.kind,
      parentId: input.parentId ?? "",
      path: parent ? `${parent.path} / ${input.name}` : input.name,
      note: input.note ?? "",
      deviceCount: 0,
    };
    store.locations = [...store.locations, created];
    return clone(created);
  },
  updateLocation: async (id, input) => {
    const parent = store.locations.find((item) => item.id === input.parentId);
    const updated: MaintenanceLocation = {
      id,
      code: input.code ?? "",
      name: input.name,
      kind: input.kind,
      parentId: input.parentId ?? "",
      path: parent ? `${parent.path} / ${input.name}` : input.name,
      note: input.note ?? "",
      deviceCount: store.locations.find((item) => item.id === id)?.deviceCount ?? 0,
    };
    store.locations = store.locations.map((item) => (item.id === id ? updated : item));
    return clone(updated);
  },
  deleteLocation: async (id) => {
    store.locations = store.locations.filter((item) => item.id !== id);
  },
  listPersonnel: async (filters = {}) =>
    clone(
      store.personnel.filter(
        (person) =>
          (!filters.specialty || person.specialty === filters.specialty) &&
          `${person.personnelCode} ${person.fullName} ${person.unit}`
            .toLowerCase()
            .includes((filters.search ?? "").toLowerCase()),
      ),
    ),
  createPersonnel: async (input) => {
    const created: MaintenancePersonnel = {
      id: nextId("per"),
      personnelCode: input.personnelCode ?? "",
      fullName: input.fullName,
      specialty: input.specialty,
      unit: input.unit ?? "",
      phone: input.phone ?? "",
      shift: input.shift ?? "",
      skills: input.skills ?? [],
      certifications: input.certifications ?? [],
      active: input.active ?? true,
    };
    store.personnel = [...store.personnel, created];
    return clone(created);
  },
  updatePersonnel: async (id, input) => {
    const updated: MaintenancePersonnel = {
      id,
      personnelCode: input.personnelCode ?? "",
      fullName: input.fullName,
      specialty: input.specialty,
      unit: input.unit ?? "",
      phone: input.phone ?? "",
      shift: input.shift ?? "",
      skills: input.skills ?? [],
      certifications: input.certifications ?? [],
      active: input.active ?? true,
    };
    store.personnel = store.personnel.map((item) => (item.id === id ? updated : item));
    return clone(updated);
  },
  deletePersonnel: async (id) => {
    store.personnel = store.personnel.filter((item) => item.id !== id);
  },
  getDeviceProfile: async (deviceId) => clone(profileOf(deviceId)),
  updateNameplate: async (deviceId, values) => {
    const profile = profileOf(deviceId);
    const nameplate = { ...profile.nameplate, ...values } as DeviceNameplate;
    nameplate.locationPath = locationPath(nameplate.locationId) || nameplate.locationPath;
    store.profiles[deviceId] = {
      ...profile,
      nameplate,
      locationPath: nameplate.locationPath,
      location: store.locations.find((item) => item.id === nameplate.locationId) ?? null,
      device: {
        ...profile.device,
        manufacturer: nameplate.manufacturer,
        modelNumber: nameplate.modelNumber,
        serialNumber: nameplate.serialNumber,
        equipmentType: nameplate.assetType,
        criticality: nameplate.criticality,
        locationId: nameplate.locationId,
        locationPath: nameplate.locationPath,
        operatorUnit: nameplate.operatorUnit,
        runningHours: Number(nameplate.runningHours) || 0,
      },
    };
    return clone(nameplate);
  },
  saveSpecifications: async (deviceId, rows) => {
    const profile = profileOf(deviceId);
    const specifications = rows.map((row, index) => ({
      id: `${deviceId}-spec-${index + 1}`,
      label: row.label,
      value: row.value ?? "",
      unit: row.unit ?? "",
      sortOrder: row.sortOrder ?? index,
    }));
    store.profiles[deviceId] = { ...profile, specifications };
    return clone(specifications);
  },
  listPmPlans: async (deviceId) => clone(profileOf(deviceId).pmPlans),
  createPmPlan: async (deviceId, input) => {
    const profile = profileOf(deviceId);
    const plan: PmPlan = {
      id: nextId("plan"),
      deviceId,
      title: input.title,
      discipline: input.discipline,
      description: input.description ?? "",
      checklist: input.checklist ?? [],
      frequencyEvery: input.frequencyEvery,
      frequencyUnit: input.frequencyUnit,
      periodDays:
        input.frequencyUnit === "day"
          ? input.frequencyEvery
          : input.frequencyUnit === "week"
            ? input.frequencyEvery * 7
            : input.frequencyUnit === "month"
              ? input.frequencyEvery * 30
              : 0,
      estimatedMinutes: input.estimatedMinutes ?? 0,
      responsibleName: input.responsibleName ?? "",
      lastExecutedOn: "",
      nextDueOn: "",
      overdue: false,
      active: input.active ?? true,
    };
    store.profiles[deviceId] = { ...profile, pmPlans: [...profile.pmPlans, plan] };
    return clone(plan);
  },
  updatePmPlan: async (planId, input) => {
    let result: PmPlan | null = null;
    Object.entries(store.profiles).forEach(([deviceId, profile]) => {
      const plans = profile.pmPlans.map((plan) => {
        if (plan.id !== planId) return plan;
        result = {
          ...plan,
          title: input.title,
          discipline: input.discipline,
          description: input.description ?? "",
          checklist: input.checklist ?? [],
          frequencyEvery: input.frequencyEvery,
          frequencyUnit: input.frequencyUnit,
          estimatedMinutes: input.estimatedMinutes ?? 0,
          responsibleName: input.responsibleName ?? "",
          active: input.active ?? true,
        };
        return result;
      });
      store.profiles[deviceId] = { ...profile, pmPlans: plans };
    });
    if (!result) throw new Error("برنامه PM یافت نشد.");
    return clone(result);
  },
  deletePmPlan: async (planId) => {
    Object.entries(store.profiles).forEach(([deviceId, profile]) => {
      store.profiles[deviceId] = {
        ...profile,
        pmPlans: profile.pmPlans.filter((plan) => plan.id !== planId),
      };
    });
  },
  recordPmExecution: async (planId, input) => {
    let execution: PmExecution | null = null;
    Object.entries(store.profiles).forEach(([deviceId, profile]) => {
      const plan = profile.pmPlans.find((item) => item.id === planId);
      if (!plan) return;
      const performedOn = input.performedOn || "2026-09-26";
      execution = {
        id: nextId("exec"),
        planId,
        deviceId,
        discipline: plan.discipline,
        performedOn,
        dueOn: plan.nextDueOn,
        onTime: !plan.nextDueOn || performedOn <= plan.nextDueOn,
        performedByName: input.performedByName ?? "",
        durationMinutes: input.durationMinutes ?? 0,
        findings: input.findings ?? "",
      };
      store.profiles[deviceId] = {
        ...profile,
        pmPlans: profile.pmPlans.map((item) =>
          item.id === planId
            ? { ...item, lastExecutedOn: performedOn, overdue: false, nextDueOn: "" }
            : item,
        ),
        pmExecutions: [execution, ...profile.pmExecutions],
      };
    });
    if (!execution) throw new Error("برنامه PM یافت نشد.");
    return clone(execution);
  },
  addBomItem: async (deviceId, input) => {
    const profile = profileOf(deviceId);
    const part = demoSpareParts.find((item) => item.id === input.partId);
    const item: DeviceBomItem = {
      id: nextId("bom"),
      partId: input.partId,
      partCode: part?.code ?? "",
      partName: part?.name ?? "",
      unit: part?.unit ?? "",
      position: input.position ?? "",
      standardQuantity: Number(input.standardQuantity ?? "1") || 1,
      note: input.note ?? "",
      quantityOnHand: part?.quantityOnHand ?? 0,
      minimumStock: part?.minimumStock ?? 0,
      lowStock: part?.lowStock ?? false,
      usageCount: 0,
      usedQuantity: 0,
      lastUsedAt: "",
    };
    store.profiles[deviceId] = {
      ...profile,
      bom: [...profile.bom.filter((row) => row.partId !== input.partId), item],
    };
    return clone(item);
  },
  removeBomItem: async (deviceId, partId) => {
    const profile = profileOf(deviceId);
    store.profiles[deviceId] = {
      ...profile,
      bom: profile.bom.filter((row) => row.partId !== partId),
    };
  },
  saveAssignments: async (deviceId, rows) => {
    const profile = profileOf(deviceId);
    const assignments: DeviceAssignment[] = rows.map((row, index) => {
      const person = store.personnel.find((item) => item.id === row.personnelId);
      return {
        id: `${deviceId}-assign-${index + 1}`,
        role: row.role,
        personnelId: row.personnelId ?? "",
        personnelName: person?.fullName ?? row.personnelName ?? "",
        unit: row.unit || person?.unit || "",
        fromDate: row.fromDate ?? "",
        toDate: row.toDate ?? "",
        current: !row.toDate,
      };
    });
    store.profiles[deviceId] = { ...profile, assignments };
    return clone(assignments);
  },
  getDeviceAnalytics: async (deviceId) =>
    clone(profileOf(deviceId).analytics ?? emptyAnalytics(deviceId)),
  getFleetAnalytics: async (filters = {}) => {
    const fleet = asFleet();
    const rows = fleet.rows.filter(
      (row) =>
        (!filters.department || row.department === filters.department) &&
        (!filters.criticality || row.criticality === filters.criticality),
    );
    return clone({ ...fleet, rows, deviceCount: rows.length });
  },
  getPartUsageReport: async (partId) => {
    const part = demoSpareParts.find((item) => item.id === partId);
    const report: PartUsageReport = {
      partId,
      partCode: part?.code ?? "",
      partName: part?.name ?? "",
      unit: part?.unit ?? "",
      fromDate: "2026-03-26",
      toDate: "2026-09-26",
      totalUsageCount: 3,
      totalQuantity: 7,
      devices: [
        {
          deviceId: "dev-1",
          deviceCode: "PUMP-01",
          deviceName: "پمپ خنک‌کننده اصلی",
          usageCount: 2,
          totalQuantity: 4,
          lastUsedAt: "2026-08-14",
        },
      ],
    };
    return clone(report);
  },
  recordClosureDetails: async (_workOrderId, input) => ({ ...input }),
});
