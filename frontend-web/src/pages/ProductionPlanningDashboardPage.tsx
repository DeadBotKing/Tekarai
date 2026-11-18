import { useMemo, useState } from "react";
import { Card, SectionHeader, ProgressBar, Button } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { toPersianDigits } from "../core/localization/jalali";
import { usePermissions } from "../core/permissions/permissionContext";
import { useAuth } from "../core/auth/authContext";

type LineStatus = "running" | "stopped" | "changeover" | "maintenance";
type ProductGroup =
  | "tablets_capsules"
  | "softgel"
  | "vials_lyo"
  | "powder_filling"
  | "syringes_ampoules";

type CompanyCode =
  | "ronak_internal"
  | "arang"
  | "ronapharmed"
  | "hakiman"
  | "zistdaru";

interface ProductionLine {
  id: string;
  name: string;
  product: string;
  group: ProductGroup;
  status: LineStatus;
  company: CompanyCode;
  planned: number;
  produced: number;
  nominalSpeed: number;
  actualSpeed: number;
  stopMinutes?: number | null;
  wastePct?: number | null;
  oeePct?: number | null;
  shift: number;
  lastUpdated: string;
}

const STATUS_META: Record<LineStatus, { label: string; color: string; dot: string }> = {
  running:     { label: "در حال تولید",  color: "#10b981", dot: "#10b981" },
  stopped:     { label: "متوقف",         color: "#ef4444", dot: "#ef4444" },
  changeover:  { label: "تعویض محصول",   color: "#f59e0b", dot: "#f59e0b" },
  maintenance: { label: "تعمیرات",        color: "#6b7280", dot: "#6b7280" },
};

interface GroupMeta {
  key: ProductGroup;
  label: string;
  short: string;
  color: string;
  icon: import("../shared/components/Icon").IconName;
}

const GROUPS: GroupMeta[] = [
  { key: "tablets_capsules", label: "قرص و کپسول",      short: "T/C", color: "#0ea5e9", icon: "target" },
  { key: "softgel",          label: "سافت‌ژل",          short: "S/G", color: "#8b5cf6", icon: "layers" },
  { key: "vials_lyo",        label: "ویال و لیوفیلیزه",  short: "V/L", color: "#10b981", icon: "activity" },
  { key: "powder_filling",   label: "پودر فیلینگ",      short: "PWD", color: "#f59e0b", icon: "briefcase" },
  { key: "syringes_ampoules",label: "سرنگ و آمپول",     short: "S/A", color: "#ef4444", icon: "bell" },
];

interface CompanyMeta {
  key: CompanyCode;
  label: string;
  short: string;
  color: string;
  icon: import("../shared/components/Icon").IconName;
  isContract: boolean;
}

const COMPANIES: CompanyMeta[] = [
  { key: "ronak_internal", label: "روناک (داخلی)", short: "روناک", color: "#0f766e", icon: "building", isContract: false },
  { key: "arang",          label: "آرنگ",          short: "آرنگ", color: "#6366f1", icon: "briefcase", isContract: true },
  { key: "ronapharmed",    label: "رونافارمد",     short: "رونافارمد", color: "#db2777", icon: "users", isContract: true },
  { key: "hakiman",        label: "حکیمان",        short: "حکیمان", color: "#059669", icon: "layers", isContract: true },
  { key: "zistdaru",       label: "زیست دارو",     short: "زیست‌دارو", color: "#ea580c", icon: "target", isContract: true },
];

const fmtNum = (n: number): string => toPersianDigits(n.toLocaleString("en-US"));
const fmtPct = (n: number): string => toPersianDigits(n.toFixed(1) + "%");
const NA = "—";
const fmtOptPct = (n: number | null | undefined): string => (n == null ? NA : fmtPct(n));
const fmtOptDur = (minutes: number | null | undefined): string => (minutes == null ? NA : fmtDur(minutes));
const fmtDur = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h === 0) return toPersianDigits(m + " دقیقه");
  return toPersianDigits(h + "h " + m + "m");
};

const thStyle: React.CSSProperties = {
  padding: "11px 12px", textAlign: "right", fontSize: "0.76rem", fontWeight: 700,
  color: "#374151", letterSpacing: 0.3, whiteSpace: "nowrap",
};
const thStyleNum: React.CSSProperties = { ...thStyle, textAlign: "center", direction: "ltr" };
const tdStyle: React.CSSProperties = {
  padding: "9px 12px", textAlign: "right", fontSize: "0.82rem", color: "#1f2937",
  borderBottom: "1px solid transparent", whiteSpace: "nowrap",
};
const tdStyleNum: React.CSSProperties = { ...tdStyle, textAlign: "center", direction: "ltr", fontVariantNumeric: "tabular-nums" };

