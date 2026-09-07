import { useMemo, useState } from "react";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { demoReports } from "../features/demo/demoData";
import type { Report } from "../shared/types/domain";
import { BarChart, LineChart } from "../shared/components/charts";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import { Button, Card, CardHeader, PermissionGuard, ProgressBar, SectionHeader, StatusBadge, TextInput, TextArea } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

export function ReportsPage(): JSX.Element {
  const { t } = useLocalization();
  const [reports, setReports] = useState<Report[]>(demoReports);
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [toast, setToast] = useState("");
  const columns = useMemo<DataTableColumn<Report>[]>(() => [
    { key: "name", label: t("report.title"), accessor: (row) => `${row.name} ${row.description}`, sortable: true, width: "30%", render: (row) => <div className="report-cell"><span className="report-cell__icon"><Icon name="chart" size={17} /></span><div><strong>{row.name}</strong><span>{row.description}</span></div></div> },
    { key: "owner", label: t("report.owner"), accessor: (row) => row.owner, sortable: true },
    { key: "schedule", label: t("report.schedule"), accessor: (row) => row.schedule },
    { key: "lastRun", label: t("report.lastRun"), accessor: (row) => row.lastRun },
    { key: "coverage", label: t("report.coverage"), accessor: (row) => row.coverage, sortable: true, render: (row) => <div className="progress-cell"><ProgressBar value={row.coverage} showValue={false} tone="green" /><span>{row.coverage}%</span></div> },
    { key: "status", label: t("report.status"), accessor: (row) => row.status, render: (row) => <StatusBadge status={row.status} /> },
    { key: "action", label: t("project.actions"), hideable: false, render: (row) => <Button variant="ghost" size="sm" icon="external" onClick={() => setToast(`${row.name} report queued.`)}>{t("report.run")}</Button> },
  ], [t]);
  const filtered = reports.filter((report) => `${report.name} ${report.description} ${report.owner}`.toLowerCase().includes(search.toLowerCase()));
  const createReport = (): void => { if (!newName.trim()) return; setReports((current) => [{ id: `report-${Date.now()}`, name: newName.trim(), description: "A configurable operational report.", owner: "Maya Chen", lastRun: "Not run", schedule: "On demand", status: "pending", coverage: 0 }, ...current]); setNewName(""); setCreateOpen(false); setToast("Report definition created."); };
  return <div className="page"><SectionHeader eyebrow={t("nav.reports")} title={t("report.title")} subtitle={t("report.subtitle")} actions={<PermissionGuard permission={PERMISSIONS.reportView}><Button variant="primary" icon="plus" onClick={() => setCreateOpen(true)}>{t("report.new")}</Button></PermissionGuard>} />
    <div className="report-insight-grid"><Card padding="md"><CardHeader title={t("report.coverage")} /><LineChart data={[72, 75, 74, 80, 83, 88, 92]} labels={["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]} color="#27b27e" ariaLabel="Operational coverage trend" /></Card><Card padding="md"><CardHeader title={t("report.insights")} /><BarChart data={[32, 22, 18, 12, 8]} labels={["Projects", "Tasks", "Docs", "Access", "Other"]} color="#2878ff" ariaLabel="Insight categories" /></Card></div>
    <Card className="content-card" padding="none"><CardHeader title={`${filtered.length} reports`} action={<div className="search-box"><Icon name="search" size={16} /><input value={search} aria-label={t("report.title")} placeholder={t("header.search")} onChange={(event) => setSearch(event.target.value)} /></div>} /><DataTable columns={columns} data={filtered} rowKey={(row) => row.id} search="" exportName="tekarai-reports" empty={{ title: t("common.noResults") }} /></Card>
    <Modal open={createOpen} title={t("report.new")} onClose={() => setCreateOpen(false)} footer={<><Button variant="secondary" onClick={() => setCreateOpen(false)}>{t("common.cancel")}</Button><Button variant="primary" onClick={createReport}>{t("common.save")}</Button></>}><TextInput label={t("report.title")} value={newName} onChange={(event) => setNewName(event.target.value)} autoFocus required /><TextArea label={t("project.description")} rows={4} placeholder={t("project.description")} /></Modal>
    {toast && <Toast message={toast} onClose={() => setToast("")} />}
  </div>;
}
