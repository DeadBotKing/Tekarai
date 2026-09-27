import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useFeatureFlags } from "../core/flags/featureFlags";
import { useLocalization } from "../core/localization/localizationContext";
import { JALALI_WEEKDAYS, toPersianDigits } from "../core/localization/jalali";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoActivity, demoProjects, demoTasks } from "../features/demo/demoData";
import { ActivityFeed } from "../shared/components/featureComponents";
import { BarChart, DonutChart } from "../shared/components/charts";
import { Icon } from "../shared/components/Icon";
import { Button, Card, CardHeader, MetricCard, PermissionGuard, ProgressBar, SectionHeader, StatusBadge } from "../shared/components/primitives";

interface WidgetConfig { id: string; title: string; kind: "pulse" | "throughput" | "activity" | "health"; size: "wide" | "half"; }

const defaultWidgets: WidgetConfig[] = [
  { id: "pulse", title: "Project pulse", kind: "pulse", size: "wide" },
  { id: "throughput", title: "Task throughput", kind: "throughput", size: "half" },
  { id: "activity", title: "Recent activity", kind: "activity", size: "half" },
  { id: "health", title: "Health by domain", kind: "health", size: "half" },
];

export function DashboardPage(): JSX.Element {
  const { t, locale } = useLocalization();
  const { isEnabled } = useFeatureFlags();
  const navigate = useNavigate();
  const [customizing, setCustomizing] = useState(false);
  const [widgets, setWidgets] = useState(defaultWidgets);
  const weekdayLabels = locale === "fa" ? JALALI_WEEKDAYS : locale === "de" ? ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"] : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const onTrackCount = demoProjects.filter((project) => project.status === "active" || project.status === "inProgress").length;
  const atRiskCount = demoProjects.filter((project) => project.status === "atRisk").length;
  const completedCount = demoProjects.filter((project) => project.status === "completed").length;
  const activeProjects = demoProjects.filter((project) => project.status !== "completed").length;
  const openTasks = demoTasks.filter((task) => task.status !== "done").length;
  const teamMembers = demoProjects.reduce((sum, project) => sum + project.members, 0);
  const averageHealth = Math.round(demoProjects.reduce((sum, project) => sum + project.health, 0) / demoProjects.length);
  const healthDigits = locale === "fa" ? toPersianDigits(averageHealth) : String(averageHealth);
  const widgetTitle = useMemo(() => (widget: WidgetConfig): string => widget.kind === "pulse" ? t("dashboard.projectPulse") : widget.kind === "throughput" ? t("dashboard.taskThroughput") : widget.kind === "activity" ? t("dashboard.activity") : t("dashboard.healthScore"), [t]);
  const removeWidget = (id: string): void => setWidgets((current) => current.filter((widget) => widget.id !== id));
  const moveWidget = (id: string, direction: -1 | 1): void => setWidgets((current) => { const index = current.findIndex((widget) => widget.id === id); const nextIndex = index + direction; if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return current; const next = [...current]; [next[index], next[nextIndex]] = [next[nextIndex], next[index]]; return next; });

  return <div className="page page--dashboard"><SectionHeader eyebrow={t("nav.workspace")} title={t("dashboard.title")} subtitle={t("dashboard.subtitle")} actions={<div className="section-actions"><span className="updated-label"><span className="live-dot" />{t("dashboard.lastUpdated")}</span>{isEnabled("dashboardCustomization") && <Button variant={customizing ? "primary" : "secondary"} icon={customizing ? "check" : "settings"} onClick={() => setCustomizing((value) => !value)}>{customizing ? t("dashboard.done") : t("dashboard.customize")}</Button>}</div>} />
    <div className="metric-grid"><MetricCard label={t("dashboard.activeProjects")} value={activeProjects} icon="briefcase" tone="blue" /><MetricCard label={t("dashboard.openTasks")} value={openTasks} icon="checkSquare" tone="purple" /><MetricCard label={t("dashboard.teamMembers")} value={teamMembers} icon="users" tone="green" /><MetricCard label={t("dashboard.healthScore")} value={`${healthDigits}%`} icon="activity" tone="amber" /></div>
    <div className="quick-actions"><span className="quick-actions__label">{t("dashboard.quickActions")}</span><PermissionGuard permission={PERMISSIONS.projectCreate}><Button variant="subtle" size="sm" icon="plus" onClick={() => navigate("/app/projects?create=1")}>{t("dashboard.newProject")}</Button></PermissionGuard><PermissionGuard permission={PERMISSIONS.taskCreate}><Button variant="subtle" size="sm" icon="checkSquare" onClick={() => navigate("/app/tasks?create=1")}>{t("dashboard.newTask")}</Button></PermissionGuard><PermissionGuard permission={PERMISSIONS.documentUpload}><Button variant="subtle" size="sm" icon="upload" onClick={() => navigate("/app/documents?upload=1")}>{t("dashboard.uploadDocument")}</Button></PermissionGuard>{isEnabled("projectIntelligence") && <PermissionGuard permission={PERMISSIONS.intelligenceAnalyze}><Button variant="subtle" size="sm" icon="sparkles" onClick={() => navigate("/app/intelligence")}>{t("dashboard.runAnalysis")}</Button></PermissionGuard>}</div>
    {customizing && <div className="customize-banner" role="status"><Icon name="settings" size={17} /><span>{t("dashboard.customizeBanner")}</span><Button variant="primary" size="sm" icon="check" onClick={() => setCustomizing(false)}>{t("dashboard.done")}</Button></div>}
    {widgets.length === 0 ? <Card padding="none"><div className="state state--empty"><span className="state__icon"><Icon name="grid" size={24} /></span><h3>{t("dashboard.noWidgets")}</h3><Button variant="secondary" icon="refresh" onClick={() => setWidgets(defaultWidgets)}>{t("dashboard.restoreWidgets")}</Button></div></Card> : <div className="widget-grid">{widgets.map((widget, index) => <Card key={widget.id} className={`dashboard-widget dashboard-widget--${widget.size}`} padding="md"><CardHeader title={widgetTitle(widget)} subtitle={widget.kind === "pulse" ? t("dashboard.projectPulseCaption") : widget.kind === "throughput" ? t("dashboard.taskThroughputCaption") : undefined} action={customizing ? <div className="widget-controls"><button type="button" aria-label="Move widget up" disabled={index === 0} onClick={() => moveWidget(widget.id, -1)}><Icon name="arrowUp" size={14} /></button><button type="button" aria-label="Move widget down" disabled={index === widgets.length - 1} onClick={() => moveWidget(widget.id, 1)}><Icon name="arrowDown" size={14} /></button><button type="button" aria-label="Remove widget" onClick={() => removeWidget(widget.id)}><Icon name="close" size={14} /></button></div> : <button type="button" className="card-kebab" aria-label={t("common.more")}><Icon name="more" size={17} /></button>} />{widget.kind === "pulse" && <div className="project-pulse">{demoProjects.slice(0, 4).map((project) => <div className="pulse-row" key={project.id}><div className="pulse-row__name"><span className="project-dot" style={{ backgroundColor: project.color }} /> <strong>{project.name}</strong><StatusBadge status={project.status} /></div><div className="pulse-row__progress"><ProgressBar value={project.progress} tone={project.status === "atRisk" ? "amber" : project.status === "completed" ? "green" : "blue"} /><span>{project.progress}%</span></div></div>)}</div>}{widget.kind === "throughput" && <BarChart data={[9, 14, 11, 18, 16, 23, 20]} labels={weekdayLabels} color="#8b5cf6" ariaLabel={t("dashboard.taskThroughput")} />}{widget.kind === "activity" && <ActivityFeed items={demoActivity.slice(0, 4)} compact />}{widget.kind === "health" && <div className="health-widget"><DonutChart value={averageHealth} label={t("dashboard.healthScore")} color="#e6a23c" ariaLabel={t("dashboard.healthScore")} /><div className="health-widget__legend"><span><i className="legend-dot legend-dot--green" />{t("common.status.inProgress")} <strong>{onTrackCount}</strong></span><span><i className="legend-dot legend-dot--amber" />{t("common.status.atRisk")} <strong>{atRiskCount}</strong></span><span><i className="legend-dot legend-dot--purple" />{t("common.status.completed")} <strong>{completedCount}</strong></span></div></div>}</Card>)}</div>}
  </div>;
}
