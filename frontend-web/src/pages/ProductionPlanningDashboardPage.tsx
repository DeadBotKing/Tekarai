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

interface ProductionLine {
  id: string;
  name: string;
  product: string;
  group: ProductGroup;
  status: LineStatus;
  planned: number;
  produced: number;
  nominalSpeed: number;
  actualSpeed: number;
  stopMinutes: number;
  wastePct: number;
  oeePct: number;
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
  icon: "pill" | "droplet" | "flask" | "package" | "syringe";
}

const GROUPS: GroupMeta[] = [
  { key: "tablets_capsules", label: "قرص و کپسول",      short: "T/C", color: "#0ea5e9", icon: "target" },
  { key: "softgel",          label: "سافت‌ژل",          short: "S/G", color: "#8b5cf6", icon: "layers" },
  { key: "vials_lyo",        label: "ویال و لیوفیلیزه",  short: "V/L", color: "#10b981", icon: "activity" },
  { key: "powder_filling",   label: "پودر فیلینگ",      short: "PWD", color: "#f59e0b", icon: "briefcase" },
  { key: "syringes_ampoules",label: "سرنگ و آمپول",     short: "S/A", color: "#ef4444", icon: "bell" },
];

const fmtNum = (n: number): string => toPersianDigits(n.toLocaleString("en-US"));
const fmtPct = (n: number): string => toPersianDigits(n.toFixed(1) + "%");
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

/** Demo production lines grouped by product family. */
const DEMO_LINES: ProductionLine[] = [
  // قرص و کپسول
  { id: "L02", name: "خط ۰۲ – قرص‌زنی",          product: "قرص 500mg",     group: "tablets_capsules",   status: "running",     planned: 80000, produced: 79200, nominalSpeed: 1200, actualSpeed: 1180, stopMinutes: 18,  wastePct: 0.8, oeePct: 91, shift: 2, lastUpdated: "14:43" },
  { id: "L06", name: "خط ۰۶ – کپسول‌زنی",        product: "کپسول 250mg",   group: "tablets_capsules",   status: "stopped",     planned: 45000, produced: 28700, nominalSpeed: 800,  actualSpeed: 0,    stopMinutes: 210, wastePct: 3.1, oeePct: 43, shift: 1, lastUpdated: "11:05" },
  // سافت‌ژل
  { id: "L08", name: "خط ۰۸ – سافت‌ژل",          product: "سافت‌ژل ۵۰۰mg", group: "softgel",            status: "running",     planned: 35000, produced: 31200, nominalSpeed: 700,  actualSpeed: 660,  stopMinutes: 35,  wastePct: 1.4, oeePct: 84, shift: 2, lastUpdated: "14:45" },
  // ویال و لیوفیلیزه
  { id: "L04", name: "خط ۰۴ – ویال پرکن",        product: "ویال 10ml",     group: "vials_lyo",          status: "running",     planned: 20000, produced: 16800, nominalSpeed: 400,  actualSpeed: 360,  stopMinutes: 75,  wastePct: 2.8, oeePct: 66, shift: 2, lastUpdated: "14:40" },
  { id: "L09", name: "خط ۰۹ – لیوفیلیزه",        product: "ویال لیو ۵۰۰mg",group: "vials_lyo",          status: "changeover",  planned: 12000, produced: 7400,  nominalSpeed: 240,  actualSpeed: 220,  stopMinutes: 115, wastePct: 2.1, oeePct: 55, shift: 2, lastUpdated: "14:25" },
  // پودر فیلینگ
  { id: "L10", name: "خط ۱۰ – پودر فیلینگ",      product: "پودر ویال",     group: "powder_filling",     status: "running",     planned: 15000, produced: 13800, nominalSpeed: 300,  actualSpeed: 290,  stopMinutes: 28,  wastePct: 0.9, oeePct: 88, shift: 2, lastUpdated: "14:44" },
  // سرنگ و آمپول
  { id: "L01", name: "خط ۰۱ – آمپول پرکن",       product: "آمپول 2ml",     group: "syringes_ampoules",  status: "running",     planned: 50000, produced: 47500, nominalSpeed: 1000, actualSpeed: 950,  stopMinutes: 42,  wastePct: 1.2, oeePct: 82, shift: 2, lastUpdated: "14:42" },
  { id: "L07", name: "خط ۰۷ – سرنگ پرکن",        product: "سرنگ 5ml",      group: "syringes_ampoules",  status: "maintenance", planned: 22000, produced: 10100, nominalSpeed: 440,  actualSpeed: 0,    stopMinutes: 185, wastePct: 0,   oeePct: 32, shift: 2, lastUpdated: "11:30" },
];

