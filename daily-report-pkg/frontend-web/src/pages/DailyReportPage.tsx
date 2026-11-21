import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../core/auth/authContext";
import { usePermissions, PERMISSIONS } from "../core/permissions/permissionContext";
import { useApiClient } from "../core/api/apiContext";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { toPersianDigits } from "../core/localization/jalali";
import { SectionHeader, Button, Badge, Card } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

// واحدهای فنی - مطابق OrganizationDepartment
const UNITS = [
  { code: "ENG_ROOT", label: "فنی و مهندسی", color: "#0f766e" },
  { code: "ENG_MECH", label: "مکانیک و طراحی", color: "#0369a1" },
  { code: "ENG_PROJ", label: "واحد پروژه", color: "#7c3aed" },
  { code: "ENG_JAM", label: "فنی جامدات", color: "#be123c" },
  { code: "ENG_TAZ", label: "فنی تزریقی", color: "#15803d" },
  { code: "ENG_FREEZE", label: "فریزدرایر", color: "#0e7490" },
  { code: "ENG_ELEC", label: "برق و اتوماسیون", color: "#c2410c" },
  { code: "ENG_HVAC", label: "تاسیسات و تهویه", color: "#1d4ed8" },
  { code: "ENG_MAINT", label: "نگهداری و تعمیرات", color: "#a16207" },
];

const SHIFTS = [
  { value: "morning", label: "شیفت صبح" },
  { value: "evening", label: "شیفت عصر" },
  { value: "night", label: "شیفت شب" },
];

type ReportStatus = "pending" | "approved" | "rejected";

interface DailyReport {
  id: string;
  tenantId: string;
  department: string;
  title: string;
  description: string;
  status: ReportStatus;
  priority: string;
  createdAt: string;
  requestedByName: string;
  requestedByUserId: string;
  orgDepartmentId?: string;
  workDone?: string;
  problems?: string;
  actions?: string;
  shift?: string;
  reportDate?: string;
}

