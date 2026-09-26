import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { JALALI_MONTHS, gregorianToJalali, toPersianDigits } from "../core/localization/jalali";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices, demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import type {
  MaintenanceDepartment,
  MaintenanceDevice,
  Priority,
  WorkOrder,
  WorkOrderStatus,
} from "../shared/types/domain";
import { BarChart, DonutChart, TrendChart } from "../shared/components/charts";
import { Icon } from "../shared/components/Icon";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  MetricCard,
  ProgressBar,
  SectionHeader,
} from "../shared/components/primitives";

// Open (not yet closed) work-order statuses, in workflow order.
const OPEN_STATUSES: WorkOrderStatus[] = [
  "submitted",
  "routed",
  "assigned",
  "inProgress",
  "onHold",
];
const PRIORITIES: Priority[] = ["low", "normal", "high", "critical"];
const DEPARTMENTS: MaintenanceDepartment[] = [
  "general",
  "electrical",
  "mechanical",
  "facilities",
  "instrumentation",
];

const PRIORITY_COLORS: Record<Priority, string> = {
  low: "#64748b",
  normal: "#2878ff",
  high: "#e6a23c",
  critical: "#ef4444",
};

// Selectable look-back windows, in days. `0` means "all time".
type RangeKey = "7" | "30" | "90" | "all";
const RANGES: RangeKey[] = ["7", "30", "90", "all"];
const RANGE_DAYS: Record<RangeKey, number> = { "7": 7, "30": 30, "90": 90, all: 0 };

const DAY_MS = 86_400_000;

const isOpen = (status: WorkOrderStatus): boolean =>
  status !== "completed" && status !== "cancelled";

const parseDate = (value: string): number | null => {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
};

// Whole-day difference between two ISO date strings (createdAt → closedAt).
const daysBetween = (from: string, to: string): number | null => {
  const start = parseDate(from);
  const end = parseDate(to);
  if (start === null || end === null || end < start) return null;
  return Math.max(0, Math.round((end - start) / DAY_MS));
};

interface Bucket {
  label: string;
  start: number;
  end: number;
}

// Split a [from, to] window into `count` contiguous buckets for the trend charts.
const buildBuckets = (from: number, to: number, count: number): Bucket[] => {
  const span = Math.max(to - from, DAY_MS);
  const step = span / count;
  const label = (ms: number): string => {
    const d = new Date(ms);
    const [, jm, jd] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
    return toPersianDigits(`${jd} ${JALALI_MONTHS[jm - 1]}`);
  };
  return Array.from({ length: count }, (_, index) => {
    const start = from + index * step;
    const end = index === count - 1 ? to + 1 : from + (index + 1) * step;
    return { label: label(start), start, end };
  });
};

// Minimal, Excel-safe CSV: quote every field and escape embedded quotes.
const toCsvValue = (value: string | number): string =>
  `"${String(value).replace(/"/g, '""')}"`;

