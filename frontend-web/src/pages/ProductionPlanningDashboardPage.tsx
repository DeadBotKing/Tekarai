import { useMemo, useState } from "react";
import { SectionHeader, Button } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import { toPersianDigits } from "../core/localization/jalali";
import { usePermissions } from "../core/permissions/permissionContext";
import { useAuth } from "../core/auth/authContext";

type LineStatus = "running" | "stopped" | "changeover" | "maintenance";
type ProductGroup = "tablets_capsules" | "softgel" | "vials_lyo" | "powder_filling" | "syringes_ampoules";
type CompanyCode = "ronak_internal" | "arang" | "ronapharmed" | "hakiman" | "zistdaru";

interface ProductionLine {
  id: string; name: string; product: string; group: ProductGroup; status: LineStatus; company: CompanyCode;
  planned: number; produced: number; nominalSpeed: number; actualSpeed: number;
  stopMinutes?: number | null; wastePct?: number | null; oeePct?: number | null; shift: number; lastUpdated: string;
}

const STATUS_META: Record<LineStatus, { label: string; color: string; dot: string }> = {
  running:     { label: "در حال تولید",  color: "#10b981", dot: "#10b981" },
  stopped:     { label: "متوقف",         color: "#ef4444", dot: "#ef4444" },
  changeover:  { label: "تعویض محصول",   color: "#f59e0b", dot: "#f59e0b" },
  maintenance: { label: "تعمیرات",        color: "#6b7280", dot: "#6b7280" },
};

interface GroupMeta { key: ProductGroup; label: string; color: string; icon: import("../shared/components/Icon").IconName; }
const GROUPS: GroupMeta[] = [
  { key: "tablets_capsules", label: "قرص و کپسول",     color: "#0ea5e9", icon: "target" },
  { key: "softgel",          label: "سافت‌ژل",         color: "#8b5cf6", icon: "layers" },
  { key: "vials_lyo",        label: "ویال و لیوفیلیزه", color: "#10b981", icon: "activity" },
  { key: "powder_filling",   label: "پودر فیلینگ",     color: "#f59e0b", icon: "briefcase" },
  { key: "syringes_ampoules",label: "سرنگ و آمپول",    color: "#ef4444", icon: "bell" },
];

interface CompanyMeta { key: CompanyCode; label: string; color: string; icon: import("../shared/components/Icon").IconName; isContract: boolean; }
const COMPANIES: CompanyMeta[] = [
  { key: "ronak_internal", label: "روناک (داخلی)", short: "روناک", color: "#0f766e", icon: "building", isContract: false } as any,
  { key: "arang",          label: "آرنگ",          short: "آرنگ", color: "#6366f1", icon: "briefcase", isContract: true } as any,
  { key: "ronapharmed",    label: "رونافارمد",     short: "رونافارمد", color: "#db2777", icon: "users", isContract: true } as any,
  { key: "hakiman",        label: "حکیمان",        short: "حکیمان", color: "#059669", icon: "layers", isContract: true } as any,
  { key: "zistdaru",       label: "زیست دارو",     short: "زیست‌دارو", color: "#ea580c", icon: "target", isContract: true } as any,
];

const fmtNum = (n: number): string => toPersianDigits(n.toLocaleString("en-US"));
const fmtPct = (n: number): string => toPersianDigits(n.toFixed(1) + "%");
const fmtOptPct = (n: number | null | undefined): string => (n == null ? "—" : fmtPct(n));
const fmtOptDur = (m: number | null | undefined): string => (m == null ? "—" : fmtDur(m));
const fmtDur = (minutes: number): string => {
  const h = Math.floor(minutes / 60); const mm = Math.round(minutes % 60);
  if (h === 0) return toPersianDigits(mm + " دقیقه");
  return toPersianDigits(h + "h " + mm + "m");
};

const thStyle: React.CSSProperties = { padding: "10px 10px", textAlign: "right", fontSize: "0.73rem", fontWeight: 700, color: "#334155", whiteSpace: "nowrap", borderBottom: "1px solid #e2e8f0" };
const thStyleNum: React.CSSProperties = { ...thStyle, textAlign: "center", direction: "ltr" };
const tdStyle: React.CSSProperties = { padding: "8px 10px", textAlign: "right", fontSize: "0.79rem", color: "#1e293b", whiteSpace: "nowrap" };
const tdStyleNum: React.CSSProperties = { ...tdStyle, textAlign: "center", direction: "ltr", fontVariantNumeric: "tabular-nums" };

