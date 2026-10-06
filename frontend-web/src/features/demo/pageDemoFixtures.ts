/**
 * Fabricated records that used to sit inline inside page components.
 *
 * Inline fixtures are invisible to the build: `ProcurementPage` carried a
 * fake supplier and `AccountPage` a fake administrator, and both were linked
 * into every production bundle no matter what `demoMode` said. Collected
 * here, they fall under `vite/demoFixtureFirewall.ts` and are replaced with
 * empty stubs whenever demo mode is off.
 *
 * Nothing in this file may be imported by a code path that runs with demo
 * mode off. `src/tests/demoFixtureIsolation.test.ts` enforces that.
 */

import type { PartTransaction, SparePart } from "../../shared/types/domain";

/** Mirrors the row shape `ProcurementPage` keeps for suppliers. */
export interface Supplier {
  id: string;
  code: string;
  name: string;
  status: string;
  contactName: string;
  phone: string;
  defaultLeadTimeDays: number;
  currency: string;
}

export interface DemoAccountUser {
  id: string;
  tenantId: string;
  username: string;
  email: string;
  displayName: string;
  status: string;
  createdAt: string;
}

export interface DemoRole {
  id: string;
  name: string;
  code: string;
  scopeType: string;
  actions: string[];
}

export const demoSuppliers: Supplier[] = [
  {
    id: "sup-demo",
    code: "SUP-001",
    name: "تأمین‌کننده نمونه",
    status: "active",
    contactName: "واحد فروش",
    phone: "",
    defaultLeadTimeDays: 7,
    currency: "IRR",
  },
];
export const demoProcurementParts = [
  {
    id: "sp-demo",
    code: "DEMO-001",
    name: "قطعه نمونه",
    unit: "عدد",
    unitCost: 100000,
  },
];

export const demoRoles: DemoRole[] = [
  {
    id: "demo",
    name: "مدیر سکو",
    code: "platformAdmin",
    scopeType: "GLOBAL",
    actions: [
      "procurement.requisition.approve",
      "procurement.purchaseOrder.approve",
      "procurement.receipt.post",
      "procurement.return.post",
      "procurement.invoice.manage",
    ],
  },
];

export const demoAccountUser: DemoAccountUser = {
  id: "demo",
  tenantId: "demo",
  username: "demo.admin",
  email: "demo@tekarai.local",
  displayName: "راهبر نمایشی",
  status: "active",
  createdAt: "",
};

export const demoParts: SparePart[] = [
  {
    id: "sp-1",
    code: "SAL-4021",
    name: "بلبرینگ 6204",
    unit: "عدد",
    quantityOnHand: 42,
    minimumStock: 20,
    unitCost: 185_000,
    lowStock: false,
    createdAt: "1405/05/12",
    updatedAt: "",
  },
  {
    id: "sp-2",
    code: "BLT-1180",
    name: "تسمه V118",
    unit: "عدد",
    quantityOnHand: 6,
    minimumStock: 10,
    unitCost: 320_000,
    lowStock: true,
    createdAt: "1405/05/12",
    updatedAt: "",
  },
  {
    id: "sp-3",
    code: "FLT-2200",
    name: "فیلتر روغن هیدرولیک",
    unit: "عدد",
    quantityOnHand: 15,
    minimumStock: 8,
    unitCost: 610_000,
    lowStock: false,
    createdAt: "1405/05/13",
    updatedAt: "",
  },
  {
    id: "sp-4",
    code: "OIL-5046",
    name: "روغن هیدرولیک ISO46",
    unit: "لیتر",
    quantityOnHand: 120,
    minimumStock: 60,
    unitCost: 340_000,
    lowStock: false,
    createdAt: "1405/05/14",
    updatedAt: "",
  },
  {
    id: "sp-5",
    code: "SL-3309",
    name: "سیل مکانیکی 45mm",
    unit: "عدد",
    quantityOnHand: 3,
    minimumStock: 5,
    unitCost: 1_850_000,
    lowStock: true,
    createdAt: "1405/05/15",
    updatedAt: "",
  },
  {
    id: "sp-6",
    code: "CNT-8800",
    name: "کنتاکتور 25A",
    unit: "عدد",
    quantityOnHand: 9,
    minimumStock: 4,
    unitCost: 2_400_000,
    lowStock: false,
    createdAt: "1405/05/15",
    updatedAt: "",
  },
];

/** دفتر نمایشی هر قطعه: دو ردیف منسجم که به موجودی فعلی می‌رسد. */
export function seedDemoLedger(part: SparePart): PartTransaction[] {
  const received: PartTransaction = {
    id: `${part.id}-t1`,
    partId: part.id,
    partCode: part.code,
    partName: part.name,
    unit: part.unit,
    transactionType: "RECEIPT",
    typeLabel: "رسید",
    quantity: part.quantityOnHand + 2,
    balanceAfter: part.quantityOnHand + 2,
    note: "موجودی اولیه",
    reference: "رسید ابتدایی",
    actorId: "",
    createdAt: part.createdAt,
  };
  const counted: PartTransaction = {
    id: `${part.id}-t2`,
    partId: part.id,
    partCode: part.code,
    partName: part.name,
    unit: part.unit,
    transactionType: "ADJUSTMENT",
    typeLabel: "تعدیل",
    quantity: -2,
    balanceAfter: part.quantityOnHand,
    note: "انبارگردانی",
    reference: "",
    actorId: "",
    createdAt: part.createdAt,
  };
  return [counted, received];
}
