// گزارشنامه‌ی هفتگی‌ی کار — دستگاه‌محور، قابل چاپ برای مدیر (راست‌به‌چپ فارسی).
import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices, demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import {
  buildWeeklyCsv,
  filterOrdersInRange,
  groupOrdersByDevice,
  iranianWeekRange,
  summarizeWeek,
  weeklyReportFileName,
} from "../features/maintenance/workReports";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import type { MaintenanceDevice, WorkOrder } from "../shared/types/domain";
import { Badge, Button, Card, SectionHeader } from "../shared/components/primitives";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";
import { Toast } from "../shared/components/overlays";
import { formatJalali } from "../core/localization/jalali";

const downloadCsv = (content: string, fileName: string): void => {
  const blob = new Blob(["﻿" + content], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(link.href);
};

export default function MaintenanceWorkReportPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [orders, setOrders] = useState<WorkOrder[]>(runtimeConfig.demoMode ? demoWorkOrders : []);
  const [devices, setDevices] = useState<MaintenanceDevice[]>(runtimeConfig.demoMode ? demoDevices : []);
  const [weekOffset, setWeekOffset] = useState<0 | -1>(0);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (runtimeConfig.demoMode) return;
    Promise.all([service.listWorkOrders({}), service.listDevices({})])
      .then(([orderList, deviceList]) => {
        setOrders(orderList);
        setDevices(deviceList);
      })
      .catch(() => setToast("بارگذاری گزارش ناموفق بود."));
  }, [service, t]);

  const range = useMemo(() => {
    if (useCustom && customFrom && customTo) {
      return { fromIso: customFrom, toIso: customTo };
    }
    return iranianWeekRange(new Date(), weekOffset);
  }, [useCustom, customFrom, customTo, weekOffset]);

  const rangedOrders = useMemo(
    () => filterOrdersInRange(orders, range.fromIso, range.toIso),
    [orders, range],
  );

  const labelOfDevice = useCallback(
    (deviceId: string): string => {
      const device = devices.find((item) => item.id === deviceId);
      return device ? `${device.code} — ${device.name}` : deviceId;
    },
    [devices],
  );

  const groups = useMemo(() => groupOrdersByDevice(rangedOrders, labelOfDevice), [rangedOrders, labelOfDevice]);
  const summary = useMemo(() => summarizeWeek(rangedOrders), [rangedOrders]);

  const rangeLabel = useMemo(
    () => `${formatJalali(range.fromIso)} تا ${formatJalali(range.toIso)}`,
    [range],
  );

  const statusLabel = (status: string): string => t(`cmms.woStatus.${status}` as Parameters<typeof t>[0]);

  return (
    <div className="page weekly-report-page" dir="rtl">
      <SectionHeader
        eyebrow="CMMS"
        title="گزارشنامه‌ی هفتگی‌ی کار"
        subtitle={`جمع‌بندی اقدام‌ها بر اساس دستگاه — ${rangeLabel}`}
        actions={
          <>
            <Button variant="secondary" icon="download" onClick={() => downloadCsv(buildWeeklyCsv(groups, statusLabel), weeklyReportFileName(range.fromIso))}>
              خروجی CSV
            </Button>
            <Button variant="primary" icon="download" onClick={() => window.print()}>
              چاپ گزارش
            </Button>
          </>
        }
      />

      <Card padding="md" className="no-print">
        <div className="cmms-filter-row" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <Button
            variant={!useCustom && weekOffset === 0 ? "primary" : "secondary"}
            onClick={() => { setUseCustom(false); setWeekOffset(0); }}
          >
            هفته‌ی جاری
          </Button>
          <Button
            variant={!useCustom && weekOffset === -1 ? "primary" : "secondary"}
            onClick={() => { setUseCustom(false); setWeekOffset(-1); }}
          >
            هفته‌ی گذشته
          </Button>
          <span style={{ color: "var(--muted)", fontWeight: 700 }}>یا بازه‌ی دلخواه:</span>
          <JalaliDatePicker label="از تاریخ" value={customFrom} onChange={(v) => { setCustomFrom(v); setUseCustom(true); }} />
          <JalaliDatePicker label="تا تاریخ" value={customTo} onChange={(v) => { setCustomTo(v); setUseCustom(true); }} />
        </div>
      </Card>

      <div className="weekly-report-summary metric-grid">
        <Card padding="md"><span>کل اقدام‌ها</span><strong>{summary.totalOrders}</strong></Card>
        <Card padding="md"><span>تکمیل‌شده</span><strong>{summary.completedOrders}</strong></Card>
        <Card padding="md"><span>مجموع توقف</span><strong>{summary.totalDowntimeMinutes.toLocaleString()} دقیقه</strong></Card>
        <Card padding="md"><span>مجموع ساعت تعمیر</span><strong>{summary.totalLabourHours.toLocaleString()} ساعت</strong></Card>
        <Card padding="md"><span>هزینه‌ی کل (ریال)</span><strong>{summary.totalCost.toLocaleString()}</strong></Card>
      </div>

      {groups.length === 0 && (
        <Card padding="md">
          <p className="detail-panel__description">در این بازه‌ی زمانی اقدامی ثبت نشده است.</p>
        </Card>
      )}

      {groups.map((group) => (
        <Card key={group.deviceId} padding="none" className="weekly-report-device">
          <div className="weekly-report-device__header card__header" style={{ padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)" }}>
            <strong>{group.deviceLabel}</strong>
            <span className="weekly-report-device__meta">
              <Badge tone="neutral" dot>{group.totalCount} کار</Badge>{" "}
              <Badge tone="success" dot>{group.completedCount} تکمیل</Badge>{" "}
              <Badge tone="warning" dot>{group.totalDowntimeMinutes} دقیقه توقف</Badge>{" "}
              <Badge tone="purple" dot>{group.totalLabourHours} ساعت تعمیر</Badge>{" "}
              <Badge tone="neutral" dot>{group.totalRepairCost.toLocaleString()} ریال</Badge>
            </span>
          </div>
          <table className="weekly-report-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>عنوان اقدام</th>
                <th style={th}>نوع</th>
                <th style={th}>وضعیت</th>
                <th style={th}>ثبت</th>
                <th style={th}>توقف (د)</th>
                <th style={th}>ساعت تعمیر</th>
                <th style={th}>هزینه</th>
              </tr>
            </thead>
            <tbody>
              {group.orders.map((order) => (
                <tr key={order.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={td}>{order.title}</td>
                  <td style={td}>{t(`cmms.woType.${order.orderType}` as Parameters<typeof t>[0])}</td>
                  <td style={td}>
                    <Badge tone={order.status === "completed" ? "success" : order.status === "cancelled" ? "danger" : "neutral"} dot>
                      {statusLabel(order.status)}
                    </Badge>
                  </td>
                  <td style={td}>{formatJalali(order.createdAt)}</td>
                  <td style={td}>{order.downtimeMinutes ? order.downtimeMinutes.toLocaleString() : "—"}</td>
                  <td style={td}>{order.labourHours ? order.labourHours.toLocaleString() : "—"}</td>
                  <td style={td}>
                    {(order.labourCost || order.partsCost)
                      ? ((order.labourCost ?? 0) + (order.partsCost ?? 0)).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ))}

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "right", padding: "8px 14px", fontSize: 11, color: "var(--muted)" };
const td: React.CSSProperties = { textAlign: "right", padding: "9px 14px", fontSize: 12 };