/** ۱۳ خط واقعی کارخانه روناک */
const DEMO_LINES: ProductionLine[] = [
  { id: "L01", name: "خط ۱ ویال",                product: "ویال 10ml",            group: "vials_lyo",         company: "ronak_internal", status: "running",    planned: 60000, produced: 58200, nominalSpeed: 1200, actualSpeed: 1150, stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:43" },
  { id: "L02", name: "خط ۲ ویال",                product: "ویال 5ml",             group: "vials_lyo",         company: "ronak_internal", status: "running",    planned: 45000, produced: 38200, nominalSpeed: 900,  actualSpeed: 840,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:40" },
  { id: "L03", name: "خط ۳ ویال",                product: "ویال لیوفیلیزه",       group: "vials_lyo",         company: "ronak_internal", status: "changeover", planned: 40000, produced: 24800, nominalSpeed: 800,  actualSpeed: 620,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:25" },
  { id: "L04", name: "خط آمپول",                 product: "آمپول 2ml",            group: "syringes_ampoules", company: "ronak_internal", status: "running",    planned: 50000, produced: 47500, nominalSpeed: 1000, actualSpeed: 950,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:42" },
  { id: "L05", name: "خط جامدات - تولید",        product: "قرص 500mg",            group: "tablets_capsules",  company: "ronak_internal", status: "running",    planned: 80000, produced: 79200, nominalSpeed: 1200, actualSpeed: 1180, stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:44" },
  { id: "L06", name: "خط جامدات - بسته‌بندی",    product: "کپسول 250mg",          group: "tablets_capsules",  company: "ronak_internal", status: "stopped",    planned: 55000, produced: 31000, nominalSpeed: 1000, actualSpeed: 0,    stopMinutes: null, wastePct: null, oeePct: null, shift: 1, lastUpdated: "11:05" },
  { id: "L07", name: "خط سافت ژل",               product: "سافت‌ژل 500mg",        group: "softgel",           company: "ronak_internal", status: "running",    planned: 35000, produced: 31200, nominalSpeed: 700,  actualSpeed: 660,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:45" },
  { id: "L08", name: "خط جامدات آنتی‌کنسر",      product: "قرص آنتی‌کنسر",       group: "tablets_capsules",  company: "ronak_internal", status: "running",    planned: 18000, produced: 14200, nominalSpeed: 360,  actualSpeed: 340,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "13:50" },
  { id: "L09", name: "خط تزریقی آنتی‌کنسر",      product: "ویال تزریقی آنتی‌کنسر",group: "syringes_ampoules", company: "ronak_internal", status: "running",    planned: 22000, produced: 19500, nominalSpeed: 440,  actualSpeed: 410,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:10" },
  { id: "L10", name: "خط بوتاکس",                product: "ویال بوتاکس",          group: "vials_lyo",         company: "ronak_internal", status: "maintenance",planned: 12000, produced: 7400,  nominalSpeed: 240,  actualSpeed: 0,    stopMinutes: null, wastePct: null, oeePct: null, shift: 1, lastUpdated: "11:30" },
  { id: "L11", name: "خط ریزدیپلام",             product: "پودر ریزدیپلام",       group: "powder_filling",    company: "ronak_internal", status: "running",    planned: 15000, produced: 13800, nominalSpeed: 300,  actualSpeed: 290,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:38" },
  { id: "L12", name: "خط سرنگ (داخل خط ۱ ویال)",  product: "سرنگ 5ml",             group: "syringes_ampoules", company: "ronak_internal", status: "running",    planned: 30000, produced: 27600, nominalSpeed: 600,  actualSpeed: 570,  stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "14:41" },
  { id: "L13", name: "خط سرنگ (داخل خط ۳ ویال)",  product: "سرنگ 2ml",             group: "syringes_ampoules", company: "ronak_internal", status: "maintenance",planned: 25000, produced: 10100, nominalSpeed: 500,  actualSpeed: 0,    stopMinutes: null, wastePct: null, oeePct: null, shift: 2, lastUpdated: "11:35" },
];

interface GroupTotals { key: ProductGroup; label: string; color: string; icon: GroupMeta["icon"]; planned: number; produced: number; achievement: number; lineCount: number; runningCount: number; issueCount: number; }
interface CompanyTotals { key: CompanyCode; label: string; color: string; icon: CompanyMeta["icon"]; isContract: boolean; planned: number; produced: number; achievement: number; shareOfTotal: number; lineCount: number; lines: ProductionLine[]; }

/* ---------- Compact Group Card ---------- */
function GroupCard({ g, onJump }: { g: GroupTotals; onJump?: (group: ProductGroup) => void }): JSX.Element {
  const achColor = g.achievement >= 95 ? "#10b981" : g.achievement >= 80 ? "#f59e0b" : "#ef4444";
  return (
    <div onClick={() => onJump?.(g.key)} style={{
      background: "#fff", borderRadius: 14, border: "1px solid #eef2f7", boxShadow: "0 1px 3px rgba(15,23,42,0.04), 0 4px 12px rgba(15,23,42,0.04)",
      padding: 14, minWidth: 230, flex: "1 1 230px", cursor: onJump ? "pointer" : "default", transition: "all 150ms", position: "relative", overflow: "hidden"
    }}>
      <div style={{ position: "absolute", top: 0, right: 0, left: 0, height: 3, background: g.color, opacity: 0.9 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: g.color + "14", color: g.color, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon name={g.icon as any} size={18} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: "0.86rem", fontWeight: 700, color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{g.label}</div>
          <div style={{ fontSize: "0.70rem", color: "#64748b" }}>{toPersianDigits(g.runningCount.toString())} فعال از {toPersianDigits(g.lineCount.toString())} {g.issueCount>0 && <span style={{ color:"#ef4444" }}>• {toPersianDigits(g.issueCount.toString())} مشکل</span>}</div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 10 }}>
        <div style={{ background: "#f8fafc", borderRadius: 9, padding: "8px 6px", textAlign: "center", border: "1px solid #f1f5f9" }}>
          <div style={{ fontSize: "0.66rem", color: "#64748b" }}>برنامه</div>
          <div style={{ fontSize: "0.92rem", fontWeight: 700, color: "#0f172a", direction: "ltr" }}>{fmtNum(g.planned)}</div>
        </div>
        <div style={{ background: "#f8fafc", borderRadius: 9, padding: "8px 6px", textAlign: "center", border: "1px solid #f1f5f9" }}>
          <div style={{ fontSize: "0.66rem", color: "#64748b" }}>تولید</div>
          <div style={{ fontSize: "0.92rem", fontWeight: 700, color: "#0f172a", direction: "ltr" }}>{fmtNum(g.produced)}</div>
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.70rem", color: "#64748b", marginBottom: 5 }}><span>تحقق</span><span style={{ color: achColor, fontWeight: 700 }}>{fmtPct(g.achievement)}</span></div>
      <div style={{ height: 6, background: "#f1f5f9", borderRadius: 99, overflow: "hidden" }}><div style={{ width: `${Math.min(g.achievement,100)}%`, height: "100%", background: achColor, borderRadius: 99, transition: "width 400ms" }} /></div>
    </div>
  );
}

/* ---------- Compact Company Card with scroll ---------- */
function CompanyCard({ c, totalProduced }: { c: CompanyTotals; totalProduced: number }): JSX.Element {
  const achColor = c.achievement >= 95 ? "#10b981" : c.achievement >= 80 ? "#f59e0b" : "#ef4444";
  const shareTotal = totalProduced > 0 ? (c.produced / totalProduced) * 100 : 0;
  const isEmpty = c.lineCount === 0 || (c.planned === 0 && c.produced === 0);
  if (isEmpty) {
    return (
      <div style={{
        background: "#f8fafc", border: "1px dashed #e2e8f0", borderRadius: 12, padding: "12px 14px",
        display: "flex", alignItems: "center", gap: 10, minWidth: 200, opacity: 0.7
      }}>
        <div style={{ width: 28, height: 28, borderRadius: 8, background: "#fff", border: "1px solid #e2e8f0", color: "#94a3b8", display: "flex", alignItems:"center", justifyContent:"center"}}><Icon name={c.icon as any} size={14} /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "#64748b" }}>{c.label}</div>
          <div style={{ fontSize: "0.70rem", color: "#94a3b8" }}>بدون تولید</div>
        </div>
        <span style={{ fontSize:"0.68rem", background:"#fff", border:"1px solid #e2e8f0", padding:"2px 6px", borderRadius:20, color:"#94a3b8" }}>{fmtPct(0)}</span>
      </div>
    );
  }
  return (
    <div style={{
      background: "#fff", borderRadius: 14, border: "1px solid #eef2f7", boxShadow: "0 1px 3px rgba(15,23,42,0.04), 0 8px 20px rgba(15,23,42,0.05)",
      width: 300, flexShrink: 0, display: "flex", flexDirection: "column", overflow: "hidden"
    }}>
      <div style={{ height: 3, background: c.color }} />
      <div style={{ padding: "12px 12px 10px", display: "flex", alignItems: "center", gap: 9, borderBottom: "1px solid #f8fafc" }}>
        <div style={{ width: 32, height: 32, borderRadius: 9, background: c.color + "12", color: c.color, display: "flex", alignItems:"center", justifyContent:"center"}}><Icon name={c.icon as any} size={16} /></div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:"0.84rem", fontWeight:700, color:"#0f172a", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>{c.label}</div>
          <div style={{ fontSize:"0.70rem", color:"#64748b" }}>{toPersianDigits(c.lineCount.toString())} خط • <span style={{ color:c.color, fontWeight:600 }}>{fmtPct(shareTotal)} از کل</span></div>
        </div>
        <span style={{ fontSize:"0.66rem", background: c.isContract ? c.color+"12" : "#f0fdfa", color: c.isContract ? c.color : "#0f766e", border:`1px solid ${c.isContract ? c.color+"20" : "#99f6e4"}`, padding:"2px 7px", borderRadius:20, fontWeight:700, whiteSpace:"nowrap"}}>{c.isContract ? "قراردادی" : "داخلی"}</span>
      </div>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6, padding: "10px 10px 0" }}>
        <div style={{ background:"#f8fafc", borderRadius:8, padding:"7px", textAlign:"center", border:"1px solid #f1f5f9"}}><div style={{ fontSize:"0.65rem", color:"#64748b"}}>برنامه</div><div style={{ fontSize:"0.88rem", fontWeight:700, color:"#0f172a", direction:"ltr"}}>{fmtNum(c.planned)}</div></div>
        <div style={{ background:"#f8fafc", borderRadius:8, padding:"7px", textAlign:"center", border:"1px solid #f1f5f9"}}><div style={{ fontSize:"0.65rem", color:"#64748b"}}>تولید</div><div style={{ fontSize:"0.88rem", fontWeight:700, color:"#0f172a", direction:"ltr"}}>{fmtNum(c.produced)}</div></div>
      </div>
      <div style={{ padding:"8px 10px 10px" }}>
        <div style={{ display:"flex", justifyContent:"space-between", fontSize:"0.70rem", color:"#64748b", marginBottom:4 }}><span>تحقق</span><span style={{ color: achColor, fontWeight:700 }}>{fmtPct(c.achievement)}</span></div>
        <div style={{ height:5, background:"#f1f5f9", borderRadius:99, overflow:"hidden"}}><div style={{ width:`${Math.min(c.achievement,100)}%`, height:"100%", background: achColor, borderRadius:99 }} /></div>
      </div>
      <div style={{ flex:1, borderTop:"1px solid #f1f5f9", display:"flex", flexDirection:"column", minHeight:0 }}>
        <div style={{ fontSize:"0.72rem", fontWeight:700, color:"#334155", padding:"8px 12px 6px"}}>محصولات</div>
        <div style={{ flex:1, overflowY:"auto", padding:"0 8px 8px", display:"flex", flexDirection:"column", gap:5, maxHeight: 150, scrollbarWidth:"thin" }}>
          {c.lines.map((l) => {
            const gm = GROUPS.find((g) => g.key === l.group)!;
            const pct = c.produced>0 ? (l.produced/c.produced)*100 : 0;
            return (
              <div key={l.id} style={{ display:"flex", alignItems:"center", gap:7, background:"#f8fafc", border:"1px solid #f1f5f9", borderRadius:8, padding:"6px 7px"}}>
                <span style={{ width:7, height:7, borderRadius:3, background:gm.color, flexShrink:0 }} />
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:"0.74rem", fontWeight:600, color:"#1e293b", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>{l.product}</div>
                  <div style={{ fontSize:"0.67rem", color:"#64748b", display:"flex", gap:4, alignItems:"center"}}><span style={{ background: gm.color+"12", color: gm.color, padding:"1px 5px", borderRadius:6, fontSize:"0.65rem", fontWeight:600}}>{gm.label}</span>{STATUS_META[l.status].label}</div>
                </div>
                <div style={{ textAlign:"left", flexShrink:0 }}>
                  <div style={{ fontSize:"0.75rem", fontWeight:700, color:"#0f172a", direction:"ltr"}}>{fmtNum(l.produced)}</div>
                  <div style={{ fontSize:"0.66rem", color:c.color, fontWeight:600, direction:"ltr"}}>{fmtPct(pct)}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ---------- Compact Overview ---------- */
function CompactOverview({ totalPlanned, totalProduced, contractProduced, internalPlanned, internalProduced }: any): JSX.Element {
  const contractPct = totalProduced>0 ? (contractProduced/totalProduced)*100 : 0;
  const internalPct = totalProduced>0 ? (internalProduced/totalProduced)*100 : 0;
  const totalAch = totalPlanned>0 ? (totalProduced/totalPlanned)*100 : 0;
  return (
    <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(220px,1fr))", gap:10 }}>
      <div style={{ background:"#fff", border:"1px solid #eef2f7", borderRadius:14, padding:12, boxShadow:"0 1px 3px rgba(15,23,42,0.04)", display:"flex", flexDirection:"column", gap:8 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}><div style={{ width:30, height:30, borderRadius:8, background:"#0f172a", color:"#fff", display:"flex", alignItems:"center", justifyContent:"center"}}><Icon name="chart" size={14} /></div><div><div style={{ fontSize:"0.78rem", fontWeight:700, color:"#0f172a"}}>کل تولید کارخانه</div><div style={{ fontSize:"0.70rem", color:"#64748b"}}>۱۳ خط فعال</div></div></div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6 }}>
          <div style={{ background:"#f8fafc", borderRadius:8, padding:7, textAlign:"center", border:"1px solid #f1f5f9"}}><div style={{ fontSize:"0.65rem", color:"#64748b"}}>برنامه</div><div style={{ fontSize:"0.95rem", fontWeight:700, direction:"ltr"}}>{fmtNum(totalPlanned)}</div></div>
          <div style={{ background:"#0f172a", borderRadius:8, padding:7, textAlign:"center", color:"#fff"}}><div style={{ fontSize:"0.65rem", opacity:0.8}}>تولید</div><div style={{ fontSize:"0.95rem", fontWeight:800, direction:"ltr"}}>{fmtNum(totalProduced)}</div></div>
        </div>
        <div><div style={{ display:"flex", justifyContent:"space-between", fontSize:"0.70rem", color:"#64748b", marginBottom:4}}><span>تحقق کل</span><span style={{ color: totalAch>=90 ? "#10b981" : "#f59e0b", fontWeight:700}}>{fmtPct(totalAch)}</span></div><div style={{ height:6, background:"#f1f5f9", borderRadius:99, overflow:"hidden"}}><div style={{ width:`${Math.min(totalAch,100)}%`, height:"100%", background: totalAch>=90 ? "#10b981" : "#f59e0b"}}/></div></div>
      </div>

      <div style={{ background:"#fff", border:"1px solid #eef2f7", borderRadius:14, padding:12, boxShadow:"0 1px 3px rgba(15,23,42,0.04)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8}}><div style={{ width:30, height:30, borderRadius:8, background:"#f0fdfa", color:"#0f766e", border:"1px solid #ccfbf1", display:"flex", alignItems:"center", justifyContent:"center"}}><Icon name="building" size={14} /></div><div style={{ flex:1}}><div style={{ fontSize:"0.82rem", fontWeight:700, color:"#0f172a"}}>روناک — داخلی</div><div style={{ fontSize:"0.70rem", color:"#64748b"}}>{fmtPct(internalPct)} از کل</div></div><div style={{ fontSize:"0.75rem", fontWeight:800, color:"#0f766e", background:"#f0fdfa", border:"1px solid #ccfbf1", padding:"4px 8px", borderRadius:20}}>{fmtNum(internalProduced)}</div></div>
        <div style={{ display:"flex", height:8, borderRadius:99, overflow:"hidden", background:"#f1f5f9", border:"1px solid #e2e8f0"}}><div style={{ width:`${internalPct}%`, background:"#0f766e"}}/></div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6, marginTop:8 }}>
          <div style={{ background:"#f8fafc", borderRadius:8, padding:6, textAlign:"center"}}><div style={{ fontSize:"0.65rem", color:"#64748b"}}>برنامه</div><div style={{ fontSize:"0.84rem", fontWeight:600, direction:"ltr"}}>{fmtNum(internalPlanned)}</div></div>
          <div style={{ background:"#f8fafc", borderRadius:8, padding:6, textAlign:"center"}}><div style={{ fontSize:"0.65rem", color:"#64748b"}}>تحقق</div><div style={{ fontSize:"0.84rem", fontWeight:700, color: internalPlanned>0 && internalProduced/internalPlanned>=0.9 ? "#10b981" : "#f59e0b"}}>{fmtPct(internalPlanned>0 ? (internalProduced/internalPlanned)*100 : 0)}</div></div>
        </div>
      </div>

      <div style={{ background:"#fff", border:"1px solid #eef2f7", borderRadius:14, padding:12, opacity: contractPct===0 ? 0.6 : 1, boxShadow:"0 1px 3px rgba(15,23,42,0.04)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8}}><div style={{ width:30, height:30, borderRadius:8, background: contractPct===0 ? "#f8fafc" : "#eef2ff", color: contractPct===0 ? "#94a3b8" : "#6366f1", border:"1px solid #e2e8f0", display:"flex", alignItems:"center", justifyContent:"center"}}><Icon name="users" size={14} /></div><div style={{ flex:1}}><div style={{ fontSize:"0.82rem", fontWeight:700, color: contractPct===0 ? "#64748b" : "#0f172a"}}>قراردادی — ۴ شرکت</div><div style={{ fontSize:"0.70rem", color:"#64748b"}}>{fmtPct(contractPct)} از کل</div></div><div style={{ fontSize:"0.75rem", fontWeight:800, color: contractPct===0 ? "#94a3b8" : "#6366f1", background: contractPct===0 ? "#f8fafc" : "#eef2ff", border:"1px solid #e2e8f0", padding:"4px 8px", borderRadius:20}}>{fmtNum(contractProduced)}</div></div>
        <div style={{ display:"flex", height:8, borderRadius:99, overflow:"hidden", background:"#f1f5f9", border:"1px solid #e2e8f0"}}><div style={{ width:`${contractPct===0 ? 0 : contractPct}%`, background:"linear-gradient(90deg,#6366f1,#ec4899)"}}/></div>
        <div style={{ fontSize:"0.70rem", color:"#94a3b8", textAlign:"center", marginTop:8, background:"#f8fafc", borderRadius:8, padding:6, border:"1px dashed #e2e8f0"}}>{contractPct===0 ? "فعلا همه تولید داخلی است" : `سهم قراردادی ${fmtPct(contractPct)}`}</div>
      </div>
    </div>
  );
}

interface DonutDatum { key: string; label: string; value: number; color: string; subLabel?: string; }
function InteractiveDonutCard({ title, subtitle, data, totalLabel, valueFormatter }: { title: string; subtitle?: string; data: DonutDatum[]; totalLabel: string; valueFormatter?: (v:number)=>string }): JSX.Element {
  const [hover, setHover]=useState<string|null>(null);
  const size=180; const stroke=22; const r=(size-stroke)/2; const cx=size/2; const cy=size/2; const C=2*Math.PI*r;
  const f=valueFormatter ?? fmtNum;
  const positive=data.filter(d=>d.value>0); const total=positive.reduce((s,d)=>s+d.value,0);
  let offset=0; const gap=positive.length>1 ? 1.2 : 0;
  const segments=positive.map(d=>{ const frac=d.value/Math.max(total,1); const dash=Math.max(frac*C-gap,0.5); const seg={...d, dash, offset, pct: frac*100}; offset+=frac*C; return seg; });
  const hovered= hover ? segments.find(s=>s.key===hover) : null;
  const hoverValue= hovered ? f(hovered.value) : f(total);
  const hoverPct= hovered ? fmtPct(hovered.pct) : fmtPct(100);
  const hoverLabel= hovered ? hovered.label : "مجموع";
  const hoverSub= hovered?.subLabel ?? totalLabel;
  const hoverColor= hovered ? hovered.color : "#0f172a";
  return (
    <div style={{ background:"#fff", border:"1px solid #eef2f7", borderRadius:14, padding:14, boxShadow:"0 1px 3px rgba(15,23,42,0.04), 0 4px 12px rgba(15,23,42,0.04)" }}>
      <div style={{ marginBottom:10}}><h4 style={{ margin:0, fontSize:"0.88rem", fontWeight:700, color:"#0f172a"}}>{title}</h4>{subtitle && <div style={{ fontSize:"0.70rem", color:"#64748b", marginTop:2}}>{subtitle}</div>}</div>
      <div style={{ display:"flex", gap:12, alignItems:"center"}}>
        <div style={{ position:"relative", width:size, height:size, flexShrink:0 }}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform:"rotate(-90deg)"}}>
            <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth={stroke} />
            {segments.map(s=>{
              const isHover= hover===s.key; const isOther= hover && hover!==s.key;
              return <circle key={s.key} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth={isHover ? stroke+4 : stroke} strokeDasharray={`${s.dash} ${C-s.dash}`} strokeDashoffset={C*0.25 - s.offset} strokeLinecap="butt" opacity={isOther ? 0.35 : 1} onMouseEnter={()=>setHover(s.key)} onMouseLeave={()=>setHover(null)} style={{ transition:"all 120ms", cursor:"pointer"}} />
            })}
          </svg>
          <div style={{ position:"absolute", inset:0, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", pointerEvents:"none", padding:"0 10px", textAlign:"center"}}>
            <div style={{ fontSize:"0.66rem", color:"#64748b", maxWidth:"80%", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{hoverLabel}</div>
            <div style={{ fontSize:"1.05rem", fontWeight:800, color:hoverColor, direction:"ltr"}}>{hoverValue}</div>
            <div style={{ fontSize:"0.70rem", color: hovered ? hoverColor : "#94a3b8", fontWeight:600}}>{hoverPct}</div>
            <div style={{ fontSize:"0.64rem", color:"#94a3b8"}}>{hoverSub}</div>
          </div>
        </div>
        <div style={{ flex:1, display:"flex", flexDirection:"column", gap:4, maxHeight:180, overflowY:"auto", scrollbarWidth:"thin", paddingLeft:2}}>
          {data.map(d=>{
            const pct= total>0 ? (d.value/total)*100 : 0; const isHover= hover===d.key; const isOther= hover && hover!==d.key;
            return (
              <div key={d.key} onMouseEnter={()=>setHover(d.key)} onMouseLeave={()=>setHover(null)} style={{ display:"flex", alignItems:"center", gap:7, padding:"5px 7px", borderRadius:8, cursor:"pointer", background: isHover ? d.color+"10" : "transparent", opacity: isOther ? 0.5 : 1, transition:"all 120ms"}}>
                <span style={{ width:8, height:8, borderRadius:3, background:d.color, flexShrink:0}}/>
                <div style={{ flex:1, minWidth:0}}><div style={{ fontSize:"0.76rem", color:"#1e293b", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>{d.label}</div>{d.subLabel && <div style={{ fontSize:"0.64rem", color:"#94a3b8"}}>{d.subLabel}</div>}</div>
                <span style={{ fontSize:"0.76rem", fontWeight:700, color:d.color, direction:"ltr"}}>{f(d.value)}</span>
                <span style={{ fontSize:"0.66rem", color:"#94a3b8", width:34, textAlign:"left", direction:"ltr"}}>{fmtPct(pct)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function ProductionPlanningDashboardPage(): JSX.Element {
  const [companyFilter, setCompanyFilter]=useState<CompanyCode|"all">("all");
  const [groupFilter, setGroupFilter]=useState<ProductGroup|"all">("all");
  const [statusFilter, setStatusFilter]=useState<LineStatus|"all">("all");
  const [editMode, setEditMode]=useState(false);
  const [draftPlanned, setDraftPlanned]=useState<Record<string,number>>({});
  const { has, permissions }=usePermissions(); const { session }=useAuth();
  const canManage= useMemo(()=>{ if(!session) return false; if(session.user.role==="Superadmin") return true; if(permissions.includes("*")) return true; if(has("production.manage")) return true; if(has(["settings.manage","tenant.manage","user.manage","role.manage"])) return true; return false; },[session, permissions, has]);
  const [lines, setLines]=useState<ProductionLine[]>(DEMO_LINES);

  const groupTotals: GroupTotals[]= useMemo(()=> GROUPS.map(gm=>{
    const gl=lines.filter(l=>l.group===gm.key);
    const planned=gl.reduce((s,l)=>s+l.planned,0); const produced=gl.reduce((s,l)=>s+l.produced,0);
    const achievement= planned>0 ? (produced/planned)*100 : 0;
    const runningCount=gl.filter(l=>l.status==="running").length; const issueCount=gl.filter(l=>l.status==="stopped"||l.status==="maintenance").length;
    return { key:gm.key, label:gm.label, color:gm.color, icon:gm.icon, planned, produced, achievement, lineCount:gl.length, runningCount, issueCount };
  }),[lines]);

  const companyTotals: CompanyTotals[]= useMemo(()=>{
    const totalProduced=lines.reduce((s,l)=>s+l.produced,0);
    return COMPANIES.map(cm=>{
      const cl=lines.filter(l=>l.company===cm.key);
      const planned=cl.reduce((s,l)=>s+l.planned,0); const produced=cl.reduce((s,l)=>s+l.produced,0);
      const achievement= planned>0 ? (produced/planned)*100 : 0;
      const shareOfTotal= totalProduced>0 ? (produced/totalProduced)*100 : 0;
      return { key:cm.key, label:(cm as any).label, color:cm.color, icon:cm.icon, isContract:cm.isContract, planned, produced, achievement, shareOfTotal, lineCount:cl.length, lines:cl };
    });
  },[lines]);

  const overall= useMemo(()=>{
    const totalPlanned=lines.reduce((s,l)=>s+l.planned,0); const totalProduced=lines.reduce((s,l)=>s+l.produced,0);
    const contractLines=lines.filter(l=>l.company!=="ronak_internal");
    const contractPlanned=contractLines.reduce((s,l)=>s+l.planned,0); const contractProduced=contractLines.reduce((s,l)=>s+l.produced,0);
    const internalLines=lines.filter(l=>l.company==="ronak_internal");
    const internalPlanned=internalLines.reduce((s,l)=>s+l.planned,0); const internalProduced=internalLines.reduce((s,l)=>s+l.produced,0);
    return { totalPlanned, totalProduced, contractPlanned, contractProduced, internalPlanned, internalProduced };
  },[lines]);

  const visible= useMemo(()=>{ let v=lines; if(companyFilter!=="all") v=v.filter(l=>l.company===companyFilter); if(groupFilter!=="all") v=v.filter(l=>l.group===groupFilter); if(statusFilter!=="all") v=v.filter(l=>l.status===statusFilter); return v; },[lines, companyFilter, groupFilter, statusFilter]);
  const visibleTotals= useMemo(()=>{ const planned=visible.reduce((s,l)=>s+l.planned,0); const produced=visible.reduce((s,l)=>s+l.produced,0); const achievement=planned>0 ? (produced/planned)*100 : 0; return { planned, produced, achievement }; },[visible]);
  const statusFilters: {key:"all"|LineStatus; label:string}[]=[{key:"all",label:"همه"},{key:"running",label:"در حال تولید"},{key:"changeover",label:"تعویض"},{key:"maintenance",label:"تعمیرات"},{key:"stopped",label:"متوقف"}];

  return (
    <div className="page" style={{ background:"#f8fafc", minHeight:"100vh", paddingBottom:24 }}>
      <style>{`
        .page { --card-shadow: 0 1px 3px rgba(15,23,42,0.05), 0 4px 12px rgba(15,23,42,0.05); }
        *::-webkit-scrollbar { width:6px; height:6px }
        *::-webkit-scrollbar-thumb { background:#e2e8f0; border-radius:99px }
        *::-webkit-scrollbar-track { background:transparent }
      `}</style>

      <SectionHeader
        title="داشبورد برنامه‌ریزی تولید"
        subtitle={canManage ? `نمای لحظه‌ای ۱۳ خط تولید • ${session?.user.role ?? "?"}` : `فقط مشاهده — ${session?.user.role ?? "?"}`}
        actions={
          <div style={{ display:"flex", gap:8, alignItems:"center"}}>
            {canManage ? <Button variant={editMode ? "primary" : "secondary"} icon={editMode ? "check" : "edit"} onClick={()=>{ if(editMode){ setLines(cur=>cur.map(l=> draftPlanned[l.id]!=null && draftPlanned[l.id]>=0 ? {...l, planned: Math.round(draftPlanned[l.id])} : l)); setDraftPlanned({});} setEditMode(!editMode); }}>{editMode ? "ذخیره برنامه" : "ویرایش برنامه"}</Button> : <span style={{ fontSize:"0.76rem", color:"#64748b", background:"#fff", border:"1px solid #e2e8f0", padding:"6px 12px", borderRadius:8, display:"inline-flex", alignItems:"center", gap:6}}><Icon name="lock" size={13}/> فقط مشاهده</span>}
            <Button variant="ghost" icon="refresh" onClick={()=>window.location.reload()}>به‌روزرسانی</Button>
          </div>
        }
      />

      <div style={{ padding:"0 16px", maxWidth:1400, margin:"0 auto", display:"flex", flexDirection:"column", gap:12 }}>
        <CompactOverview {...overall} />

        {/* Group cards - compact scroll */}
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
            <span style={{ width:4, height:18, background:"#0f172a", borderRadius:99}}/>
            <h3 style={{ margin:0, fontSize:"0.90rem", fontWeight:700, color:"#0f172a"}}>گروه‌های محصول</h3>
            <span style={{ fontSize:"0.70rem", color:"#64748b", background:"#fff", border:"1px solid #e2e8f0", padding:"2px 8px", borderRadius:20}}>{toPersianDigits(groupTotals.length.toString())} گروه</span>
          </div>
          <div style={{ display:"flex", gap:10, overflowX:"auto", paddingBottom:6, scrollbarWidth:"thin"}}>
            {groupTotals.map(g=> <GroupCard key={g.key} g={g} onJump={(k)=> setGroupFilter(groupFilter===k ? "all" : k)} />)}
          </div>
        </div>

        {/* Company cards - horizontal scroll compact */}
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
            <span style={{ width:4, height:18, background:"#6366f1", borderRadius:99}}/>
            <h3 style={{ margin:0, fontSize:"0.90rem", fontWeight:700, color:"#0f172a"}}>تفکیک شرکت‌ها</h3>
            <span style={{ fontSize:"0.70rem", color:"#64748b"}}>اسکرول افقی ←</span>
          </div>
          <div style={{ display:"flex", gap:10, overflowX:"auto", paddingBottom:8, scrollbarWidth:"thin", scrollSnapType:"x mandatory"}}>
            {companyTotals.map(c=> <CompanyCard key={c.key} c={c} totalProduced={overall.totalProduced} />)}
          </div>
        </div>

        {/* Filters - compact pill */}
        <div style={{ background:"#fff", border:"1px solid #eef2f7", borderRadius:12, padding:"10px 12px", boxShadow:"0 1px 2px rgba(15,23,42,0.04)", display:"flex", flexDirection:"column", gap:8}}>
          <div style={{ display:"flex", gap:6, flexWrap:"wrap", alignItems:"center"}}>
            <span style={{ fontSize:"0.72rem", fontWeight:600, color:"#334155", minWidth:60}}>شرکت:</span>
            <button type="button" onClick={()=>setCompanyFilter("all")} style={{ padding:"4px 10px", borderRadius:20, border: companyFilter==="all" ? "1px solid #0f172a" : "1px solid #e2e8f0", background: companyFilter==="all" ? "#0f172a" : "#fff", color: companyFilter==="all" ? "#fff" : "#334155", cursor:"pointer", fontSize:"0.74rem", fontWeight:600}}>همه</button>
            {COMPANIES.map(cm=>(
              <button key={cm.key} type="button" onClick={()=>setCompanyFilter(companyFilter===cm.key ? "all" : cm.key)} style={{ padding:"4px 10px", borderRadius:20, border: companyFilter===cm.key ? "none" : "1px solid #e2e8f0", background: companyFilter===cm.key ? cm.color : "#fff", color: companyFilter===cm.key ? "#fff" : "#334155", cursor:"pointer", fontSize:"0.74rem", fontWeight:500, display:"inline-flex", alignItems:"center", gap:5}}>
                <span style={{ width:7, height:7, borderRadius:"50%", background: companyFilter===cm.key ? "#fff" : cm.color}} />{(cm as any).label}
              </button>
            ))}
          </div>
          <div style={{ display:"flex", gap:6, flexWrap:"wrap", alignItems:"center"}}>
            <span style={{ fontSize:"0.72rem", fontWeight:600, color:"#334155", minWidth:60}}>گروه:</span>
            <button type="button" onClick={()=>setGroupFilter("all")} style={{ padding:"4px 10px", borderRadius:20, border: groupFilter==="all" ? "1px solid #0f172a" : "1px solid #e2e8f0", background: groupFilter==="all" ? "#0f172a" : "#fff", color: groupFilter==="all" ? "#fff" : "#334155", cursor:"pointer", fontSize:"0.74rem", fontWeight:600}}>همه</button>
            {GROUPS.map(gm=>(
              <button key={gm.key} type="button" onClick={()=>setGroupFilter(groupFilter===gm.key ? "all" : gm.key)} style={{ padding:"4px 10px", borderRadius:20, border: groupFilter===gm.key ? "none" : "1px solid #e2e8f0", background: groupFilter===gm.key ? gm.color : "#fff", color: groupFilter===gm.key ? "#fff" : "#334155", cursor:"pointer", fontSize:"0.74rem", fontWeight:500}}>{gm.label}</button>
            ))}
          </div>
          <div style={{ display:"flex", gap:6, flexWrap:"wrap", alignItems:"center"}}>
            <span style={{ fontSize:"0.72rem", fontWeight:600, color:"#334155", minWidth:60}}>وضعیت:</span>
            {statusFilters.map(f=>{
              const active=statusFilter===f.key; const meta=f.key!=="all" ? STATUS_META[f.key as LineStatus] : null;
              return <button key={f.key} type="button" onClick={()=>setStatusFilter(f.key as any)} style={{ padding:"4px 10px", borderRadius:20, border: active ? "none" : "1px solid #e2e8f0", background: active ? (meta?.color ?? "#0f172a") : "#fff", color: active ? "#fff" : "#334155", cursor:"pointer", fontSize:"0.74rem", display:"inline-flex", alignItems:"center", gap:4}}>{meta && <span style={{ width:6, height:6, borderRadius:"50%", background: active ? "#fff" : meta.color}}/>}{f.label}</button>
            })}
            {(companyFilter!=="all" || groupFilter!=="all" || statusFilter!=="all") && <button type="button" onClick={()=>{setCompanyFilter("all"); setGroupFilter("all"); setStatusFilter("all");}} style={{ marginRight:6, padding:"4px 10px", borderRadius:20, border:"1px dashed #cbd5e1", background:"#fff", color:"#64748b", cursor:"pointer", fontSize:"0.72rem"}}>پاک کردن</button>}
          </div>
        </div>

        {/* Table - polished */}
        <div style={{ background:"#fff", border:"1px solid #eef2f7", borderRadius:14, overflow:"hidden", boxShadow:"0 1px 3px rgba(15,23,42,0.04), 0 4px 16px rgba(15,23,42,0.04)"}} id="comparison-table">
          <div style={{ padding:"12px 14px", borderBottom:"1px solid #f1f5f9", display:"flex", justifyContent:"space-between", alignItems:"center"}}>
            <div style={{ fontSize:"0.86rem", fontWeight:700, color:"#0f172a", display:"flex", alignItems:"center", gap:8}}><Icon name="table" size={16}/> جدول مقایسه خطوط <span style={{ background:"#f1f5f9", color:"#475569", padding:"2px 8px", borderRadius:20, fontSize:"0.72rem"}}>{toPersianDigits(visible.length.toString())} ردیف</span></div>
            <div style={{ fontSize:"0.70rem", color:"#94a3b8"}}>ویرایش برنامه با دکمه بالا</div>
          </div>
          <div style={{ overflowX:"auto"}}>
            <table style={{ width:"100%", borderCollapse:"collapse", minWidth:1000 }}>
              <thead><tr style={{ background:"#f8fafc"}}>
                <th style={thStyle}>شرکت</th><th style={thStyle}>گروه</th><th style={thStyle}>خط تولید</th><th style={thStyle}>محصول</th><th style={thStyle}>وضعیت</th><th style={thStyleNum}>برنامه</th><th style={thStyleNum}>تولید</th><th style={thStyleNum}>تحقق</th><th style={thStyleNum}>سهم</th><th style={thStyleNum}>سرعت</th><th style={thStyleNum}>توقف</th><th style={thStyleNum}>ضایعات</th><th style={thStyleNum}>OEE</th><th style={thStyleNum}>شیفت</th>
              </tr></thead>
              <tbody>
                {visible.map((line, idx)=>{
                  const meta=STATUS_META[line.status]; const gm=GROUPS.find(g=>g.key===line.group)!; const cm=(COMPANIES as any).find((c:any)=>c.key===line.company)!;
                  const ach= line.planned>0 ? (line.produced/line.planned)*100 : 0;
                  const share= overall.totalProduced>0 ? (line.produced/overall.totalProduced)*100 : 0;
                  const achColor= ach>=95 ? "#10b981" : ach>=80 ? "#f59e0b" : "#ef4444";
                  const speedRatio= line.nominalSpeed>0 ? line.actualSpeed/line.nominalSpeed : 0;
                  return (
                    <tr key={line.id} style={{ background: idx%2===0 ? "#fff" : "#f8fafc", borderBottom:"1px solid #f1f5f9"}}>
                      <td style={tdStyle}><span style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"3px 8px", borderRadius:20, background: cm.color+"10", color: cm.color, fontSize:"0.72rem", fontWeight:700, border:`1px solid ${cm.color}18`}}><span style={{ width:6, height:6, borderRadius:"50%", background:cm.color}}/>{cm.label}</span></td>
                      <td style={tdStyle}><span style={{ display:"inline-flex", padding:"3px 8px", borderRadius:20, background: gm.color+"10", color: gm.color, fontSize:"0.72rem", fontWeight:600, border:`1px solid ${gm.color}14`}}>{gm.label}</span></td>
                      <td style={tdStyle}><strong style={{ color:"#0f172a", fontSize:"0.80rem"}}>{line.name}</strong></td>
                      <td style={tdStyle}>{line.product}</td>
                      <td style={tdStyle}><span style={{ display:"inline-flex", alignItems:"center", gap:5, color:meta.color, fontWeight:600, fontSize:"0.76rem"}}><span style={{ width:7, height:7, borderRadius:"50%", background:meta.dot, boxShadow: line.status==="running" ? `0 0 0 3px ${meta.dot}20` : "none"}}/>{meta.label}</span></td>
                      <td style={tdStyleNum}>{editMode && canManage ? <input type="number" min={0} defaultValue={line.planned} onChange={e=>setDraftPlanned(cur=>({...cur, [line.id]: Number(e.target.value)||0}))} style={{ width:80, padding:"4px 6px", border:"1px solid #0ea5e9", borderRadius:8, fontSize:"0.78rem", textAlign:"center"}}/> : fmtNum(line.planned)}</td>
                      <td style={tdStyleNum}><span style={{ fontWeight:600}}>{fmtNum(line.produced)}</span></td>
                      <td style={tdStyleNum}><span style={{ color: achColor, fontWeight:700, background: achColor+"10", padding:"2px 6px", borderRadius:20, fontSize:"0.76rem"}}>{fmtPct(ach)}</span></td>
                      <td style={tdStyleNum}><span style={{ color: cm.color, fontWeight:600, fontSize:"0.76rem"}}>{fmtPct(share)}</span></td>
                      <td style={tdStyleNum}><span style={{ color: speedRatio>=0.95 ? "#10b981" : speedRatio>=0.8 ? "#f59e0b" : "#ef4444", fontWeight:600}}>{fmtNum(line.actualSpeed)}</span><span style={{ color:"#94a3b8", fontSize:"0.70rem"}}>/{fmtNum(line.nominalSpeed)}</span></td>
                      <td style={tdStyleNum}><span style={{ color: line.stopMinutes==null ? "#cbd5e1" : "#64748b", fontSize:"0.76rem"}}>{fmtOptDur(line.stopMinutes)}</span></td>
                      <td style={tdStyleNum}><span style={{ color: line.wastePct==null ? "#cbd5e1" : "#64748b"}}>{fmtOptPct(line.wastePct)}</span></td>
                      <td style={tdStyleNum}><span style={{ color: line.oeePct==null ? "#cbd5e1" : "#0f172a", fontWeight: line.oeePct==null ? 400 : 600}}>{fmtOptPct(line.oeePct)}</span></td>
                      <td style={tdStyleNum}>{toPersianDigits(line.shift.toString())}</td>
                    </tr>
                  );
                })}
              </tbody>
              {visible.length>0 && (
                <tfoot><tr style={{ background:"#f0f9ff", borderTop:"2px solid #bae6fd"}}>
                  <td style={{ ...tdStyle, fontWeight:700, color:"#0c4a6e"}} colSpan={5}>جمع فیلتر شده</td>
                  <td style={{ ...tdStyleNum, fontWeight:700}}>{fmtNum(visibleTotals.planned)}</td>
                  <td style={{ ...tdStyleNum, fontWeight:700}}>{fmtNum(visibleTotals.produced)}</td>
                  <td style={{ ...tdStyleNum}}><span style={{ background:"#fff", border:"1px solid #bae6fd", padding:"2px 6px", borderRadius:20, fontWeight:700, color: visibleTotals.achievement>=90 ? "#10b981" : "#f59e0b"}}>{fmtPct(visibleTotals.achievement)}</span></td>
                  <td style={{ ...tdStyleNum, color:"#6366f1", fontWeight:600}}>{fmtPct(overall.totalProduced>0 ? (visibleTotals.produced/overall.totalProduced)*100 : 0)}</td>
                  <td style={tdStyleNum}>—</td><td style={tdStyleNum}>—</td><td style={tdStyleNum}>—</td><td style={tdStyleNum}>—</td><td style={tdStyleNum}>—</td>
                </tr></tfoot>
              )}
            </table>
          </div>
        </div>

        {/* Donuts - compact */}
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8}}>
            <span style={{ width:4, height:18, background:"#0f172a", borderRadius:99}}/>
            <h3 style={{ margin:0, fontSize:"0.90rem", fontWeight:700, color:"#0f172a"}}>سهم تولید</h3>
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(340px,1fr))", gap:10}}>
            <InteractiveDonutCard title="سهم شرکت‌ها از تولید" subtitle="بر اساس فیلتر فعلی" data={visible.length>0 ? (()=>{ const m=new Map<CompanyCode,number>(); visible.forEach(l=> m.set(l.company, (m.get(l.company)??0)+l.produced)); return Array.from(m.entries()).map(([k,v])=>{ const cm=(COMPANIES as any).find((c:any)=>c.key===k)!; return { key:k, label:cm.label, subLabel: `${toPersianDigits(visible.filter(l=>l.company===k).length.toString())} خط`, value:v, color:cm.color }; }); })() : (COMPANIES as any).map((cm:any)=>({ key:cm.key, label:cm.label, value:0, color:cm.color }))} totalLabel="عدد" />
            <InteractiveDonutCard title="سهم گروه‌ها از تولید" subtitle="قرص، ویال، سرنگ..." data={visible.length>0 ? (()=>{ const m=new Map<ProductGroup,number>(); visible.forEach(l=> m.set(l.group, (m.get(l.group)??0)+l.produced)); return Array.from(m.entries()).map(([k,v])=>{ const gm=GROUPS.find(g=>g.key===k)!; return { key:k, label:gm.label, value:v, color:gm.color }; }); })() : GROUPS.map(g=>({ key:g.key, label:g.label, value:0, color:g.color }))} totalLabel="عدد" />
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(340px,1fr))", gap:10, marginTop:10}}>
            <InteractiveDonutCard title="تولید به تفکیک محصول" subtitle="هر خط = یک برش" data={visible.map(l=> ({ key:l.id, label:l.product, subLabel: `${l.name}`, value:l.produced, color: GROUPS.find(g=>g.key===l.group)!.color }))} totalLabel="عدد" />
            <InteractiveDonutCard title="برنامه به تفکیک محصول" subtitle="سهم برنامه هر محصول" data={visible.map(l=> ({ key:l.id, label:l.product, subLabel:l.name, value:l.planned, color: GROUPS.find(g=>g.key===l.group)!.color }))} totalLabel="عدد" />
          </div>
        </div>
      </div>
    </div>
  );
}
export default ProductionPlanningDashboardPage;