/** Demo production lines grouped by product family + contracted company. */
const DEMO_LINES: ProductionLine[] = [
  // قرص و کپسول
  { id: "L02", name: "خط ۰۲ – قرص‌زنی",          product: "قرص 500mg",     group: "tablets_capsules",   company: "arang",          status: "running",     planned: 80000, produced: 79200, nominalSpeed: 1200, actualSpeed: 1180, stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:43" },
  { id: "L06", name: "خط ۰۶ – کپسول‌زنی",        product: "کپسول 250mg",   group: "tablets_capsules",   company: "ronapharmed",    status: "stopped",     planned: 45000, produced: 28700, nominalSpeed: 800,  actualSpeed: 0,    stopMinutes: null, wastePct: null, oeePct: null, shift: 1, lastUpdated: "11:05" },
  // سافت‌ژل
  { id: "L08", name: "خط ۰۸ – سافت‌ژل",          product: "سافت‌ژل ۵۰۰mg", group: "softgel",            company: "ronak_internal", status: "running",     planned: 35000, produced: 31200, nominalSpeed: 700,  actualSpeed: 660,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:45" },
  // ویال و لیوفیلیزه
  { id: "L04", name: "خط ۰۴ – ویال پرکن",        product: "ویال 10ml",     group: "vials_lyo",          company: "hakiman",        status: "running",     planned: 20000, produced: 16800, nominalSpeed: 400,  actualSpeed: 360,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:40" },
  { id: "L09", name: "خط ۰۹ – لیوفیلیزه",        product: "ویال لیو ۵۰۰mg",group: "vials_lyo",          company: "zistdaru",       status: "changeover",  planned: 12000, produced: 7400,  nominalSpeed: 240,  actualSpeed: 220,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:25" },
  // پودر فیلینگ
  { id: "L10", name: "خط ۱۰ – پودر فیلینگ",      product: "پودر ویال",     group: "powder_filling",     company: "arang",          status: "running",     planned: 15000, produced: 13800, nominalSpeed: 300,  actualSpeed: 290,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:44" },
  // سرنگ و آمپول
  { id: "L01", name: "خط ۰۱ – آمپول پرکن",       product: "آمپول 2ml",     group: "syringes_ampoules",  company: "ronapharmed",    status: "running",     planned: 50000, produced: 47500, nominalSpeed: 1000, actualSpeed: 950,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:42" },
  { id: "L07", name: "خط ۰۷ – سرنگ پرکن",        product: "سرنگ 5ml",      group: "syringes_ampoules",  company: "ronak_internal", status: "maintenance", planned: 22000, produced: 10100, nominalSpeed: 440,  actualSpeed: 0,    stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "11:30" },
];

interface GroupTotals {
  key: ProductGroup;
  label: string;
  color: string;
  icon: GroupMeta["icon"];
  planned: number;
  produced: number;
  achievement: number;
  weightedOee: number | null;
  totalStopMin: number | null;
  weightedWaste: number | null;
  lineCount: number;
  runningCount: number;
  issueCount: number;
  lines: ProductionLine[];
}

interface CompanyTotals {
  key: CompanyCode;
  label: string;
  color: string;
  icon: CompanyMeta["icon"];
  isContract: boolean;
  planned: number;
  produced: number;
  achievement: number;
  shareOfTotal: number;
  shareOfContract: number | null;
  lineCount: number;
  lines: ProductionLine[];
}

/** Big product-group summary card (one per product family). */
function GroupCard({ g, onJump }: { g: GroupTotals; onJump?: (group: ProductGroup) => void }): JSX.Element {
  const achColor = g.achievement >= 95 ? "#10b981" : g.achievement >= 80 ? "#f59e0b" : "#ef4444";
  const oeeColor = (g.weightedOee ?? 0) >= 85 ? "#10b981" : (g.weightedOee ?? 0) >= 70 ? "#f59e0b" : "#ef4444";
  const wasteColor = (g.weightedWaste ?? 0) > 2.5 ? "#ef4444" : (g.weightedWaste ?? 0) > 1.5 ? "#f59e0b" : "#10b981";
  const iconName = g.icon;
  return (
    <Card padding="lg" style={{ borderRight: `5px solid ${g.color}`, position: "relative" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <div style={{ width: 44, height: 44, borderRadius: 12, background: g.color + "15", color: g.color, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name={iconName as any} size={22} />
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>{g.label}</h3>
          <div style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: 2 }}>
            {toPersianDigits(g.runningCount.toString())} خط فعال از {toPersianDigits(g.lineCount.toString())} خط
            {g.issueCount > 0 && <span style={{ color: "#ef4444", marginRight: 8 }}>• {toPersianDigits(g.issueCount.toString())} خط دارای مشکل</span>}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
        <div style={{ background: "#f9fafb", borderRadius: 10, padding: "10px 12px", textAlign: "center" }}>
          <div style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 3 }}>برنامه</div>
          <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(g.planned)}</div>
        </div>
        <div style={{ background: "#f9fafb", borderRadius: 10, padding: "10px 12px", textAlign: "center" }}>
          <div style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 3 }}>تولید</div>
          <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(g.produced)}</div>
        </div>
      </div>

      <div style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.74rem", color: "#6b7280", marginBottom: 4 }}>
          <span>تحقق</span><span style={{ color: achColor, fontWeight: 700 }}>{fmtPct(g.achievement)}</span>
        </div>
        <ProgressBar value={Math.min(g.achievement, 100)} tone={g.achievement >= 95 ? "green" : g.achievement >= 80 ? "amber" : "purple"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: "0.78rem", borderTop: "1px solid #eef0f2", paddingTop: 10 }}>
        <MiniStat label="OEE" value={fmtOptPct(g.weightedOee)} color={g.weightedOee == null ? "#cbd5e1" : oeeColor} />
        <MiniStat label="توقف" value={fmtOptDur(g.totalStopMin)} color={g.totalStopMin == null ? "#cbd5e1" : g.totalStopMin > 120 ? "#ef4444" : "#6b7280"} />
        <MiniStat label="ضایعات" value={fmtOptPct(g.weightedWaste)} color={g.weightedWaste == null ? "#cbd5e1" : wasteColor} />
      </div>

      {onJump && (
        <button
          type="button"
          onClick={() => onJump(g.key)}
          style={{
            position: "absolute", top: 12, left: 12, background: "transparent", border: "none",
            color: g.color, fontSize: "0.75rem", fontWeight: 600, cursor: "pointer",
            padding: "4px 8px", borderRadius: 6,
          }}
        >
          جزئیات ↓
        </button>
      )}
    </Card>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color?: string }): JSX.Element {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "0.68rem", color: "#9ca3af" }}>{label}</div>
      <div style={{ fontWeight: 700, color: color ?? "#111", direction: "ltr", fontSize: "0.88rem" }}>{value}</div>
    </div>
  );
}