interface GroupTotals {
  key: ProductGroup;
  label: string;
  color: string;
  icon: GroupMeta["icon"];
  planned: number;
  produced: number;
  achievement: number;
  weightedOee: number;
  totalStopMin: number;
  weightedWaste: number;
  lineCount: number;
  runningCount: number;
  issueCount: number;
  lines: ProductionLine[];
}

interface LineCardProps { line: ProductionLine; }
function LineCard({ line }: LineCardProps): JSX.Element {
  const meta = STATUS_META[line.status];
  const achievement = line.planned > 0 ? (line.produced / line.planned) * 100 : 0;
  const speedAchievement = line.nominalSpeed > 0 ? (line.actualSpeed / line.nominalSpeed) * 100 : 0;
  const achievementColor = achievement >= 95 ? "#10b981" : achievement >= 80 ? "#f59e0b" : "#ef4444";
  const oeeColor = line.oeePct >= 85 ? "#10b981" : line.oeePct >= 70 ? "#f59e0b" : "#ef4444";

  return (
    <Card padding="lg" className="prod-line-card" style={{ borderTop: `4px solid ${meta.color}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>{line.name}</h3>
          <div style={{ fontSize: "0.82rem", color: "#6b7280", marginTop: 3 }}>محصول: <strong style={{ color: "#374151" }}>{line.product}</strong></div>
        </div>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: meta.color + "18", color: meta.color, padding: "4px 10px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 600 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: meta.dot, boxShadow: line.status === "running" ? `0 0 0 3px ${meta.dot}30` : "none" }} />
          {meta.label}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
        <Stat label="برنامه" value={fmtNum(line.planned)} />
        <Stat label="تولید" value={fmtNum(line.produced)} />
        <Stat label="تحقق" value={fmtPct(achievement)} valueColor={achievementColor} />
      </div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.74rem", color: "#6b7280", marginBottom: 4 }}>
          <span>پیشرفت تولید</span>
          <span style={{ color: achievementColor, fontWeight: 600 }}>{fmtPct(achievement)}</span>
        </div>
        <ProgressBar value={Math.min(achievement, 100)} tone={achievement >= 95 ? "green" : achievement >= 80 ? "amber" : "purple"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 14px", fontSize: "0.82rem", borderTop: "1px solid #eef0f2", paddingTop: 12 }}>
        <DetailRow label="سرعت اسمی" value={fmtNum(line.nominalSpeed) + " عدد/h"} />
        <DetailRow label="سرعت واقعی" value={fmtNum(line.actualSpeed) + " عدد/h"} valueColor={speedAchievement >= 95 ? "#10b981" : speedAchievement >= 80 ? "#f59e0b" : "#ef4444"} />
        <DetailRow label="توقف" value={fmtDur(line.stopMinutes)} valueColor={line.stopMinutes > 120 ? "#ef4444" : line.stopMinutes > 60 ? "#f59e0b" : undefined} />
        <DetailRow label="ضایعات" value={fmtPct(line.wastePct)} valueColor={line.wastePct > 2.5 ? "#ef4444" : line.wastePct > 1.5 ? "#f59e0b" : "#10b981"} />
        <DetailRow label="OEE" value={fmtPct(line.oeePct)} valueColor={oeeColor} />
        <DetailRow label="شیفت" value={toPersianDigits(line.shift.toString())} />
      </div>
      <div style={{ marginTop: 10, fontSize: "0.72rem", color: "#9ca3af", textAlign: "left" }}>آخرین به‌روزرسانی: {toPersianDigits(line.lastUpdated)}</div>
    </Card>
  );
}

function Stat({ label, value, valueColor }: { label: string; value: string; valueColor?: string }): JSX.Element {
  return (
    <div style={{ background: "#f9fafb", borderRadius: 10, padding: "10px 12px", textAlign: "center" }}>
      <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: "1.15rem", fontWeight: 700, color: valueColor ?? "#111", direction: "ltr" }}>{value}</div>
    </div>
  );
}

function DetailRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }): JSX.Element {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 0" }}>
      <span style={{ color: "#6b7280" }}>{label}</span>
      <span style={{ fontWeight: 600, color: valueColor ?? "#1f2937", direction: "ltr" }}>{value}</span>
    </div>
  );
}

/** Big product-group summary card (one per product family). */
function GroupCard({ g, onJump }: { g: GroupTotals; onJump?: (group: ProductGroup) => void }): JSX.Element {
  const achColor = g.achievement >= 95 ? "#10b981" : g.achievement >= 80 ? "#f59e0b" : "#ef4444";
  const oeeColor = g.weightedOee >= 85 ? "#10b981" : g.weightedOee >= 70 ? "#f59e0b" : "#ef4444";
  const wasteColor = g.weightedWaste > 2.5 ? "#ef4444" : g.weightedWaste > 1.5 ? "#f59e0b" : "#10b981";
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
        <ProgressBar value={Math.min(g.achievement, 100)} tone={g.achievement >= 95 ? "green" : g.achievement >= 80 ? "amber" : "orange"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: "0.78rem", borderTop: "1px solid #eef0f2", paddingTop: 10 }}>
        <MiniStat label="OEE" value={fmtPct(g.weightedOee)} color={oeeColor} />
        <MiniStat label="توقف" value={fmtDur(g.totalStopMin)} color={g.totalStopMin > 120 ? "#ef4444" : "#6b7280"} />
        <MiniStat label="ضایعات" value={fmtPct(g.weightedWaste)} color={wasteColor} />
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

interface DonutDatum { key: string; label: string; value: number; color: string; }
function InteractiveDonutCard({
  title, subtitle, data, totalLabel, valueFormatter, dimmed = false,
}: {
  title: string; subtitle?: string; data: DonutDatum[]; totalLabel: string;
  valueFormatter?: (v: number) => string; dimmed?: boolean;
}): JSX.Element {
  const [hover, setHover] = useState<string | null>(null);
  const size = 200;
  const stroke = 32;
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
          }}>
            <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>{hoverLabel}</div>
            <div style={{ fontSize: "1.25rem", fontWeight: 800, color: hoverColor, direction: "ltr" }}>{hoverValue}</div>
            <div style={{ fontSize: "0.72rem", color: "#9ca3af", marginTop: 2 }}>{hoverPct}</div>
          </div>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
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
                <span style={{ fontSize: "0.82rem", color: "#374151", flex: 1 }}>{d.label}</span>
                <span style={{ fontSize: "0.82rem", fontWeight: 700, color: d.color, direction: "ltr" }}>
                  {f(d.value)}
                </span>
                <span style={{ fontSize: "0.7rem", color: "#9ca3af", direction: "ltr", width: 38, textAlign: "left" }}>
                  {fmtPct(pct)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {dimmed ? null : null}
    </Card>
  );
}

export function ProductionPlanningDashboardPage(): JSX.Element {
  const [filter, setFilter] = useState<"all" | LineStatus | ProductGroup>("all");
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
      const totalStopMin = gl.reduce((s, l) => s + l.stopMinutes, 0);
      const weightedWaste = produced > 0 ? gl.reduce((s, l) => s + (l.wastePct / 100) * l.produced, 0) / produced * 100 : 0;
      const weightedOee = gl.length > 0 ? gl.reduce((s, l) => s + l.oeePct * Math.max(l.produced, 1), 0) / Math.max(gl.reduce((s, l) => s + Math.max(l.produced, 1), 0), 1) : 0;
      const runningCount = gl.filter((l) => l.status === "running").length;
      const issueCount = gl.filter((l) => l.status === "stopped" || l.status === "maintenance").length;
      return {
        key: gm.key, label: gm.label, color: gm.color, icon: gm.icon,
        planned, produced, achievement, weightedOee, totalStopMin, weightedWaste,
        lineCount: gl.length, runningCount, issueCount, lines: gl,
      };
    });
  }, [lines]);

  const visible = useMemo(() => {
    if (filter === "all") return lines;
    if (["running", "stopped", "changeover", "maintenance"].includes(filter))
      return lines.filter((l) => l.status === (filter as LineStatus));
    return lines.filter((l) => l.group === (filter as ProductGroup));
  }, [lines, filter]);

  const visibleTotals = useMemo(() => {
    const planned = visible.reduce((s, l) => s + l.planned, 0);
    const produced = visible.reduce((s, l) => s + l.produced, 0);
    const achievement = planned > 0 ? (produced / planned) * 100 : 0;
    const totalStopMin = visible.reduce((s, l) => s + l.stopMinutes, 0);
    const weightedWaste = produced > 0 ? visible.reduce((s, l) => s + (l.wastePct / 100) * l.produced, 0) / produced * 100 : 0;
    const avgOee = visible.length > 0 ? visible.reduce((s, l) => s + l.oeePct, 0) / visible.length : 0;
    return { planned, produced, achievement, totalStopMin, weightedWaste, avgOee };
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
            ? `نمای لحظه‌ای گروه‌های محصول + ویرایش برنامه (دسترسی: ${session?.user.role ?? "?"})`
            : `نمای لحظه‌ای گروه‌های محصول (فقط مشاهده — دسترسی: ${session?.user.role ?? "?"})`
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

      {/* Product group summary cards (5 groups) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginBottom: 10 }}>
        {groupTotals.map((g) => (
          <GroupCard key={g.key} g={g} onJump={(k) => setFilter(filter === k ? "all" : k)} />
        ))}
      </div>

      {/* Group filter chips */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0 4px", alignItems: "center" }}>
        <span style={{ fontSize: "0.78rem", color: "#6b7280", marginLeft: 6 }}>فیلتر گروه محصول:</span>
        <button
          type="button"
          onClick={() => setFilter("all")}
          style={{
            padding: "5px 12px", borderRadius: 16, border: filter === "all" ? "none" : "1px solid #e5e7eb",
            background: filter === "all" ? "#374151" : "#fff", color: filter === "all" ? "#fff" : "#374151",
            cursor: "pointer", fontSize: "0.78rem", fontWeight: 600,
          }}
        >همه گروه‌ها</button>
        {GROUPS.map((gm) => (
          <button
            key={gm.key}
            type="button"
            onClick={() => setFilter(filter === gm.key ? "all" : gm.key)}
            style={{
              padding: "5px 12px", borderRadius: 16,
              border: filter === gm.key ? "none" : "1px solid #e5e7eb",
              background: filter === gm.key ? gm.color : "#fff",
              color: filter === gm.key ? "#fff" : "#374151",
              cursor: "pointer", fontSize: "0.78rem", fontWeight: 600,
            }}
          >{gm.label}</button>
        ))}
      </div>

      {/* Status filter chips */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "4px 0 10px", alignItems: "center" }}>
        <span style={{ fontSize: "0.78rem", color: "#6b7280", marginLeft: 6 }}>وضعیت:</span>
        {statusFilters.map((f) => {
          const active = filter === f.key;
          const meta = f.key !== "all" ? STATUS_META[f.key as LineStatus] : null;
          return (
            <button
              key={f.key} type="button" onClick={() => setFilter(f.key)}
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
      </div>

      {/* Central comparison table */}
      <Card padding="none">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem", minWidth: 900 }}>
            <thead>
              <tr style={{ background: "#f8fafb", borderBottom: "2px solid #e5e7eb" }}>
                <th style={thStyle}>گروه محصول</th>
                <th style={thStyle}>خط تولید</th>
                <th style={thStyle}>محصول</th>
                <th style={thStyle}>وضعیت</th>
                <th style={thStyleNum}>برنامه</th>
                <th style={thStyleNum}>تولید</th>
                <th style={thStyleNum}>تحقق</th>
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
                const ach = line.planned > 0 ? (line.produced / line.planned) * 100 : 0;
                const achColor = ach >= 95 ? "#10b981" : ach >= 80 ? "#f59e0b" : "#ef4444";
                const oeeColor = line.oeePct >= 85 ? "#10b981" : line.oeePct >= 70 ? "#f59e0b" : "#ef4444";
                const wasteColor = line.wastePct > 2.5 ? "#ef4444" : line.wastePct > 1.5 ? "#f59e0b" : "#10b981";
                const stopColor = line.stopMinutes > 120 ? "#ef4444" : line.stopMinutes > 60 ? "#f59e0b" : "#10b981";
                const speedRatio = line.nominalSpeed > 0 ? line.actualSpeed / line.nominalSpeed : 0;
                const speedColor = speedRatio >= 0.95 ? "#10b981" : speedRatio >= 0.8 ? "#f59e0b" : "#ef4444";
                return (
                  <tr key={line.id} style={{ borderBottom: "1px solid #f0f2f4", background: idx % 2 === 0 ? "#fff" : "#fafbfc" }}>
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
                    <td style={tdStyleNum}>
                      <span style={{ color: speedColor }}>{fmtNum(line.actualSpeed)}</span>
                      <span style={{ color: "#9ca3af", fontSize: "0.72rem" }}> / {fmtNum(line.nominalSpeed)}</span>
                    </td>
                    <td style={tdStyleNum}><span style={{ color: stopColor }}>{fmtDur(line.stopMinutes)}</span></td>
                    <td style={tdStyleNum}><span style={{ color: wasteColor }}>{fmtPct(line.wastePct)}</span></td>
                    <td style={tdStyleNum}><span style={{ color: oeeColor, fontWeight: 700 }}>{fmtPct(line.oeePct)}</span></td>
                    <td style={tdStyleNum}>{toPersianDigits(line.shift.toString())}</td>
                  </tr>
                );
              })}
            </tbody>
            {visible.length > 0 && (
              <tfoot>
                <tr style={{ background: "#f0f6ff", borderTop: "2px solid #bfdbfe", fontWeight: 700 }}>
                  <td style={{ ...tdStyle, padding: "10px 12px" }} colSpan={4}>جمع فیلتر شده</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtNum(visibleTotals.planned)}</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtNum(visibleTotals.produced)}</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>
                    <span style={{ color: visibleTotals.achievement >= 90 ? "#10b981" : visibleTotals.achievement >= 75 ? "#f59e0b" : "#ef4444" }}>
                      {fmtPct(visibleTotals.achievement)}
                    </span>
                  </td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>—</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtDur(visibleTotals.totalStopMin)}</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtPct(visibleTotals.weightedWaste)}</td>
                  <td style={{ ...tdStyleNum, padding: "10px 12px" }}>{fmtPct(visibleTotals.avgOee)}</td>
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
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>سهم تولید به تفکیک گروه محصول</h3>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
          <InteractiveDonutCard
            title="تولید واقعی"
            subtitle="ماوس روی هر تکه نگه دارید تا تعداد تولید هر گروه را ببینید"
            data={groupTotals.map((g) => ({ key: g.key, label: g.label, value: g.produced, color: g.color }))}
            totalLabel="عدد"
          />
          <InteractiveDonutCard
            title="برنامه تولید"
            subtitle="مقایسه برنامه اختصاص‌یافته به هر گروه"
            data={groupTotals.map((g) => ({ key: g.key, label: g.label, value: g.planned, color: g.color }))}
            totalLabel="عدد"
            dimmed
          />
          <InteractiveDonutCard
            title="توقفات"
            subtitle="سهم هر گروه از مجموع زمان توقف"
            data={groupTotals.map((g) => ({ key: g.key, label: g.label, value: Math.round(g.totalStopMin), color: g.color }))}
            totalLabel="دقیقه"
            valueFormatter={(v) => fmtDur(v)}
          />
        </div>
      </div>

      {/* Per-group line cards */}
      {GROUPS.map((gm) => {
        const groupLines = visible.filter((l) => l.group === gm.key);
        if (groupLines.length === 0) return null;
        return (
          <div key={gm.key} style={{ marginTop: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ width: 6, height: 22, background: gm.color, borderRadius: 3 }} />
              <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "#111" }}>{gm.label}</h3>
              <span style={{ fontSize: "0.78rem", color: "#6b7280" }}>
                ({toPersianDigits(groupLines.length.toString())} خط)
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 14 }}>
              {groupLines.map((line) => <LineCard key={line.id} line={line} />)}
            </div>
          </div>
        );
      })}

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