export function DailyReportPage(): JSX.Element {
  const api = useApiClient();
  const { session } = useAuth();
  const { has } = usePermissions();
  const canCreate = has(PERMISSIONS.maintenanceWorkOrderCreate);
  const canApprove = has(PERMISSIONS.maintenanceWorkOrderApprove);
  
  const [selectedUnit, setSelectedUnit] = useState<string>("ENG_TAZ");
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [filterStatus, setFilterStatus] = useState<ReportStatus | "all">("all");
  const [dateFilter, setDateFilter] = useState<string>("");

  // User's unit for filtering (from session assignment)
  const userDepartment = (session as any)?.user?.departmentCode || null;
  const userRoleCode = (session as any)?.user?.roleCode || "";
  const isSpecialist = userRoleCode === "tech_specialist" || userRoleCode === "tech_facility";
  const isManager = userRoleCode === "tech_director" || userRoleCode === "tech_head" || userRoleCode === "tech_supervisor";

  // Form state
  const [form, setForm] = useState({
    reportDate: new Date().toISOString().slice(0, 10),
    shift: "morning",
    workDone: "",
    problems: "",
    actions: "",
  });

  const service = useMemo(() => createMaintenanceService(api), [api]);

  const loadReports = async () => {
    setLoading(true);
    try {
      // Use workOrders as daily reports (orderType: dailyReport) - filtered by department
      const data = await service.listWorkOrders({ 
        department: selectedUnit,
        search: "گزارش روزانه",
      } as any);
      // Filter client-side for daily reports of this unit
      const filtered = (data as any[]).filter((r: any) => 
        r.title?.includes("گزارش روزانه") && r.department === selectedUnit
      );
      setReports(filtered);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, [selectedUnit]);

  const handleCreate = async () => {
    if (!form.workDone.trim()) return;
    const selectedUnitLabel = UNITS.find(u => u.code === selectedUnit)?.label || selectedUnit;
    const shiftLabel = SHIFTS.find(s => s.value === form.shift)?.label || form.shift;
    try {
      await (service as any).createWorkOrder({
        title: `گزارش روزانه ${selectedUnitLabel} - ${form.reportDate} ${shiftLabel}`,
        description: `شیفت: ${shiftLabel}\nتاریخ: ${form.reportDate}\n\nکار انجام شده:\n${form.workDone}\n\nمشکلات:\n${form.problems || "—"}\n\nاقدامات:\n${form.actions || "—"}`,
        department: selectedUnit,
        orderType: "dailyReport",
        priority: "normal",
        deviceId: "00000000-0000-0000-0000-000000000000", // dummy for daily report
      });
      setShowCreate(false);
      setForm({ reportDate: new Date().toISOString().slice(0, 10), shift: "morning", workDone: "", problems: "", actions: "" });
      loadReports();
    } catch (e) {
      alert("خطا در ثبت گزارش");
    }
  };

  const handleApprove = async (id: string, approve: boolean) => {
    try {
      await (service as any).updateWorkOrder(id, { 
        status: approve ? "approved" : "rejected",
        resolutionNote: approve ? "تایید شد" : "رد شد"
      });
      loadReports();
    } catch (e) {
      alert("خطا در تایید");
    }
  };

  const filteredReports = reports.filter(r => {
    if (filterStatus !== "all" && r.status !== filterStatus) return false;
    if (dateFilter && !r.createdAt.includes(dateFilter)) return false;
    return true;
  });

  const unitColor = UNITS.find(u => u.code === selectedUnit)?.color || "#0f766e";

  return (
    <div style={{ padding: "16px", maxWidth: "1200px", margin: "0 auto", fontFamily: "Vazirmatn, system-ui" }} dir="rtl">
      <SectionHeader
        title="گزارش روزانه"
        subtitle="هر واحد گزارش خود را ثبت می‌کند — تایید نهایی فقط با سرپرست و رییس همان واحد"
        icon="clipboard"
      />

      {/* Unit Tabs - Horizontal scroll */}
      <div style={{ 
        display: "flex", gap: "8px", overflowX: "auto", padding: "12px 0",
        borderBottom: "2px solid #e5e7eb", marginBottom: "16px",
        scrollbarWidth: "thin"
      }}>
        {UNITS.map(unit => (
          <button
            key={unit.code}
            onClick={() => setSelectedUnit(unit.code)}
            style={{
              padding: "8px 16px",
              borderRadius: "20px",
              border: "none",
              background: selectedUnit === unit.code ? unit.color : "#f3f4f6",
              color: selectedUnit === unit.code ? "white" : "#374151",
              fontWeight: selectedUnit === unit.code ? 700 : 400,
              fontSize: "13px",
              whiteSpace: "nowrap",
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            {unit.label}
          </button>
        ))}
      </div>

      {/* Filters & Create */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value as any)} style={{ padding: "6px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px" }}>
            <option value="all">همه وضعیت‌ها</option>
            <option value="pending">در انتظار تایید</option>
            <option value="approved">تایید شده</option>
            <option value="rejected">رد شده</option>
          </select>
          <input type="date" value={dateFilter} onChange={e => setDateFilter(e.target.value)} style={{ padding: "6px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px" }} />
          {(filterStatus !== "all" || dateFilter) && (
            <button onClick={() => { setFilterStatus("all"); setDateFilter(""); }} style={{ padding: "6px 12px", background: "#fee2e2", border: "none", borderRadius: "8px", fontSize: "12px", cursor: "pointer" }}>پاک کردن فیلتر</button>
          )}
        </div>
        {canCreate && (
          <Button onClick={() => setShowCreate(true)} style={{ background: unitColor, color: "white" }}>
            <Icon name="plus" size={16} /> ثبت گزارش روزانه
          </Button>
        )}
      </div>

      {/* Info banner for specialist */}
      {isSpecialist && (
        <div style={{ background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", fontSize: "13px", display: "flex", gap: "8px", alignItems: "center" }}>
          <Icon name="info" size={16} /> 
          <span>شما فقط مجاز به ثبت گزارش برای <strong>{UNITS.find(u => u.code === userDepartment)?.label || "واحد خود"}</strong> هستید — تایید با سرپرست/رییس واحد.</span>
        </div>
      )}

      {/* Reports List */}
      {loading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "#6b7280" }}>در حال بارگذاری...</div>
      ) : filteredReports.length === 0 ? (
        <Card style={{ padding: "40px", textAlign: "center", background: "#f9fafb" }}>
          <Icon name="inbox" size={32} style={{ opacity: 0.3, marginBottom: "12px" }} />
          <div style={{ color: "#6b7280", fontSize: "14px" }}>هنوز گزارشی برای {UNITS.find(u => u.code === selectedUnit)?.label} ثبت نشده</div>
          <div style={{ color: "#9ca3af", fontSize: "12px", marginTop: "4px" }}>اولین گزارش روزانه را ثبت کنید</div>
        </Card>
      ) : (
        <div style={{ display: "grid", gap: "12px" }}>
          {filteredReports.map(report => (
            <Card key={report.id} style={{ padding: "16px", borderRight: `4px solid ${unitColor}`, background: "white" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: "14px", marginBottom: "4px" }}>{report.title}</div>
                  <div style={{ fontSize: "13px", color: "#4b5563", whiteSpace: "pre-wrap", lineHeight: "1.6", maxHeight: "80px", overflow: "hidden" }}>
                    {report.description.slice(0, 200)}{report.description.length > 200 ? "..." : ""}
                  </div>
                  <div style={{ display: "flex", gap: "12px", marginTop: "8px", fontSize: "12px", color: "#6b7280" }}>
                    <span>👤 {report.requestedByName}</span>
                    <span>📅 {toPersianDigits(new Date(report.createdAt).toLocaleDateString("fa-IR"))}</span>
                    <Badge style={{ background: report.status === "approved" ? "#dcfce7" : report.status === "rejected" ? "#fee2e2" : "#fef3c7", color: report.status === "approved" ? "#166534" : report.status === "rejected" ? "#991b1b" : "#92400e", fontSize: "11px" }}>
                      {report.status === "pending" ? "در انتظار تایید" : report.status === "approved" ? "تایید شد" : "رد شد"}
                    </Badge>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  {canApprove && report.status === "pending" && (isManager || selectedUnit === userDepartment) && (
                    <>
                      <Button size="sm" onClick={() => handleApprove(report.id, true)} style={{ background: "#16a34a", color: "white", fontSize: "12px", padding: "6px 12px" }}>تایید</Button>
                      <Button size="sm" onClick={() => handleApprove(report.id, false)} style={{ background: "#dc2626", color: "white", fontSize: "12px", padding: "6px 12px" }}>رد</Button>
                    </>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => alert(report.description)} style={{ fontSize: "12px" }}>جزئیات</Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: "16px" }} onClick={() => setShowCreate(false)}>
          <div onClick={e => e.stopPropagation()} style={{ background: "white", borderRadius: "12px", padding: "20px", width: "100%", maxWidth: "600px", maxHeight: "90vh", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid #e5e7eb", paddingBottom: "12px" }}>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: unitColor }}>ثبت گزارش روزانه — {UNITS.find(u => u.code === selectedUnit)?.label}</h3>
              <button onClick={() => setShowCreate(false)} style={{ background: "#f3f4f6", border: "none", borderRadius: "50%", width: "28px", height: "28px", cursor: "pointer" }}>✕</button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              <div style={{ display: "flex", gap: "12px" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: "12px", color: "#374151", fontWeight: 600, display: "block", marginBottom: "4px" }}>تاریخ *</label>
                  <input type="date" value={form.reportDate} onChange={e => setForm({...form, reportDate: e.target.value})} style={{ width: "100%", padding: "8px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px" }} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: "12px", color: "#374151", fontWeight: 600, display: "block", marginBottom: "4px" }}>شیفت *</label>
                  <select value={form.shift} onChange={e => setForm({...form, shift: e.target.value})} style={{ width: "100%", padding: "8px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px" }}>
                    {SHIFTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label style={{ fontSize: "12px", color: "#374151", fontWeight: 600, display: "block", marginBottom: "4px" }}>کار انجام شده *</label>
                <textarea value={form.workDone} onChange={e => setForm({...form, workDone: e.target.value})} rows={3} placeholder="مثلا: تعمیر پمپ خط ۲، کالیبراسیون..." style={{ width: "100%", padding: "8px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px", resize: "vertical" }} />
              </div>
              <div>
                <label style={{ fontSize: "12px", color: "#374151", fontWeight: 600, display: "block", marginBottom: "4px" }}>مشکلات</label>
                <textarea value={form.problems} onChange={e => setForm({...form, problems: e.target.value})} rows={2} placeholder="مشکل مشاهده شده (اختیاری)" style={{ width: "100%", padding: "8px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px", resize: "vertical" }} />
              </div>
              <div>
                <label style={{ fontSize: "12px", color: "#374151", fontWeight: 600, display: "block", marginBottom: "4px" }}>اقدامات / پیشنهادات</label>
                <textarea value={form.actions} onChange={e => setForm({...form, actions: e.target.value})} rows={2} placeholder="اقدام بعدی یا پیشنهاد (اختیاری)" style={{ width: "100%", padding: "8px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "13px", resize: "vertical" }} />
              </div>
              <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "8px" }}>
                <Button variant="ghost" onClick={() => setShowCreate(false)}>انصراف</Button>
                <Button onClick={handleCreate} disabled={!form.workDone.trim()} style={{ background: unitColor, color: "white", opacity: !form.workDone.trim() ? 0.5 : 1 }}>ثبت گزارش</Button>
              </div>
              <div style={{ fontSize: "11px", color: "#6b7280", background: "#f9fafb", padding: "8px", borderRadius: "6px" }}>
                ℹ️ این گزارش برای <strong>{UNITS.find(u => u.code === selectedUnit)?.label}</strong> ثبت می‌شود و فقط سرپرست/رییس همان واحد می‌تواند تایید نهایی کند.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default DailyReportPage;
