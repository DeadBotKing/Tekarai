import { useMemo } from "react";
import { useLocation } from "react-router-dom";
import { useLocalization } from "../core/localization/localizationContext";
import type { DataTableColumn } from "../shared/components/DataTable";
import { DataTable } from "../shared/components/DataTable";
import { Avatar, Badge, Button, Card, CardHeader, SectionHeader, StatusBadge } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

interface ResourceRecord { id: string; name: string; detail: string; status: "active" | "pending" | "atRisk"; owner: string; metric: string; }
const resourceData: Record<string, { title: string; subtitle: string; icon: "users" | "layers" | "cpu"; rows: ResourceRecord[] }> = {
  employees: { title: "Employees", subtitle: "A tenant-aware directory for people and operational ownership.", icon: "users", rows: [{ id: "e1", name: "Maya Chen", detail: "Platform Administrator", status: "active", owner: "Nordic Manufacturing Group", metric: "248 members" }, { id: "e2", name: "Jon Bell", detail: "Workspace Manager", status: "active", owner: "Atlas Engineering GmbH", metric: "18 projects" }, { id: "e3", name: "Sara Novak", detail: "Operations Lead", status: "active", owner: "Nordic Manufacturing Group", metric: "6 workflows" }] },
  departments: { title: "Departments", subtitle: "Organize ownership and access without hard-coding industry-specific rules.", icon: "layers", rows: [{ id: "d1", name: "Operations", detail: "Delivery and service", status: "active", owner: "Jon Bell", metric: "42 people" }, { id: "d2", name: "Quality", detail: "Validation and governance", status: "active", owner: "Sara Novak", metric: "18 people" }, { id: "d3", name: "Engineering", detail: "Technical delivery", status: "pending", owner: "Owen Wright", metric: "31 people" }] },
  devices: { title: "Devices", subtitle: "Monitor connected operational devices through a permission-aware view.", icon: "cpu", rows: [{ id: "v1", name: "Plant gateway 04", detail: "Telemetry gateway", status: "active", owner: "Nova Plant Modernization", metric: "99.8% uptime" }, { id: "v2", name: "Quality scanner 12", detail: "Edge device", status: "active", owner: "Atlas Quality System", metric: "98.6% uptime" }, { id: "v3", name: "Energy meter 07", detail: "Read-only sensor", status: "atRisk", owner: "Orbit Energy Reporting", metric: "91.2% uptime" }] },
};

export function OperationsResourcePage(): JSX.Element {
  const { t } = useLocalization();
  const location = useLocation();
  const key = location.pathname.includes("employees") ? "employees" : location.pathname.includes("departments") ? "departments" : "devices";
  const config = resourceData[key];
  const columns = useMemo<DataTableColumn<ResourceRecord>[]>(() => [{ key: "name", label: config.title, accessor: (row) => `${row.name} ${row.detail}`, sortable: true, width: "30%", render: (row) => <div className="person-cell"><Avatar name={row.name} size="sm" tone="purple" /><div><strong>{row.name}</strong><span>{row.detail}</span></div></div> }, { key: "owner", label: t("project.owner"), accessor: (row) => row.owner, sortable: true }, { key: "status", label: t("project.status"), accessor: (row) => row.status, render: (row) => <StatusBadge status={row.status} /> }, { key: "metric", label: "Signal", accessor: (row) => row.metric, render: (row) => <Badge tone="info">{row.metric}</Badge> }, { key: "action", label: t("project.actions"), hideable: false, render: () => <Button variant="ghost" size="sm" icon="external">{t("common.view")}</Button> }], [config.title, t]);
  return <div className="page"><SectionHeader eyebrow={t("nav.organization")} title={config.title} subtitle={config.subtitle} actions={<Button variant="primary" icon="plus">Add {config.title.slice(0, -1).toLowerCase()}</Button>} /><Card className="content-card" padding="none"><CardHeader title="Configuration-driven resource" subtitle="This page is a generic feature surface; its data and permissions come from the application contract." /><DataTable columns={columns} data={config.rows} rowKey={(row) => row.id} exportName={`tekarai-${key}`} /></Card><div className="resource-note"><Icon name={config.icon} size={18} /><span>Backend remains the source of truth for {config.title.toLowerCase()}, tenant isolation and authorization.</span></div></div>;
}