/* ---------- NEW: Company Card ---------- */
function CompanyCard({ c, onJump, totalProduced, contractProduced }: { c: CompanyTotals; onJump?: (company: CompanyCode) => void; totalProduced: number; contractProduced: number }): JSX.Element {
  const achColor = c.achievement >= 95 ? "#10b981" : c.achievement >= 80 ? "#f59e0b" : "#ef4444";
  const shareTotal = totalProduced > 0 ? (c.produced / totalProduced) * 100 : 0;
  const shareContract = c.isContract && contractProduced > 0 ? (c.produced / contractProduced) * 100 : null;
  return (
    <Card padding="lg" style={{ borderRight: `5px solid ${c.color}`, position: "relative", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{ width: 42, height: 42, borderRadius: 12, background: c.color + "14", color: c.color, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name={c.icon as any} size={20} />
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: "0.98rem", fontWeight: 700, color: "#111" }}>{c.label}</h3>
          <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: 2 }}>
            {toPersianDigits(c.lineCount.toString())} محصول
            <span style={{ marginRight: 6, background: c.color + "12", color: c.color, padding: "2px 7px", borderRadius: 10, fontWeight: 600, fontSize: "0.72rem" }}>
              {fmtPct(shareTotal)} از کل
            </span>
            {shareContract != null && (
              <span style={{ marginRight: 4, background: "#f3f4f6", color: "#374151", padding: "2px 7px", borderRadius: 10, fontSize: "0.70rem" }}>
                {fmtPct(shareContract)} از قراردادی
              </span>
            )}
          </div>
        </div>
        {!c.isContract && <span style={{ fontSize: "0.68rem", background: "#f0fdfa", color: "#0f766e", border: "1px solid #99f6e4", padding: "3px 8px", borderRadius: 20, fontWeight: 700 }}>داخلی</span>}
        {c.isContract && <span style={{ fontSize: "0.68rem", background: c.color + "12", color: c.color, border: `1px solid ${c.color}30`, padding: "3px 8px", borderRadius: 20, fontWeight: 700 }}>قراردادی</span>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
        <div style={{ background: "#f9fafb", borderRadius: 10, padding: "9px 10px", textAlign: "center" }}>
          <div style={{ fontSize: "0.68rem", color: "#6b7280" }}>برنامه</div>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(c.planned)}</div>
        </div>
        <div style={{ background: "#f9fafb", borderRadius: 10, padding: "9px 10px", textAlign: "center" }}>
          <div style={{ fontSize: "0.68rem", color: "#6b7280" }}>تولید</div>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(c.produced)}</div>
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "#6b7280", marginBottom: 4 }}>
          <span>تحقق</span><span style={{ color: achColor, fontWeight: 700 }}>{fmtPct(c.achievement)}</span>
        </div>
        <ProgressBar value={Math.min(c.achievement, 100)} tone={c.achievement >= 95 ? "green" : c.achievement >= 80 ? "amber" : "purple"} />
      </div>

      {/* Breakdown by product type */}
      <div style={{ borderTop: "1px solid #eef0f2", paddingTop: 10, flex: 1 }}>
        <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "#374151", marginBottom: 7 }}>ترکیب محصولات:</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {c.lines.map((l) => {
            const gm = GROUPS.find((g) => g.key === l.group)!;
            const pctOfCompany = c.produced > 0 ? (l.produced / c.produced) * 100 : 0;
            return (
              <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 8, background: "#f9fafb", borderRadius: 8, padding: "7px 8px" }}>
                <span style={{ width: 8, height: 8, borderRadius: 3, background: gm.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "#1f2937", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {l.product}
                  </div>
                  <div style={{ fontSize: "0.70rem", color: "#6b7280", display: "flex", gap: 6 }}>
                    <span style={{ background: gm.color + "14", color: gm.color, padding: "1px 6px", borderRadius: 8, fontWeight: 600 }}>{gm.label}</span>
                    <span>{STATUS_META[l.status].label}</span>
                  </div>
                </div>
                <div style={{ textAlign: "left", flexShrink: 0 }}>
                  <div style={{ fontSize: "0.80rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(l.produced)}</div>
                  <div style={{ fontSize: "0.68rem", color: c.color, fontWeight: 600, direction: "ltr" }}>{fmtPct(pctOfCompany)}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {onJump && (
        <button
          type="button"
          onClick={() => onJump(c.key)}
          style={{
            marginTop: 10, width: "100%", background: c.color + "0e", border: `1px solid ${c.color}22`,
            color: c.color, fontSize: "0.76rem", fontWeight: 700, cursor: "pointer",
            padding: "7px", borderRadius: 8,
          }}
        >
          نمایش در جدول ↓
        </button>
      )}
    </Card>
  );
}

/* ---------- Contract overview hero ---------- */
function ContractHero({ totalPlanned, totalProduced, contractPlanned, contractProduced, internalPlanned, internalProduced }: {
  totalPlanned: number; totalProduced: number;
  contractPlanned: number; contractProduced: number;
  internalPlanned: number; internalProduced: number;
}): JSX.Element {
  const contractPct = totalProduced > 0 ? (contractProduced / totalProduced) * 100 : 0;
  const internalPct = totalProduced > 0 ? (internalProduced / totalProduced) * 100 : 0;
  const contractAch = contractPlanned > 0 ? (contractProduced / contractPlanned) * 100 : 0;
  const internalAch = internalPlanned > 0 ? (internalProduced / internalPlanned) * 100 : 0;

  return (
    <Card padding="lg" style={{ border: "1px solid #e5e7eb", background: "linear-gradient(135deg, #f8fafc 0%, #ffffff 60%, #f0fdfa 100%)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: "#0f766e", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="briefcase" size={20} />
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: "1.02rem", fontWeight: 800, color: "#111" }}>سهم تولید قراردادی از کل تولید</h3>
          <div style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: 2 }}>تفکیک تولید داخلی روناک و ۴ شرکت قراردادی — تعداد، درصد و نوع محصول</div>
        </div>
        <div style={{ textAlign: "center", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: "8px 14px" }}>
          <div style={{ fontSize: "0.70rem", color: "#6b7280" }}>سهم قراردادی</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#6366f1", direction: "ltr" }}>{fmtPct(contractPct)}</div>
          <div style={{ fontSize: "0.70rem", color: "#9ca3af" }}>از کل تولید</div>
        </div>
      </div>

      {/* Stacked bar */}
      <div style={{ display: "flex", height: 18, borderRadius: 999, overflow: "hidden", background: "#e5e7eb", marginBottom: 14, border: "1px solid #e5e7eb" }}>
        <div style={{ width: `${internalPct}%`, background: "#0f766e", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: "0.68rem", fontWeight: 700, minWidth: internalPct > 12 ? undefined : 0 }}>
          {internalPct > 12 ? toPersianDigits(internalPct.toFixed(0) + "%") : ""}
        </div>
        <div style={{ width: `${contractPct}%`, background: "linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899, #f97316)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: "0.68rem", fontWeight: 700 }}>
          {contractPct > 12 ? toPersianDigits(contractPct.toFixed(0) + "%") : ""}
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, justifyContent: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.74rem", color: "#374151" }}><span style={{ width: 12, height: 12, borderRadius: 3, background: "#0f766e" }} />روناک داخلی ({fmtPct(internalPct)})</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.74rem", color: "#374151" }}><span style={{ width: 12, height: 12, borderRadius: 3, background: "linear-gradient(90deg,#6366f1,#ec4899)" }} />قراردادی ({fmtPct(contractPct)})</span>
      </div>

      {/* Two big comparison panels */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
        {/* Internal */}
        <div style={{ background: "#fff", border: "1.5px solid #ccfbf1", borderRadius: 14, padding: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ width: 32, height: 32, borderRadius: 9, background: "#0f766e15", color: "#0f766e", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="building" size={16} /></span>
            <strong style={{ fontSize: "0.92rem", color: "#0f766e" }}>تولید داخلی — روناک</strong>
            <span style={{ marginRight: "auto", fontSize: "0.72rem", background: "#f0fdfa", color: "#0f766e", padding: "3px 8px", borderRadius: 20, fontWeight: 700 }}>{fmtPct(internalPct)} از کل</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ background: "#f8fafc", borderRadius: 10, padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "0.68rem", color: "#6b7280" }}>برنامه</div>
              <div style={{ fontSize: "1rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(internalPlanned)}</div>
            </div>
            <div style={{ background: "#f0fdfa", borderRadius: 10, padding: "10px", textAlign: "center", border: "1px solid #ccfbf1" }}>
              <div style={{ fontSize: "0.68rem", color: "#0f766e" }}>تولید</div>
              <div style={{ fontSize: "1rem", fontWeight: 800, color: "#0f766e", direction: "ltr" }}>{fmtNum(internalProduced)}</div>
            </div>
          </div>
          <div style={{ marginTop: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "#6b7280", marginBottom: 4 }}><span>تحقق</span><span style={{ color: internalAch >= 90 ? "#10b981" : internalAch >= 75 ? "#f59e0b" : "#ef4444", fontWeight: 700 }}>{fmtPct(internalAch)}</span></div>
            <ProgressBar value={Math.min(internalAch, 100)} tone={internalAch >= 90 ? "green" : internalAch >= 75 ? "amber" : "purple"} />
          </div>
        </div>

        {/* Contract total */}
        <div style={{ background: "#fff", border: "1.5px solid #ddd6fe", borderRadius: 14, padding: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ width: 32, height: 32, borderRadius: 9, background: "#6366f115", color: "#6366f1", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="users" size={16} /></span>
            <strong style={{ fontSize: "0.92rem", color: "#6366f1" }}>تولید قراردادی — ۴ شرکت</strong>
            <span style={{ marginRight: "auto", fontSize: "0.72rem", background: "#eef2ff", color: "#6366f1", padding: "3px 8px", borderRadius: 20, fontWeight: 700 }}>{fmtPct(contractPct)} از کل</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ background: "#f8fafc", borderRadius: 10, padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "0.68rem", color: "#6b7280" }}>برنامه</div>
              <div style={{ fontSize: "1rem", fontWeight: 700, color: "#111", direction: "ltr" }}>{fmtNum(contractPlanned)}</div>
            </div>
            <div style={{ background: "#eef2ff", borderRadius: 10, padding: "10px", textAlign: "center", border: "1px solid #ddd6fe" }}>
              <div style={{ fontSize: "0.68rem", color: "#6366f1" }}>تولید</div>
              <div style={{ fontSize: "1rem", fontWeight: 800, color: "#6366f1", direction: "ltr" }}>{fmtNum(contractProduced)}</div>
            </div>
          </div>
          <div style={{ marginTop: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "#6b7280", marginBottom: 4 }}><span>تحقق</span><span style={{ color: contractAch >= 90 ? "#10b981" : contractAch >= 75 ? "#f59e0b" : "#ef4444", fontWeight: 700 }}>{fmtPct(contractAch)}</span></div>
            <ProgressBar value={Math.min(contractAch, 100)} tone={contractAch >= 90 ? "green" : contractAch >= 75 ? "amber" : "purple"} />
          </div>
        </div>
      </div>

      {/* Overall total footer */}
      <div style={{ marginTop: 12, display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap", fontSize: "0.78rem", color: "#6b7280", background: "#f9fafb", borderRadius: 10, padding: "10px 14px", border: "1px solid #f3f4f6" }}>
        <span>کل برنامه: <strong style={{ color: "#111", direction: "ltr" }}>{fmtNum(totalPlanned)}</strong></span>
        <span style={{ color: "#d1d5db" }}>•</span>
        <span>کل تولید: <strong style={{ color: "#111", direction: "ltr" }}>{fmtNum(totalProduced)}</strong></span>
        <span style={{ color: "#d1d5db" }}>•</span>
        <span>تحقق کل: <strong style={{ color: totalProduced / Math.max(totalPlanned, 1) >= 0.9 ? "#10b981" : "#f59e0b" }}>{fmtPct(totalPlanned > 0 ? (totalProduced / totalPlanned) * 100 : 0)}</strong></span>
      </div>
    </Card>
  );
}

interface DonutDatum { key: string; label: string; value: number; color: string; subLabel?: string; }
function InteractiveDonutCard({
  title, subtitle, data, totalLabel, valueFormatter,
}: {
  title: string; subtitle?: string; data: DonutDatum[]; totalLabel: string;
  valueFormatter?: (v: number) => string;
}): JSX.Element {
  const [hover, setHover] = useState<string | null>(null);
  const size = 220;
  const stroke = 28;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const C = 2 * Math.PI * r;
  const f = valueFormatter ?? fmtNum;
  const positive = data.filter((d) => d.value > 0);
  const total = positive.reduce((s, d) => s + d.value, 0);

  let offset = 0;
  const gap = positive.length > 1 ? 1.5 : 0;
  const segments = positive.map((d) => {
    const frac = d.value / Math.max(total, 1);
    const dash = Math.max(frac * C - gap, 0.5);
    const seg = { ...d, dash, offset, pct: frac * 100 };
    offset += frac * C;
    return seg;
  });

  const hovered = hover ? segments.find((s) => s.key === hover) : null;
  const hoverValue = hovered ? f(hovered.value) : f(total);
  const hoverPct = hovered ? fmtPct(hovered.pct) : fmtPct(100);
  const hoverLabel = hovered ? hovered.label : "مجموع";
  const hoverSub = hovered?.subLabel ?? totalLabel;
  const hoverColor = hovered ? hovered.color : "#111";

  return (
    <Card padding="lg" style={{ position: "relative" }}>
      <div style={{ marginBottom: 10 }}>
        <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "#111" }}>{title}</h4>
        {subtitle && <div style={{ fontSize: "0.76rem", color: "#6b7280", marginTop: 2 }}>{subtitle}</div>}
      </div>
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
            <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f3f5" strokeWidth={stroke} />
            {segments.map((s) => {
              const isHover = hover === s.key;
              const isOther = hover && hover !== s.key;
              return (
                <circle
                  key={s.key}
                  cx={cx} cy={cy} r={r}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={isHover ? stroke + 6 : stroke}
                  strokeDasharray={`${s.dash} ${C - s.dash}`}
                  strokeDashoffset={C * 0.25 - s.offset}
                  strokeLinecap="butt"
                  opacity={isOther ? 0.35 : 1}
                  onMouseEnter={() => setHover(s.key)}
                  onMouseLeave={() => setHover(null)}
                  style={{ transition: "stroke-width 120ms ease, opacity 120ms ease", cursor: "pointer" }}
                />
              );
            })}
          </svg>
          <div style={{
            position: "absolute", inset: 0, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", pointerEvents: "none",
            padding: "0 12px", textAlign: "center",
          }}>
            <div style={{ fontSize: "0.68rem", color: "#6b7280", marginBottom: 2, maxWidth: "80%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{hoverLabel}</div>
            <div style={{ fontSize: "1.2rem", fontWeight: 800, color: hoverColor, direction: "ltr", lineHeight: 1.2 }}>{hoverValue}</div>
            <div style={{ fontSize: "0.72rem", color: hovered ? hoverColor : "#9ca3af", marginTop: 3, fontWeight: 600 }}>{hoverPct}</div>
            <div style={{ fontSize: "0.66rem", color: "#9ca3af", marginTop: 1 }}>{hoverSub}</div>
          </div>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 5, maxHeight: 220, overflowY: "auto" }}>
          {data.map((d) => {
            const pct = total > 0 ? (d.value / total) * 100 : 0;
            const isHover = hover === d.key;
            const isOther = hover && hover !== d.key;
            return (
              <div
                key={d.key}
                onMouseEnter={() => setHover(d.key)}
                onMouseLeave={() => setHover(null)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "6px 8px",
                  borderRadius: 8, cursor: "pointer",
                  background: isHover ? d.color + "12" : "transparent",
                  opacity: isOther ? 0.5 : 1,
                  transition: "all 120ms ease",
                }}
              >
                <span style={{ width: 10, height: 10, borderRadius: 3, background: d.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.8rem", color: "#374151", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{d.label}</div>
                  {d.subLabel && <div style={{ fontSize: "0.66rem", color: "#9ca3af" }}>{d.subLabel}</div>}
                </div>
                <span style={{ fontSize: "0.8rem", fontWeight: 700, color: d.color, direction: "ltr" }}>{f(d.value)}</span>
                <span style={{ fontSize: "0.68rem", color: "#9ca3af", direction: "ltr", width: 38, textAlign: "left" }}>{fmtPct(pct)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

export function ProductionPlanningDashboardPage(): JSX.Element {
  const [companyFilter, setCompanyFilter] = useState<CompanyCode | "all">("all");
  const [groupFilter, setGroupFilter] = useState<ProductGroup | "all">("all");
  const [statusFilter, setStatusFilter] = useState<LineStatus | "all">("all");
  const [editMode, setEditMode] = useState(false);
  const [draftPlanned, setDraftPlanned] = useState<Record<string, number>>({});
  const { has, permissions } = usePermissions();
  const { session } = useAuth();

  const canManage = useMemo(() => {
    if (!session) return false;
    if (session.user.role === "Superadmin") return true;
    if (permissions.includes("*")) return true;
    if (has("production.manage")) return true;
    if (has(["settings.manage", "tenant.manage", "user.manage", "role.manage"])) return true;
    return false;
  }, [session, permissions, has]);

  const [lines, setLines] = useState<ProductionLine[]>(DEMO_LINES);

  const groupTotals: GroupTotals[] = useMemo(() => {
    return GROUPS.map((gm) => {
      const gl = lines.filter((l) => l.group === gm.key);
      const planned = gl.reduce((s, l) => s + l.planned, 0);
      const produced = gl.reduce((s, l) => s + l.produced, 0);
      const achievement = planned > 0 ? (produced / planned) * 100 : 0;
      const totalStopMin: number | null = null;
      const weightedWaste: number | null = null;
      const weightedOee: number | null = null;
      const runningCount = gl.filter((l) => l.status === "running").length;
      const issueCount = gl.filter((l) => l.status === "stopped" || l.status === "maintenance").length;
      return {
        key: gm.key, label: gm.label, color: gm.color, icon: gm.icon,
        planned, produced, achievement, weightedOee, totalStopMin, weightedWaste,
        lineCount: gl.length, runningCount, issueCount, lines: gl,
      };
    });
  }, [lines]);

  const companyTotals: CompanyTotals[] = useMemo(() => {
    const totalProduced = lines.reduce((s, l) => s + l.produced, 0);
    const contractProduced = lines.filter(l => l.company !== "ronak_internal").reduce((s, l) => s + l.produced, 0);
    return COMPANIES.map((cm) => {
      const cl = lines.filter((l) => l.company === cm.key);
      const planned = cl.reduce((s, l) => s + l.planned, 0);
      const produced = cl.reduce((s, l) => s + l.produced, 0);
      const achievement = planned > 0 ? (produced / planned) * 100 : 0;
      const shareOfTotal = totalProduced > 0 ? (produced / totalProduced) * 100 : 0;
      const shareOfContract = cm.isContract && contractProduced > 0 ? (produced / contractProduced) * 100 : null;
      return {
        key: cm.key, label: cm.label, color: cm.color, icon: cm.icon, isContract: cm.isContract,
        planned, produced, achievement, shareOfTotal, shareOfContract,
        lineCount: cl.length, lines: cl,
      };
    });
  }, [lines]);

  const overall = useMemo(() => {
    const totalPlanned = lines.reduce((s, l) => s + l.planned, 0);
    const totalProduced = lines.reduce((s, l) => s + l.produced, 0);
    const contractLines = lines.filter(l => l.company !== "ronak_internal");
    const contractPlanned = contractLines.reduce((s, l) => s + l.planned, 0);
    const contractProduced = contractLines.reduce((s, l) => s + l.produced, 0);
    const internalLines = lines.filter(l => l.company === "ronak_internal");
    const internalPlanned = internalLines.reduce((s, l) => s + l.planned, 0);
    const internalProduced = internalLines.reduce((s, l) => s + l.produced, 0);
    return { totalPlanned, totalProduced, contractPlanned, contractProduced, internalPlanned, internalProduced };
  }, [lines]);

  const visible = useMemo(() => {
    let v = lines;
    if (companyFilter !== "all") v = v.filter((l) => l.company === companyFilter);
    if (groupFilter !== "all") v = v.filter((l) => l.group === groupFilter);
    if (statusFilter !== "all") v = v.filter((l) => l.status === statusFilter);
    return v;
  }, [lines, companyFilter, groupFilter, statusFilter]);

  const visibleTotals = useMemo(() => {
    const planned = visible.reduce((s, l) => s + l.planned, 0);
    const produced = visible.reduce((s, l) => s + l.produced, 0);
    const achievement = planned > 0 ? (produced / planned) * 100 : 0;
    return { planned, produced, achievement, totalStopMin: null, weightedWaste: null, avgOee: null };
  }, [visible]);

  const statusFilters: { key: "all" | LineStatus; label: string }[] = [
    { key: "all", label: "همه" },
    { key: "running", label: "در حال تولید" },
    { key: "changeover", label: "تعویض" },
    { key: "maintenance", label: "تعمیرات" },
    { key: "stopped", label: "متوقف" },
  ];

  return (
    <div className="page">
      <SectionHeader
        title="داشبورد برنامه‌ریزی تولید"
        subtitle={
          canManage
            ? `نمای لحظه‌ای گروه‌های محصول و شرکت‌های قراردادی + ویرایش برنامه (دسترسی: ${session?.user.role ?? "?"})`
            : `نمای لحظه‌ای گروه‌های محصول و شرکت‌های قراردادی (فقط مشاهده — دسترسی: ${session?.user.role ?? "?"})`
        }
        actions={
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {canManage ? (
              <Button
                variant={editMode ? "primary" : "secondary"}
                icon={editMode ? "check" : "edit"}
                onClick={() => {
                  if (editMode) {
                    setLines((cur) => cur.map((l) =>
                      draftPlanned[l.id] != null && draftPlanned[l.id] >= 0
                        ? { ...l, planned: Math.round(draftPlanned[l.id]) } : l,
                    ));
                    setDraftPlanned({});
                  }
                  setEditMode(!editMode);
                }}
              >
                {editMode ? "ذخیره برنامه" : "ویرایش برنامه"}
              </Button>
            ) : (
              <span style={{ fontSize: "0.78rem", color: "#6b7280", background: "#f3f4f6", padding: "6px 12px", borderRadius: 8, display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Icon name="lock" size={13} /> فقط مشاهده
              </span>
            )}
            <Button variant="ghost" icon="refresh" onClick={() => window.location.reload()}>به‌روزرسانی</Button>
            <Button icon="download">خروجی گزارش</Button>
          </div>
        }
      />

      {/* Hero: Contract vs Internal share */}
      <ContractHero
        totalPlanned={overall.totalPlanned}
        totalProduced={overall.totalProduced}
        contractPlanned={overall.contractPlanned}
        contractProduced={overall.contractProduced}
        internalPlanned={overall.internalPlanned}
        internalProduced={overall.internalProduced}
      />

      {/* Company summary cards: 4 contract + internal */}
      <div style={{ marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ width: 6, height: 22, background: "#6366f1", borderRadius: 3 }} />
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>تولید به تفکیک شرکت قراردادی</h3>
          <span style={{ fontSize: "0.74rem", color: "#6b7280", background: "#f3f4f6", padding: "3px 9px", borderRadius: 20 }}>
            هر کارت = یک شرکت — تعداد، درصد و نوع محصول (قرص/آمپول/ویال...)
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
          {companyTotals.map((c) => (
            <CompanyCard
              key={c.key}
              c={c}
              totalProduced={overall.totalProduced}
              contractProduced={overall.contractProduced}
              onJump={(k) => { setCompanyFilter(k); document.getElementById("comparison-table")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}
            />
          ))}
        </div>
      </div>

      {/* Product group summary cards (5 groups) */}
      <div style={{ marginTop: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ width: 6, height: 22, background: "#374151", borderRadius: 3 }} />
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>خلاصه گروه‌های محصول</h3>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
          {groupTotals.map((g) => (
            <GroupCard key={g.key} g={g} onJump={(k) => { setGroupFilter(filter => filter === k ? "all" as any : k); }} />
          ))}
        </div>
      </div>

      {/* Filters: Company / Group / Status */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: "12px 14px", marginTop: 14 }}>
        {/* Company filter */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: "0.78rem", color: "#6b7280", marginLeft: 6, fontWeight: 600, minWidth: 90 }}>شرکت:</span>
          <button
            type="button"
            onClick={() => setCompanyFilter("all")}
            style={{
              padding: "5px 12px", borderRadius: 16, border: companyFilter === "all" ? "none" : "1px solid #e5e7eb",
              background: companyFilter === "all" ? "#374151" : "#fff", color: companyFilter === "all" ? "#fff" : "#374151",
              cursor: "pointer", fontSize: "0.78rem", fontWeight: 600,
            }}
          >همه شرکت‌ها</button>
          {COMPANIES.map((cm) => (
            <button
              key={cm.key}
              type="button"
              onClick={() => setCompanyFilter(companyFilter === cm.key ? "all" : cm.key)}
              style={{
                padding: "5px 12px", borderRadius: 16,
                border: companyFilter === cm.key ? "none" : "1px solid #e5e7eb",
                background: companyFilter === cm.key ? cm.color : "#fff",
                color: companyFilter === cm.key ? "#fff" : "#374151",
                cursor: "pointer", fontSize: "0.78rem", fontWeight: 600,
                display: "inline-flex", alignItems: "center", gap: 6,
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: companyFilter === cm.key ? "#fff" : cm.color }} />
              {cm.label}
              {!cm.isContract && <span style={{ fontSize: "0.65rem", opacity: 0.8 }}>(داخلی)</span>}
            </button>
          ))}
        </div>

        {/* Group filter chips */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: "0.78rem", color: "#6b7280", marginLeft: 6, fontWeight: 600, minWidth: 90 }}>گروه محصول:</span>
          <button
            type="button"
            onClick={() => setGroupFilter("all")}
            style={{
              padding: "5px 12px", borderRadius: 16, border: groupFilter === "all" ? "none" : "1px solid #e5e7eb",
              background: groupFilter === "all" ? "#374151" : "#fff", color: groupFilter === "all" ? "#fff" : "#374151",
              cursor: "pointer", fontSize: "0.78rem", fontWeight: 600,
            }}
          >همه گروه‌ها</button>
          {GROUPS.map((gm) => (
            <button
              key={gm.key}
              type="button"
              onClick={() => setGroupFilter(groupFilter === gm.key ? "all" : gm.key)}
              style={{
                padding: "5px 12px", borderRadius: 16,
                border: groupFilter === gm.key ? "none" : "1px solid #e5e7eb",
                background: groupFilter === gm.key ? gm.color : "#fff",
                color: groupFilter === gm.key ? "#fff" : "#374151",
                cursor: "pointer", fontSize: "0.78rem", fontWeight: 600,
              }}
            >{gm.label}</button>
          ))}
        </div>

        {/* Status filter chips */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.78rem", color: "#6b7280", marginLeft: 6, fontWeight: 600, minWidth: 90 }}>وضعیت:</span>
          {statusFilters.map((f) => {
            const active = statusFilter === f.key;
            const meta = f.key !== "all" ? STATUS_META[f.key as LineStatus] : null;
            return (
              <button
                key={f.key} type="button" onClick={() => setStatusFilter(f.key as any)}
                style={{
                  padding: "5px 12px", borderRadius: 16,
                  border: active ? "none" : "1px solid #e5e7eb",
                  background: active ? (meta?.color ?? "#2878ff") : "#fff",
                  color: active ? "#fff" : "#374151", cursor: "pointer",
                  fontSize: "0.78rem", fontWeight: active ? 600 : 500,
                  display: "inline-flex", alignItems: "center", gap: 5,
                }}
              >
                {meta ? <span style={{ width: 7, height: 7, borderRadius: "50%", background: active ? "#fff" : meta.color }} /> : null}
                {f.label}
              </button>
            );
          })}
          {(companyFilter !== "all" || groupFilter !== "all" || statusFilter !== "all") && (
            <button
              type="button"
              onClick={() => { setCompanyFilter("all"); setGroupFilter("all"); setStatusFilter("all"); }}
              style={{ marginRight: 8, padding: "5px 12px", borderRadius: 16, border: "1px dashed #d1d5db", background: "#fff", color: "#6b7280", cursor: "pointer", fontSize: "0.76rem" }}
            >
              پاک کردن فیلترها
            </button>
          )}
        </div>
      </div>

      {/* Central comparison table */}
      <Card padding="none" style={{ marginTop: 12 }} id="comparison-table">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem", minWidth: 1050 }}>
            <thead>
              <tr style={{ background: "#f8fafb", borderBottom: "2px solid #e5e7eb" }}>
                <th style={thStyle}>شرکت</th>
                <th style={thStyle}>گروه محصول</th>
                <th style={thStyle}>خط تولید</th>
                <th style={thStyle}>محصول</th>
                <th style={thStyle}>وضعیت</th>
                <th style={thStyleNum}>برنامه</th>
                <th style={thStyleNum}>تولید</th>
                <th style={thStyleNum}>تحقق</th>
                <th style={thStyleNum}>سهم از کل</th>
                <th style={thStyleNum}>سرعت</th>
                <th style={thStyleNum}>توقف</th>
                <th style={thStyleNum}>ضایعات</th>
                <th style={thStyleNum}>OEE</th>
                <th style={thStyleNum}>شیفت</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((line, idx) => {
                const meta = STATUS_META[line.status];
                const gm = GROUPS.find((g) => g.key === line.group)!;
                const cm = COMPANIES.find((c) => c.key === line.company)!;
                const ach = line.planned > 0 ? (line.produced / line.planned) * 100 : 0;
                const shareOfTotal = overall.totalProduced > 0 ? (line.produced / overall.totalProduced) * 100 : 0;
                const achColor = ach >= 95 ? "#10b981" : ach >= 80 ? "#f59e0b" : "#ef4444";
                const oeeColor = (line.oeePct ?? 0) >= 85 ? "#10b981" : (line.oeePct ?? 0) >= 70 ? "#f59e0b" : "#ef4444";
                const wasteColor = (line.wastePct ?? 0) > 2.5 ? "#ef4444" : (line.wastePct ?? 0) > 1.5 ? "#f59e0b" : "#10b981";
                const stopColor = (line.stopMinutes ?? 0) > 120 ? "#ef4444" : (line.stopMinutes ?? 0) > 60 ? "#f59e0b" : "#10b981";
                const speedRatio = line.nominalSpeed > 0 ? line.actualSpeed / line.nominalSpeed : 0;
                const speedColor = speedRatio >= 0.95 ? "#10b981" : speedRatio >= 0.8 ? "#f59e0b" : "#ef4444";
                return (
                  <tr key={line.id} style={{ borderBottom: "1px solid #f0f2f4", background: idx % 2 === 0 ? "#fff" : "#fafbfc" }}>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px", borderRadius: 12, background: cm.color + "15", color: cm.color, fontSize: "0.74rem", fontWeight: 700 }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: cm.color }} />
                        {cm.label}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px", borderRadius: 12, background: gm.color + "15", color: gm.color, fontSize: "0.74rem", fontWeight: 600 }}>
                        {gm.label}
                      </span>
                    </td>
                    <td style={tdStyle}><strong style={{ color: "#111" }}>{line.name}</strong></td>
                    <td style={tdStyle}>{line.product}</td>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: meta.color, fontWeight: 600 }}>
                        <span style={{ width: 8, height: 8, borderRadius: "50%", background: meta.dot, boxShadow: line.status === "running" ? `0 0 0 3px ${meta.dot}30` : "none" }} />
                        {meta.label}
                      </span>
                    </td>
                    <td style={tdStyleNum}>
                      {editMode && canManage ? (
                        <input type="number" min={0} defaultValue={line.planned}
                          onChange={(e) => setDraftPlanned((cur) => ({ ...cur, [line.id]: Number(e.target.value) || 0 }))}
                          style={{ width: 88, padding: "4px 6px", border: "1px solid #2878ff", borderRadius: 6, fontSize: "0.82rem", textAlign: "center", fontFamily: "inherit" }} />
                      ) : fmtNum(line.planned)}
                    </td>
                    <td style={tdStyleNum}>{fmtNum(line.produced)}</td>
                    <td style={tdStyleNum}><span style={{ color: achColor, fontWeight: 700 }}>{fmtPct(ach)}</span></td>
                    <td style={tdStyleNum}><span style={{ color: cm.color, fontWeight: 600 }}>{fmtPct(shareOfTotal)}</span></td>
                    <td style={tdStyleNum}>
                      <span style={{ color: speedColor }}>{fmtNum(line.actualSpeed)}</span>
                      <span style={{ color: "#9ca3af", fontSize: "0.72rem" }}> / {fmtNum(line.nominalSpeed)}</span>
                    </td>
                    <td style={tdStyleNum}><span style={{ color: line.stopMinutes == null ? "#cbd5e1" : stopColor }}>{fmtOptDur(line.stopMinutes)}</span></td>
                    <td style={tdStyleNum}><span style={{ color: line.wastePct == null ? "#cbd5e1" : wasteColor }}>{fmtOptPct(line.wastePct)}</span></td>
                    <td style={tdStyleNum}><span style={{ color: line.oeePct == null ? "#cbd5e1" : oeeColor, fontWeight: line.oeePct == null ? 400 : 700 }}>{fmtOptPct(line.oeePct)}</span></td>
                    <td style={tdStyleNum}>{toPersianDigits(line.shift.toString())}</td>
                  </tr>
                );
              })}
            </tbody>
            {visible.length > 0 && (
              <tfoot>
                <tr style={{ background: "#f0f6ff", borderTop: "2px solid #bfdbfe", fontWeight: 700 }}>
                  <td style={{ ...tdStyle, padding: "10px 12px" }} colSpan={5}>جمع فیلتر شده</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtNum(visibleTotals.planned)}</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtNum(visibleTotals.produced)}</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>
                    <span style={{ color: visibleTotals.achievement >= 90 ? "#10b981" : visibleTotals.achievement >= 75 ? "#f59e0b" : "#ef4444" }}>
                      {fmtPct(visibleTotals.achievement)}
                    </span>
                  </td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>
                    <span style={{ color: "#6366f1" }}>{fmtPct(overall.totalProduced > 0 ? (visibleTotals.produced / overall.totalProduced) * 100 : 0)}</span>
                  </td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>—</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px", color: "#cbd5e1" }}>—</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px", color: "#cbd5e1" }}>—</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px", color: "#cbd5e1" }}>—</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>—</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </Card>

      {/* Interactive Donut charts section */}
      <div style={{ marginTop: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ width: 6, height: 22, background: "#374151", borderRadius: 3 }} />
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>سهم تولید به تفکیک</h3>
        </div>
        {/* First row: Company share */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14 }}>
          <InteractiveDonutCard
            title="سهم شرکت‌ها از تولید واقعی"
            subtitle="هر تکه = یک شرکت — ماوس را نگه دارید تا مقدار و درصد هر شرکت را ببینید"
            data={visible.length > 0
              ? (() => {
                  const map = new Map<CompanyCode, number>();
                  visible.forEach(l => map.set(l.company, (map.get(l.company) ?? 0) + l.produced));
                  return Array.from(map.entries()).map(([k, v]) => {
                    const cm = COMPANIES.find(c => c.key === k)!;
                    const count = visible.filter(l => l.company === k).length;
                    return { key: k, label: cm.label, subLabel: `${toPersianDigits(count.toString())} محصول • ${COMPANIES.find(c => c.key === k)!.isContract ? "قراردادی" : "داخلی"}`, value: v, color: cm.color };
                  });
                })()
              : COMPANIES.map(cm => ({ key: cm.key, label: cm.label, subLabel: cm.isContract ? "قراردادی" : "داخلی", value: 0, color: cm.color }))}
            totalLabel="عدد"
          />
          <InteractiveDonutCard
            title="سهم شرکت‌ها از برنامه تولید"
            subtitle="سهم برنامه هر شرکت از کل برنامه فیلتر شده"
            data={visible.length > 0
              ? (() => {
                  const map = new Map<CompanyCode, number>();
                  visible.forEach(l => map.set(l.company, (map.get(l.company) ?? 0) + l.planned));
                  return Array.from(map.entries()).map(([k, v]) => {
                    const cm = COMPANIES.find(c => c.key === k)!;
                    return { key: k, label: cm.label, subLabel: cm.isContract ? "قراردادی" : "داخلی", value: v, color: cm.color };
                  });
                })()
              : COMPANIES.map(cm => ({ key: cm.key, label: cm.label, subLabel: cm.isContract ? "قراردادی" : "داخلی", value: 0, color: cm.color }))}
            totalLabel="عدد"
          />
        </div>
        {/* Second row: Product share */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14, marginTop: 14 }}>
          <InteractiveDonutCard
            title="تولید واقعی به تفکیک محصول"
            subtitle="ماوس روی هر تکه نگه دارید تا نام محصول، شرکت و مقدار تولیدش را ببینید"
            data={visible.map((l) => {
              const cm = COMPANIES.find((c) => c.key === l.company)!;
              return { key: l.id, label: l.product, subLabel: `${cm.label} • ${GROUPS.find(g=>g.key===l.group)!.label}`, value: l.produced, color: cm.color };
            })}
            totalLabel="عدد"
          />
          <InteractiveDonutCard
            title="برنامه تولید به تفکیک محصول"
            subtitle="سهم برنامه هر محصول از کل برنامه"
            data={visible.map((l) => {
              const cm = COMPANIES.find((c) => c.key === l.company)!;
              return { key: l.id, label: l.product, subLabel: `${cm.label} • ${GROUPS.find(g=>g.key===l.group)!.label}`, value: l.planned, color: cm.color };
            })}
            totalLabel="عدد"
          />
        </div>
      </div>

      {visible.length === 0 ? (
        <Card padding="lg">
          <div style={{ textAlign: "center", color: "#6b7280", padding: "30px 0" }}>
            <Icon name="filter" size={28} />
            <p style={{ marginTop: 8 }}>هیچ خطی با این فیلتر نمایش داده نمی‌شود.</p>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

export default ProductionPlanningDashboardPage;
