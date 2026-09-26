import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { useApiClient } from "../core/api/apiContext";
import { formatJalali } from "../core/localization/jalali";
import { useLocalization } from "../core/localization/localizationContext";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices, demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import type { MaintenanceDevice, WorkOrder, WorkOrderStatus } from "../shared/types/domain";
import { BarChart } from "../shared/components/charts";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";
import { Badge, Button, Card, MetricCard, SectionHeader } from "../shared/components/primitives";
import { Toast } from "../shared/components/overlays";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";

const STATUS_ORDER: WorkOrderStatus[] = [
  "submitted",
  "routed",
  "assigned",
  "inProgress",
  "onHold",
  "pendingApproval",
  "completed",
  "cancelled",
];

const dateOnly = (value: string): string => value.slice(0, 10);

export function MaintenanceReportPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [orders, setOrders] = useState<WorkOrder[]>(runtimeConfig.demoMode ? demoWorkOrders : []);
  const [devices, setDevices] = useState<MaintenanceDevice[]>(runtimeConfig.demoMode ? demoDevices : []);
  const [fromDraft, setFromDraft] = useState("");
  const [toDraft, setToDraft] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [toast, setToast] = useState("");

  const load = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    setLoading(true);
    try {
      const [workOrders, deviceList] = await Promise.all([
        service.listWorkOrders(),
        service.listDevices(),
      ]);
      setOrders(workOrders);
      setDevices(deviceList);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "بارگذاری گزارش کلی ناموفق بود.");
    } finally {
      setLoading(false);
    }
  }, [service]);

  useEffect(() => {
    void load();
  }, [load]);

  const applyRange = (): void => {
    if (fromDraft && toDraft && fromDraft > toDraft) {
      setToast("تاریخ شروع گزارش نباید بعد از تاریخ پایان باشد.");
      return;
    }
    setFromDate(fromDraft);
    setToDate(toDraft);
  };

  const clearRange = (): void => {
    setFromDraft("");
    setToDraft("");
    setFromDate("");
    setToDate("");
  };

  const filteredOrders = useMemo(
    () =>
      orders.filter((order) => {
        const created = dateOnly(order.createdAt);
        return (!fromDate || created >= fromDate) && (!toDate || created <= toDate);
      }),
    [orders, fromDate, toDate],
  );

  const deviceNames = useMemo(
    () => new Map(devices.map((device) => [device.id, `${device.code} — ${device.name}`])),
    [devices],
  );

  const stats = useMemo(() => {
    const completed = filteredOrders.filter((order) => order.status === "completed").length;
    const cancelled = filteredOrders.filter((order) => order.status === "cancelled").length;
    const open = filteredOrders.length - completed - cancelled;
    const overdue = filteredOrders.filter((order) => Boolean(order.overdue)).length;
    return { total: filteredOrders.length, completed, open, overdue };
  }, [filteredOrders]);

  const byStatus = useMemo(
    () => STATUS_ORDER.map((status) => filteredOrders.filter((order) => order.status === status).length),
    [filteredOrders],
  );

  const columns = useMemo<DataTableColumn<WorkOrder>[]>(
    () => [
      {
        key: "title",
        label: "درخواست کار",
        accessor: (row) => row.title,
        sortable: true,
        render: (row) => <strong>{row.title}</strong>,
      },
      {
        key: "device",
        label: "دستگاه",
        accessor: (row) => deviceNames.get(row.deviceId) ?? row.deviceId,
      },
      {
        key: "type",
        label: "نوع",
        accessor: (row) => t(`cmms.type.${row.orderType}`),
        render: (row) => <Badge tone="info">{t(`cmms.type.${row.orderType}`)}</Badge>,
      },
      {
        key: "department",
        label: "واحد",
        accessor: (row) => taxonomyLabel(t, "cmms.department.", row.department),
      },
      {
        key: "status",
        label: "وضعیت",
        accessor: (row) => t(`cmms.woStatus.${row.status}`),
        render: (row) => <Badge tone={row.status === "completed" ? "success" : row.overdue ? "danger" : "neutral"}>{t(`cmms.woStatus.${row.status}`)}</Badge>,
      },
      {
        key: "createdAt",
        label: "تاریخ ایجاد",
        accessor: (row) => row.createdAt,
        sortable: true,
        render: (row) => <span>{formatJalali(row.createdAt, { style: "short" })}</span>,
      },
    ],
    [deviceNames, t],
  );

  return (
    <div className="page cmms-report" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title="گزارش کلی نگهداری و تعمیرات"
        subtitle="گزارش درخواست‌های کار همه دستگاه‌ها در بازه زمانی انتخابی"
        actions={
          <div className="cmms-header-actions dash-actions--noprint">
            <Button variant="secondary" icon="arrowRight" onClick={() => navigate("/app/maintenance/devices")}>دستگاه‌ها و PM</Button>
            <Button variant="primary" icon="file" onClick={() => window.print()}>چاپ / PDF</Button>
          </div>
        }
      />

      <Card className="content-card dash-actions--noprint" padding="md">
        <div className="cmms-report-filter">
          <div className="cmms-range-intro">
            <strong>بازه گزارش همه دستگاه‌ها</strong>
            <span>تمام درخواست‌های کار ایجادشده در این بازه را فیلتر می‌کند.</span>
          </div>
          <JalaliDatePicker label="درخواست‌ها از تاریخ" value={fromDraft} onChange={setFromDraft} />
          <JalaliDatePicker label="درخواست‌ها تا تاریخ" value={toDraft} onChange={setToDraft} />
          <Button variant="primary" icon="filter" onClick={applyRange}>اعمال فیلتر گزارش</Button>
          {(fromDate || toDate || fromDraft || toDraft) && (
            <Button variant="ghost" icon="close" onClick={clearRange}>پاک کردن فیلتر</Button>
          )}
        </div>
      </Card>

      <div className="metric-grid">
        <MetricCard label="کل درخواست‌ها" value={stats.total} icon="checkSquare" tone="purple" />
        <MetricCard label="درخواست‌های باز" value={stats.open} icon="activity" tone="blue" />
        <MetricCard label="تکمیل‌شده" value={stats.completed} icon="checkCircle" tone="green" />
        <MetricCard label="دارای تأخیر" value={stats.overdue} icon="warning" tone="amber" />
      </div>

      <Card className="dashboard-widget" padding="md">
        <h3 className="cmms-report__section-title">توزیع وضعیت درخواست‌ها</h3>
        <BarChart
          data={byStatus}
          labels={STATUS_ORDER.map((status) => t(`cmms.woStatus.${status}`))}
          color="#2878ff"
          ariaLabel="توزیع وضعیت درخواست‌های کار همه دستگاه‌ها"
        />
      </Card>

      <Card className="content-card" padding="none">
        {loading ? (
          <p className="detail-panel__description">{t("cmms.common.loading")}</p>
        ) : (
          <DataTable
            columns={columns}
            data={filteredOrders}
            rowKey={(row) => row.id}
            search=""
            exportName="tekarai-maintenance-all-devices"
            empty={{ title: "در این بازه هیچ درخواست کاری ثبت نشده است." }}
          />
        )}
      </Card>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