export function MaintenanceDashboardPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const navigate = useNavigate();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [orders, setOrders] = useState<WorkOrder[]>(
    runtimeConfig.demoMode ? demoWorkOrders : [],
  );
  const [devices, setDevices] = useState<MaintenanceDevice[]>(
    runtimeConfig.demoMode ? demoDevices : [],
  );
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [range, setRange] = useState<RangeKey>("30");

  const refresh = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    try {
      const [woList, deviceList] = await Promise.all([
        service.listWorkOrders(),
        service.listDevices().catch(() => [] as MaintenanceDevice[]),
      ]);
      setOrders(woList);
      setDevices(deviceList);
    } catch {
      /* keep last known state */
    } finally {
      setLoading(false);
    }
  }, [service]);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // The active window: orders created within it feed every metric and chart.
  const windowBounds = useMemo(() => {
    const now = Date.now();
    const days = RANGE_DAYS[range];
    if (days === 0) {
      const earliest = orders.reduce((min, order) => {
        const created = parseDate(order.createdAt);
        return created !== null && created < min ? created : min;
      }, now);
      return { from: Math.min(earliest, now - DAY_MS), to: now };
    }
    return { from: now - days * DAY_MS, to: now };
  }, [range, orders]);

  const rangedOrders = useMemo(
    () =>
      orders.filter((order) => {
        const created = parseDate(order.createdAt);
        return created !== null && created >= windowBounds.from && created <= windowBounds.to;
      }),
    [orders, windowBounds],
  );

  const stats = useMemo(() => {
    const scoped = rangedOrders;
    const total = scoped.length;
    const openOrders = scoped.filter((order) => isOpen(order.status));
    const completed = scoped.filter((order) => order.status === "completed");
    const cancelled = scoped.filter((order) => order.status === "cancelled");
    // Completion rate excludes cancelled work from the denominator.
    const resolvable = total - cancelled.length;
    const completionRate =
      resolvable > 0 ? Math.round((completed.length / resolvable) * 100) : 0;
    const duePm = devices.filter((device) => device.pmDue).length;

    const resolutionDays = completed
      .map((order) => daysBetween(order.createdAt, order.closedAt))
      .filter((value): value is number => value !== null);
    const mttr =
      resolutionDays.length > 0
        ? Math.round(
            (resolutionDays.reduce((sum, value) => sum + value, 0) /
              resolutionDays.length) *
              10,
          ) / 10
        : null;

    const byStatus = OPEN_STATUSES.map(
      (status) => openOrders.filter((order) => order.status === status).length,
    );
    // Priority breakdown, sorted ascending by count (1 → 4) as requested.
    const byPriorityRaw = PRIORITIES.map((priority) => ({
      priority,
      count: openOrders.filter((order) => order.priority === priority).length,
    }));
    const byPriority = [...byPriorityRaw].sort((a, b) => a.count - b.count);
    const byDepartment = DEPARTMENTS.map(
      (department) => openOrders.filter((order) => order.department === department).length,
    );

    return {
      total,
      open: openOrders.length,
      completed: completed.length,
      cancelled: cancelled.length,
      completionRate,
      duePm,
      mttr,
      byStatus,
      byPriority,
      byDepartment,
      criticalOpen: openOrders.filter((order) => order.priority === "critical").length,
    };
  }, [rangedOrders, devices]);

  // Trend: submitted (by createdAt) vs completed (by closedAt) across the window.
  const trend = useMemo(() => {
    const bucketCount = range === "7" ? 7 : 6;
    const buckets = buildBuckets(windowBounds.from, windowBounds.to, bucketCount);
    const submitted = buckets.map(
      (bucket) =>
        orders.filter((order) => {
          const created = parseDate(order.createdAt);
          return created !== null && created >= bucket.start && created < bucket.end;
        }).length,
    );
    const completed = buckets.map(
      (bucket) =>
        orders.filter((order) => {
          if (order.status !== "completed") return false;
          const closed = parseDate(order.closedAt);
          return closed !== null && closed >= bucket.start && closed < bucket.end;
        }).length,
    );
    // Average resolution time (days) for orders completed within each bucket.
    const mttr = buckets.map((bucket) => {
      const resolved = orders
        .filter((order) => {
          if (order.status !== "completed") return false;
          const closed = parseDate(order.closedAt);
          return closed !== null && closed >= bucket.start && closed < bucket.end;
        })
        .map((order) => daysBetween(order.createdAt, order.closedAt))
        .filter((value): value is number => value !== null);
      if (resolved.length === 0) return 0;
      return (
        Math.round(
          (resolved.reduce((sum, value) => sum + value, 0) / resolved.length) * 10,
        ) / 10
      );
    });
    const hasMttr = mttr.some((value) => value > 0);
    return { labels: buckets.map((bucket) => bucket.label), submitted, completed, mttr, hasMttr };
  }, [orders, windowBounds, range]);

  const hasData = orders.length > 0 || devices.length > 0;

  const goToOrders = useCallback(
    (params: { status?: WorkOrderStatus; department?: MaintenanceDepartment }): void => {
      const query = new URLSearchParams();
      if (params.status) query.set("status", params.status);
      if (params.department) query.set("department", params.department);
      const suffix = query.toString();
      navigate(`/app/maintenance/work-orders${suffix ? `?${suffix}` : ""}`);
    },
    [navigate],
  );

  const exportCsv = useCallback((): void => {
    const header = [
      t("cmms.wo.woTitle"),
      t("cmms.wo.status"),
      t("cmms.wo.priority"),
      t("cmms.wo.department"),
      t("cmms.wo.type"),
      t("cmms.wo.requestedBy"),
      t("cmms.wo.assignedTo"),
      t("cmms.wo.createdAt"),
      t("cmms.dash.csvClosedAt"),
    ];
    const rows = rangedOrders.map((order) => [
      order.title,
      t(`cmms.woStatus.${order.status}`),
      t(`cmms.priority.${order.priority}`),
      t(`cmms.department.${order.department}`),
      t(`cmms.type.${order.orderType}`),
      order.requestedByName,
      order.assignedToName,
      order.createdAt,
      order.closedAt,
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map(toCsvValue).join(","))
      .join("\r\n");
    // Prepend a BOM so Excel opens the Persian text as UTF-8.
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `maintenance-report-${range}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [rangedOrders, range, t]);

  return (
    <div className="page page--dashboard">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("cmms.dash.title")}
        subtitle={t("cmms.dash.subtitle")}
        actions={
          <div className="section-actions dash-actions--noprint">
            <Button variant="secondary" icon="refresh" onClick={() => void refresh()}>
              {t("cmms.dash.refresh")}
            </Button>
            <Button
              variant="secondary"
              icon="download"
              onClick={exportCsv}
              disabled={rangedOrders.length === 0}
            >
              {t("cmms.dash.exportCsv")}
            </Button>
            <Button variant="secondary" icon="file" onClick={() => window.print()}>
              {t("cmms.dash.print")}
            </Button>
            <Button
              variant="secondary"
              icon="chart"
              onClick={() => navigate("/app/maintenance/reports")}
            >
              گزارش کلی
            </Button>
            <Button
              variant="primary"
              icon="checkSquare"
              onClick={() => navigate("/app/maintenance/work-orders")}
            >
              {t("cmms.dash.openWorkOrders")}
            </Button>
          </div>
        }
      />

      <div className="dash-range-bar dash-actions--noprint">
        <span className="dash-range-bar__label">
          <Icon name="calendar" size={15} />
          {t("cmms.dash.rangeLabel")}
        </span>
        <div
          className="segmented-control"
          role="tablist"
          aria-label={t("cmms.dash.rangeLabel")}
        >
          {RANGES.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={range === key}
              className={range === key ? "is-active" : ""}
              onClick={() => setRange(key)}
            >
              {t(`cmms.dash.range.${key}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="metric-grid">
        <MetricCard
          label={t("cmms.dash.openWo")}
          value={stats.open}
          icon="checkSquare"
          tone="blue"
          trendLabel={t("cmms.dash.openWoHint", { critical: stats.criticalOpen })}
        />
        <MetricCard
          label={t("cmms.dash.duePm")}
          value={stats.duePm}
          icon="clock"
          tone="amber"
          trendLabel={t("cmms.dash.duePmHint")}
        />
        <MetricCard
          label={t("cmms.dash.completionRate")}
          value={`${stats.completionRate}%`}
          icon="checkCircle"
          tone="green"
          trendLabel={t("cmms.dash.completionHint", {
            done: stats.completed,
            total: stats.total,
          })}
        />
        <MetricCard
          label={t("cmms.dash.mttr")}
          value={stats.mttr === null ? t("cmms.common.none") : stats.mttr}
          icon="activity"
          tone="purple"
          trendLabel={t("cmms.dash.mttrHint")}
        />
      </div>

      {loading && !hasData ? (
        <Card padding="lg">
          <div className="state state--empty">
            <span className="state__icon">
              <Icon name="refresh" size={24} />
            </span>
            <h3>{t("cmms.dash.loading")}</h3>
          </div>
        </Card>
      ) : !hasData ? (
        <Card padding="lg">
          <div className="state state--empty">
            <span className="state__icon">
              <Icon name="chart" size={24} />
            </span>
            <h3>{t("cmms.dash.empty")}</h3>
            <Button
              variant="secondary"
              icon="plus"
              onClick={() => navigate("/app/maintenance/work-orders")}
            >
              {t("cmms.wo.new")}
            </Button>
          </div>
        </Card>
      ) : (
        <div className="widget-grid">
          <Card className="dashboard-widget dashboard-widget--wide" padding="md">
            <CardHeader
              title={t("cmms.dash.trend")}
              subtitle={t("cmms.dash.trendCaption")}
              icon="activity"
            />
            {stats.total === 0 ? (
              <div className="dash-chart-empty">{t("cmms.dash.rangeEmpty")}</div>
            ) : (
              <TrendChart
                series={[
                  {
                    label: t("cmms.dash.trendSubmitted"),
                    data: trend.submitted,
                    color: "#2878ff",
                  },
                  {
                    label: t("cmms.dash.trendCompleted"),
                    data: trend.completed,
                    color: "#22c55e",
                  },
                ]}
                labels={trend.labels}
                ariaLabel={t("cmms.dash.trend")}
              />
            )}
          </Card>

          <Card className="dashboard-widget dashboard-widget--wide" padding="md">
            <CardHeader
              title={t("cmms.dash.mttrTrend")}
              subtitle={t("cmms.dash.mttrTrendCaption")}
              icon="clock"
            />
            {!trend.hasMttr ? (
              <div className="dash-chart-empty">{t("cmms.dash.mttrTrendEmpty")}</div>
            ) : (
              <TrendChart
                series={[
                  {
                    label: t("cmms.dash.mttr"),
                    data: trend.mttr,
                    color: "#8b5cf6",
                  },
                ]}
                labels={trend.labels}
                ariaLabel={t("cmms.dash.mttrTrend")}
              />
            )}
          </Card>

          <Card className="dashboard-widget dashboard-widget--wide" padding="md">
            <CardHeader
              title={t("cmms.dash.byStatus")}
              subtitle={t("cmms.dash.byStatusHint")}
              icon="layers"
            />
            <BarChart
              data={stats.byStatus}
              labels={OPEN_STATUSES.map((status) => t(`cmms.woStatus.${status}`))}
              color="#2878ff"
              ariaLabel={t("cmms.dash.byStatus")}
              onBarClick={(index) => goToOrders({ status: OPEN_STATUSES[index] })}
            />
          </Card>

          <Card className="dashboard-widget" padding="md">
            <CardHeader
              title={t("cmms.dash.completionChart")}
              subtitle={t("cmms.dash.completionCaption")}
              icon="checkCircle"
            />
            <div className="health-widget">
              <DonutChart
                value={stats.completionRate}
                label={t("cmms.dash.donutLabel")}
                color="#22c55e"
                ariaLabel={t("cmms.dash.completionChart")}
              />
              <div className="health-widget__legend">
                <span>
                  <i className="legend-dot legend-dot--green" />
                  {t("cmms.woStatus.completed")} <strong>{stats.completed}</strong>
                </span>
                <span>
                  <i className="legend-dot legend-dot--blue" />
                  {t("cmms.dash.legendOpen")} <strong>{stats.open}</strong>
                </span>
                <span>
                  <i className="legend-dot legend-dot--amber" />
                  {t("cmms.woStatus.cancelled")} <strong>{stats.cancelled}</strong>
                </span>
              </div>
            </div>
          </Card>

          <Card className="dashboard-widget" padding="md">
            <CardHeader
              title={t("cmms.dash.byPriority")}
              subtitle={t("cmms.dash.byPriorityCaption")}
              icon="warning"
            />
            <BarChart
              data={stats.byPriority.map((entry) => entry.count)}
              labels={stats.byPriority.map((entry) => t(`cmms.priority.${entry.priority}`))}
              barColors={stats.byPriority.map((entry) => PRIORITY_COLORS[entry.priority])}
              ariaLabel={t("cmms.dash.byPriority")}
            />
            <div className="dash-priority-legend">
              {stats.byPriority.map((entry) => (
                <span key={entry.priority}>
                  <i
                    className="legend-dot"
                    style={{ background: PRIORITY_COLORS[entry.priority] }}
                  />
                  {t(`cmms.priority.${entry.priority}`)}
                  <strong>{entry.count}</strong>
                </span>
              ))}
            </div>
          </Card>

          <Card className="dashboard-widget dashboard-widget--wide" padding="md">
            <CardHeader
              title={t("cmms.dash.byDepartment")}
              subtitle={t("cmms.dash.byDepartmentHint")}
              icon="building"
            />
            <div className="dash-department-list">
              {DEPARTMENTS.map((department, index) => {
                const count = stats.byDepartment[index];
                const max = Math.max(...stats.byDepartment, 1);
                return (
                  <div
                    className="dash-department-row dash-department-row--clickable"
                    key={department}
                    role="button"
                    tabIndex={0}
                    onClick={() => goToOrders({ department })}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        goToOrders({ department });
                      }
                    }}
                  >
                    <span className="dash-department-row__name">
                      {t(`cmms.department.${department}`)}
                    </span>
                    <div className="dash-department-row__bar">
                      <ProgressBar
                        value={Math.round((count / max) * 100)}
                        tone={count > 0 ? "blue" : "purple"}
                        showValue={false}
                      />
                    </div>
                    <Badge tone={count > 0 ? "info" : "neutral"}>{count}</Badge>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
