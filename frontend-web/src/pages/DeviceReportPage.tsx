import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import type {
  DeviceMaintenanceReport,
  Priority,
  WorkOrderStatus,
} from "../shared/types/domain";
import { Badge, Button, Card, MetricCard, SectionHeader, TextInput } from "../shared/components/primitives";
import { DonutChart } from "../shared/components/charts";
import { Toast } from "../shared/components/overlays";

const statusTone = (
  status: string,
): "success" | "info" | "warning" | "danger" | "neutral" | "purple" =>
  status === "completed"
    ? "success"
    : status === "inProgress"
      ? "info"
      : status === "onHold"
        ? "warning"
        : status === "pendingApproval"
          ? "purple"
          : status === "cancelled"
            ? "danger"
            : status === "assigned"
              ? "purple"
              : status === "routed"
                ? "info"
                : "neutral";

const priorityTone = (priority: string): "danger" | "warning" | "neutral" =>
  priority === "critical" ? "danger" : priority === "high" ? "warning" : "neutral";

const formatDateTime = (value: string, locale: string): string => {
  if (!value) return "";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(time),
  );
};

const triggerDownload = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export function DeviceReportPage(): JSX.Element {
  const { t, locale } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const { deviceId = "" } = useParams<{ deviceId: string }>();

  const [report, setReport] = useState<DeviceMaintenanceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal): Promise<void> => {
      if (!deviceId) return;
      setLoading(true);
      setError("");
      try {
        const result = await service.getDeviceReport(deviceId, { fromDate, toDate }, signal);
        setReport(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("cmms.report.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [deviceId, fromDate, toDate, service, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
    // Only auto-load on first mount; range changes are applied via the button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  const download = async (format: "csv" | "xlsx"): Promise<void> => {
    if (!report) return;
    setDownloading(true);
    try {
      const blob = await service.downloadDeviceReport(deviceId, format, { fromDate, toDate });
      triggerDownload(blob, `maintenance-report-${report.device.code}.${format}`);
    } catch (err) {
      setToast(err instanceof Error ? err.message : t("cmms.report.downloadFailed"));
    } finally {
      setDownloading(false);
    }
  };

  const summary = report?.summary ?? null;
  const completionRate =
    summary && summary.totalOrders > 0
      ? Math.round((summary.completedOrders / summary.totalOrders) * 100)
      : 0;

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={
          report ? `${t("cmms.report.title")} — ${report.device.name}` : t("cmms.report.title")
        }
        subtitle={t("cmms.report.subtitle")}
        actions={
          <div className="section-actions dash-actions--noprint">
            <Button variant="ghost" icon="arrowRight" onClick={() => navigate(-1)}>
              {t("cmms.common.back")}
            </Button>
            <Button
              variant="secondary"
              icon="download"
              onClick={() => void download("csv")}
              disabled={!report || downloading}
            >
              {t("cmms.report.exportCsv")}
            </Button>
            <Button
              variant="secondary"
              icon="table"
              onClick={() => void download("xlsx")}
              disabled={!report || downloading}
            >
              {t("cmms.report.exportExcel")}
            </Button>
            <Button
              variant="primary"
              icon="file"
              onClick={() => window.print()}
              disabled={!report}
            >
              {t("cmms.report.printPdf")}
            </Button>
          </div>
        }
      />

      <Card className="content-card dash-actions--noprint" padding="md">
        <div className="cmms-report-filter">
          <TextInput
            type="date"
            label={t("cmms.report.fromDate")}
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
          />
          <TextInput
            type="date"
            label={t("cmms.report.toDate")}
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
          />
          <Button variant="primary" icon="filter" onClick={() => void load()}>
            {t("cmms.report.applyRange")}
          </Button>
          {(fromDate || toDate) && (
            <Button
              variant="ghost"
              icon="close"
              onClick={() => {
                setFromDate("");
                setToDate("");
                void load();
              }}
            >
              {t("cmms.report.clearRange")}
            </Button>
          )}
        </div>
      </Card>

      {loading && <p className="detail-panel__description">{t("cmms.common.loading")}</p>}
      {error && !loading && <p className="detail-panel__description">{error}</p>}

      {report && !loading && (
        <div className="cmms-report">
          <div className="cmms-report__print-head">
            <h1>{t("cmms.report.title")}</h1>
            <p>
              {t("cmms.report.generatedAt")}: {formatDateTime(report.generatedAt, locale)}
            </p>
          </div>

          <Card className="content-card" padding="md">
            <h3 className="cmms-report__section-title">{t("cmms.report.deviceInfo")}</h3>
            <div className="detail-stats">
              <div>
                <span>{t("cmms.device.code")}</span>
                <strong>{report.device.code}</strong>
              </div>
              <div>
                <span>{t("cmms.device.name")}</span>
                <strong>{report.device.name}</strong>
              </div>
              <div>
                <span>{t("cmms.device.location")}</span>
                <strong>{report.device.location || t("cmms.common.none")}</strong>
              </div>
              <div>
                <span>{t("cmms.device.department")}</span>
                <strong>{t(`cmms.department.${report.device.department}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.device.status")}</span>
                <strong>{t(`cmms.status.${report.device.status}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.device.nextPm")}</span>
                <strong>{report.device.nextDueDate || t("cmms.common.none")}</strong>
              </div>
            </div>
          </Card>

          <div className="metric-grid">
            <MetricCard
              label={t("cmms.report.totalOrders")}
              value={summary?.totalOrders ?? 0}
              icon="checkSquare"
              tone="purple"
            />
            <MetricCard
              label={t("cmms.report.openOrders")}
              value={summary?.openOrders ?? 0}
              icon="activity"
              tone="amber"
            />
            <MetricCard
              label={t("cmms.report.overdueOrders")}
              value={summary?.overdueOrders ?? 0}
              icon="warning"
              tone="amber"
            />
            <MetricCard
              label={t("cmms.report.mttr")}
              value={summary?.mttrHours === null || summary === null ? t("cmms.common.none") : summary.mttrHours}
              icon="clock"
              tone="blue"
            />
          </div>

          <Card className="content-card" padding="md">
            <div className="cmms-report__completion">
              <DonutChart
                value={completionRate}
                label={`${completionRate}%`}
                color="#16a34a"
                ariaLabel={t("cmms.report.completionRate")}
              />
              <div>
                <h3 className="cmms-report__section-title">{t("cmms.report.completionRate")}</h3>
                <p className="detail-panel__description">
                  {t("cmms.report.completedOf")
                    .replace("{done}", String(summary?.completedOrders ?? 0))
                    .replace("{total}", String(summary?.totalOrders ?? 0))}
                </p>
              </div>
            </div>
          </Card>

          <Card className="content-card" padding="none">
            <div className="cmms-report__table-head">
              <h3 className="cmms-report__section-title">{t("cmms.report.orderList")}</h3>
            </div>
            {report.workOrders.length === 0 ? (
              <p className="detail-panel__description" style={{ padding: "0 16px 16px" }}>
                {t("cmms.report.noOrders")}
              </p>
            ) : (
              <div className="cmms-report__table-wrap">
                <table className="cmms-report__table">
                  <thead>
                    <tr>
                      <th>{t("cmms.wo.woTitle")}</th>
                      <th>{t("cmms.wo.type")}</th>
                      <th>{t("cmms.wo.priority")}</th>
                      <th>{t("cmms.wo.status")}</th>
                      <th>{t("cmms.wo.assignedTo")}</th>
                      <th>{t("cmms.wo.createdAt")}</th>
                      <th>{t("cmms.report.overdue")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.workOrders.map((order) => (
                      <tr key={order.id}>
                        <td>{order.title}</td>
                        <td>{t(`cmms.type.${order.orderType}`)}</td>
                        <td>
                          <Badge tone={priorityTone(order.priority as Priority)}>
                            {t(`cmms.priority.${order.priority}`)}
                          </Badge>
                        </td>
                        <td>
                          <Badge tone={statusTone(order.status as WorkOrderStatus)} dot>
                            {t(`cmms.woStatus.${order.status}`)}
                          </Badge>
                        </td>
                        <td>{order.assignedToName || t("cmms.common.none")}</td>
                        <td>{formatDateTime(order.createdAt, locale)}</td>
                        <td>
                          {order.overdue ? (
                            <Badge tone="danger">{t("cmms.report.yes")}</Badge>
                          ) : (
                            <span className="muted-cell">{t("cmms.report.no")}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
