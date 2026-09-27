import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { apiEndpoints } from "../core/api/endpoints";
import { useFeatureFlags } from "../core/flags/featureFlags";
import { useLocalization } from "../core/localization/localizationContext";
import { toPersianDigits } from "../core/localization/jalali";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { demoActivity, demoProjects, demoTasks } from "../features/demo/demoData";
import { demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import { createProjectService } from "../features/projects/projectService";
import { createTaskService } from "../features/tasks/taskService";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { ActivityFeed } from "../shared/components/featureComponents";
import { BarChart, DonutChart } from "../shared/components/charts";
import { Icon } from "../shared/components/Icon";
import { Button, Card, CardHeader, MetricCard, PermissionGuard, ProgressBar, SectionHeader, StatusBadge } from "../shared/components/primitives";
import type { ActivityItem, Project, Task, WorkOrder } from "../shared/types/domain";

interface WidgetConfig { id: string; title: string; kind: "pulse" | "throughput" | "activity" | "health"; size: "wide" | "half"; }

const defaultWidgets: WidgetConfig[] = [
  { id: "pulse", title: "Project pulse", kind: "pulse", size: "wide" },
  { id: "throughput", title: "Task throughput", kind: "throughput", size: "half" },
  { id: "activity", title: "Recent activity", kind: "activity", size: "half" },
  { id: "health", title: "Health by domain", kind: "health", size: "half" },
];

const isOpenOrder = (order: WorkOrder): boolean => order.status !== "completed" && order.status !== "cancelled";

const WIDGETS_STORAGE_KEY = "tekarai.dashboard.widgets.v1";

/** Persist the dashboard layout (order + visibility) per browser profile. */
function loadWidgets(): WidgetConfig[] {
  try {
    const raw = window.localStorage.getItem(WIDGETS_STORAGE_KEY);
    if (!raw) return defaultWidgets;
    const parsed = JSON.parse(raw) as WidgetConfig[];
    const validIds = new Set(defaultWidgets.map((widget) => widget.id));
    const restored = parsed.filter((widget) => validIds.has(widget.id));
    const missing = defaultWidgets.filter((widget) => !restored.some((item) => item.id === widget.id));
    return [...restored, ...missing];
  } catch {
    return defaultWidgets;
  }
}

function saveWidgets(widgets: WidgetConfig[]): void {
  try {
    window.localStorage.setItem(WIDGETS_STORAGE_KEY, JSON.stringify(widgets));
  } catch {
    // Quota errors (private mode) must never break the dashboard.
  }
}

/** Tolerant mapper for /platform/audit-events rows (shape varies by phase). */
const toActivityItem = (row: Record<string, unknown>, index: number): ActivityItem => ({
  id: String(row.id ?? row.eventId ?? index),
  actor: String(row.actorName ?? row.actor ?? row.actorUserId ?? "system"),
  action: String(row.action ?? row.eventName ?? row.operation ?? "activity"),
  resource: String(row.resource ?? row.resourceType ?? ""),
  timestamp: String(row.timestamp ?? row.occurredAt ?? row.createdAt ?? ""),
  tone: (["blue", "green", "amber", "purple"] as const)[index % 4],
});

export function DashboardPage(): JSX.Element {
  const { t, locale } = useLocalization();
  const { isEnabled } = useFeatureFlags();
  const api = useApiClient();
  const navigate = useNavigate();
  const projectService = useMemo(() => createProjectService(api), [api]);
  const taskService = useMemo(() => createTaskService(api), [api]);
  const maintenanceService = useMemo(() => createMaintenanceService(api), [api]);

  const [customizing, setCustomizing] = useState(false);
  const [widgets, setWidgets] = useState<WidgetConfig[]>(loadWidgets);

  useEffect(() => {
    saveWidgets(widgets);
  }, [widgets]);

  // Real server data in live mode; curated demo data when demoMode is on.
  const [projects, setProjects] = useState<Project[]>(runtimeConfig.demoMode ? demoProjects : []);
  const [tasks, setTasks] = useState<Task[]>(runtimeConfig.demoMode ? demoTasks : []);
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>(runtimeConfig.demoMode ? demoWorkOrders : []);
  const [activity, setActivity] = useState<ActivityItem[]>(runtimeConfig.demoMode ? demoActivity : []);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);

  const refresh = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    setLoading(true);
    // Every source loads independently — one failing endpoint must not blank the page.
    const [projectRows, taskRows, orderRows, auditRows] = await Promise.allSettled([
      projectService.list(),
      taskService.list(),
      maintenanceService.listWorkOrders(),
      api.get<Array<Record<string, unknown>>>(apiEndpoints.audit, { query: { pageSize: 8 } }),
    ]);
    if (projectRows.status === "fulfilled") setProjects(projectRows.value);
    if (taskRows.status === "fulfilled") setTasks(taskRows.value);
    if (orderRows.status === "fulfilled") setWorkOrders(orderRows.value);
    if (auditRows.status === "fulfilled") setActivity(auditRows.value.slice(0, 4).map(toActivityItem));
    setLoading(false);
  }, [api, projectService, taskService, maintenanceService]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activeProjects = projects.filter((project) => project.status !== "completed" && project.status !== "archived").length;
  const openTasks = tasks.filter((task) => task.status !== "done").length;
  const openWorkOrders = workOrders.filter(isOpenOrder).length;
  const averageHealth = projects.length ? Math.round(projects.reduce((sum, project) => sum + project.health, 0) / projects.length) : null;
  const healthLabel = averageHealth === null ? "—" : `${locale === "fa" ? toPersianDigits(averageHealth) : averageHealth}%`;

  const statusCounts = useMemo(() => {
    const buckets: Record<string, number> = { backlog: 0, inProgress: 0, review: 0, done: 0 };
    tasks.forEach((task) => {
      buckets[task.status] = (buckets[task.status] ?? 0) + 1;
    });
    return buckets;
  }, [tasks]);
  const throughputData = [statusCounts.backlog, statusCounts.inProgress, statusCounts.review, statusCounts.done];
  const throughputLabels = [
    t("dashboard.taskStatus.backlog"),
    t("common.status.inProgress"),
    t("dashboard.taskStatus.review"),
    t("common.status.completed"),
  ];

  const onTrackCount = projects.filter((project) => project.status === "active" || project.status === "inProgress").length;
  const atRiskCount = projects.filter((project) => project.status === "atRisk").length;
  const completedCount = projects.filter((project) => project.status === "completed").length;

  const widgetTitle = useMemo(() => (widget: WidgetConfig): string => widget.kind === "pulse" ? t("dashboard.projectPulse") : widget.kind === "throughput" ? t("dashboard.taskThroughput") : widget.kind === "activity" ? t("dashboard.activity") : t("dashboard.healthScore"), [t]);
  const removeWidget = (id: string): void => setWidgets((current) => current.filter((widget) => widget.id !== id));
  const moveWidget = (id: string, direction: -1 | 1): void => setWidgets((current) => {
    const index = current.findIndex((widget) => widget.id === id);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return current;
    const next = [...current];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    return next;
  });

  return <div className="page page--dashboard">
    <SectionHeader
      eyebrow={t("nav.workspace")}
      title={t("dashboard.title")}
      subtitle={t("dashboard.subtitle")}
      actions={<div className="section-actions"><span className="updated-label"><span className="live-dot" />{loading ? "…" : t("dashboard.lastUpdated")}</span>{isEnabled("dashboardCustomization") && <Button variant={customizing ? "primary" : "secondary"} icon={customizing ? "check" : "settings"} onClick={() => setCustomizing((value) => !value)}>{customizing ? t("dashboard.done") : t("dashboard.customize")}</Button>}</div>}
    />
    <div className="metric-grid">
      <MetricCard label={t("dashboard.activeProjects")} value={locale === "fa" ? toPersianDigits(activeProjects) : activeProjects} icon="briefcase" tone="blue" />
      <MetricCard label={t("dashboard.openTasks")} value={locale === "fa" ? toPersianDigits(openTasks) : openTasks} icon="checkSquare" tone="purple" />
      <MetricCard label={t("dashboard.openWorkOrders")} value={locale === "fa" ? toPersianDigits(openWorkOrders) : openWorkOrders} icon="activity" tone="green" />
      <MetricCard label={t("dashboard.healthScore")} value={healthLabel} icon="chart" tone="amber" />
    </div>
    <div className="quick-actions">
      <span className="quick-actions__label">{t("dashboard.quickActions")}</span>
      <PermissionGuard permission={PERMISSIONS.projectCreate}><Button variant="subtle" size="sm" icon="plus" onClick={() => navigate("/app/projects?create=1")}>{t("dashboard.newProject")}</Button></PermissionGuard>
      <PermissionGuard permission={PERMISSIONS.taskCreate}><Button variant="subtle" size="sm" icon="checkSquare" onClick={() => navigate("/app/tasks?create=1")}>{t("dashboard.newTask")}</Button></PermissionGuard>
      <PermissionGuard permission={PERMISSIONS.documentUpload}><Button variant="subtle" size="sm" icon="upload" onClick={() => navigate("/app/documents?upload=1")}>{t("dashboard.uploadDocument")}</Button></PermissionGuard>
      {isEnabled("projectIntelligence") && <PermissionGuard permission={PERMISSIONS.intelligenceAnalyze}><Button variant="subtle" size="sm" icon="sparkles" onClick={() => navigate("/app/intelligence")}>{t("dashboard.runAnalysis")}</Button></PermissionGuard>}
    </div>
    {customizing && <div className="customize-banner" role="status"><Icon name="settings" size={17} /><span>{t("dashboard.customizeBanner")}</span><Button variant="primary" size="sm" icon="check" onClick={() => setCustomizing(false)}>{t("dashboard.done")}</Button></div>}
    {loading ? (
      <Card padding="lg"><div className="state state--loading"><span className="spinner" /><span>{t("dashboard.loading")}</span></div></Card>
    ) : widgets.length === 0 ? (
      <Card padding="none"><div className="state state--empty"><span className="state__icon"><Icon name="grid" size={24} /></span><h3>{t("dashboard.noWidgets")}</h3><Button variant="secondary" icon="refresh" onClick={() => setWidgets(defaultWidgets)}>{t("dashboard.restoreWidgets")}</Button></div></Card>
    ) : (
      <div className="widget-grid">
        {widgets.map((widget, index) => (
          <Card key={widget.id} className={`dashboard-widget dashboard-widget--${widget.size}`} padding="md">
            <CardHeader
              title={widgetTitle(widget)}
              subtitle={widget.kind === "pulse" ? t("dashboard.projectPulseCaption") : widget.kind === "throughput" ? t("dashboard.taskThroughputCaption") : undefined}
              action={customizing ? <div className="widget-controls"><button type="button" aria-label="جابه‌جایی کارت به بالا" disabled={index === 0} onClick={() => moveWidget(widget.id, -1)}><Icon name="arrowUp" size={14} /></button><button type="button" aria-label="جابه‌جایی کارت به پایین" disabled={index === widgets.length - 1} onClick={() => moveWidget(widget.id, 1)}><Icon name="arrowDown" size={14} /></button><button type="button" aria-label="حذف کارت" onClick={() => removeWidget(widget.id)}><Icon name="close" size={14} /></button></div> : <button type="button" className="card-kebab" aria-label={t("common.more")}><Icon name="more" size={17} /></button>}
            />
            {widget.kind === "pulse" && (
              projects.length === 0
                ? <div className="dash-chart-empty">{t("dashboard.emptyNote")}</div>
                : <div className="project-pulse">{projects.slice(0, 4).map((project) => <div className="pulse-row" key={project.id}><div className="pulse-row__name"><span className="project-dot" style={{ backgroundColor: project.color }} /> <strong>{project.name}</strong><StatusBadge status={project.status} /></div><div className="pulse-row__progress"><ProgressBar value={project.progress} tone={project.status === "atRisk" ? "amber" : project.status === "completed" ? "green" : "blue"} /><span>{locale === "fa" ? toPersianDigits(project.progress) : project.progress}%</span></div></div>)}</div>
            )}
            {widget.kind === "throughput" && (
              tasks.length === 0
                ? <div className="dash-chart-empty">{t("dashboard.emptyNote")}</div>
                : <BarChart data={throughputData} labels={throughputLabels} color="#8b5cf6" ariaLabel={t("dashboard.taskThroughput")} />
            )}
            {widget.kind === "activity" && (
              activity.length === 0
                ? <div className="dash-chart-empty">{t("dashboard.emptyNote")}</div>
                : <ActivityFeed items={activity} compact />
            )}
            {widget.kind === "health" && (
              averageHealth === null
                ? <div className="dash-chart-empty">{t("dashboard.emptyNote")}</div>
                : <div className="health-widget"><DonutChart value={averageHealth} label={t("dashboard.healthScore")} color="#e6a23c" ariaLabel={t("dashboard.healthScore")} /><div className="health-widget__legend"><span><i className="legend-dot legend-dot--green" />{t("common.status.inProgress")} <strong>{locale === "fa" ? toPersianDigits(onTrackCount) : onTrackCount}</strong></span><span><i className="legend-dot legend-dot--amber" />{t("common.status.atRisk")} <strong>{locale === "fa" ? toPersianDigits(atRiskCount) : atRiskCount}</strong></span><span><i className="legend-dot legend-dot--purple" />{t("common.status.completed")} <strong>{locale === "fa" ? toPersianDigits(completedCount) : completedCount}</strong></span></div></div>
            )}
          </Card>
        ))}
      </div>
    )}
  </div>;
}
