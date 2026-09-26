import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createRegistryService } from "../features/maintenance/registryService";
import { createDemoRegistryService } from "../features/maintenance/registryDemoData";
import {
  EQUIPMENT_CRITICALITIES,
  MAINTENANCE_DEPARTMENTS,
  type FleetAnalytics,
  type FleetAnalyticsRow,
} from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  MetricCard,
  SectionHeader,
  SelectInput,
} from "../shared/components/primitives";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";

const formatNumber = (value: number | null, digits = 1): string =>
  value === null || Number.isNaN(value) ? "—" : value.toFixed(digits);

const formatMoney = (value: number): string =>
  value ? new Intl.NumberFormat("fa-IR").format(Math.round(value)) : "۰";

/** Plant-wide comparison of maintenance KPIs across every registered device. */
export function FleetAnalyticsPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const registry = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );

  const [fleet, setFleet] = useState<FleetAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [department, setDepartment] = useState("");
  const [criticality, setCriticality] = useState("");

  const refresh = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      setFleet(await registry.getFleetAnalytics({ fromDate, toDate, department, criticality }));
    } catch {
      setToast(t("registry.common.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [registry, fromDate, toDate, department, criticality, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const columns: DataTableColumn<FleetAnalyticsRow>[] = [
    {
      key: "code",
      label: t("registry.column.code"),
      accessor: (row) => row.code,
      sortable: true,
      render: (row) => <strong>{row.code}</strong>,
    },
    { key: "name", label: t("registry.column.name"), accessor: (row) => row.name, sortable: true },
    {
      key: "locationPath",
      label: t("registry.column.location"),
      accessor: (row) => row.locationPath,
      render: (row) => (
        <span className="muted-cell">{row.locationPath || t("registry.common.none")}</span>
      ),
    },
    {
      key: "criticality",
      label: t("registry.column.criticality"),
      accessor: (row) => row.criticality,
      sortable: true,
      render: (row) => (
        <Badge tone={row.criticality === "critical" ? "danger" : "neutral"}>
          {t(`registry.criticality.${row.criticality}`)}
        </Badge>
      ),
    },
    {
      key: "repairCount",
      label: t("registry.analytics.repairs"),
      accessor: (row) => row.repairCount,
      sortable: true,
    },
    {
      key: "downtimeHours",
      label: t("registry.analytics.downtime"),
      accessor: (row) => row.downtimeHours,
      sortable: true,
      render: (row) => formatNumber(row.downtimeHours),
    },
    {
      key: "mtbfHours",
      label: t("registry.analytics.mtbf"),
      accessor: (row) => row.mtbfHours ?? 0,
      sortable: true,
      render: (row) => formatNumber(row.mtbfHours),
    },
    {
      key: "mttrHours",
      label: t("registry.analytics.mttr"),
      accessor: (row) => row.mttrHours ?? 0,
      sortable: true,
      render: (row) => formatNumber(row.mttrHours),
    },
    {
      key: "availabilityPercent",
      label: t("registry.analytics.availability"),
      accessor: (row) => row.availabilityPercent ?? 0,
      sortable: true,
      render: (row) => formatNumber(row.availabilityPercent),
    },
    {
      key: "pmCompliancePercent",
      label: t("registry.analytics.pmCompliance"),
      accessor: (row) => row.pmCompliancePercent ?? 0,
      sortable: true,
      render: (row) => formatNumber(row.pmCompliancePercent),
    },
    {
      key: "totalCost",
      label: t("registry.analytics.cost"),
      accessor: (row) => row.totalCost,
      sortable: true,
      render: (row) => formatMoney(row.totalCost),
    },
  ];

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("registry.fleet.title")}
        subtitle={t("registry.fleet.subtitle")}
        actions={
          <Button
            variant="secondary"
            icon="arrowRight"
            onClick={() => navigate("/app/maintenance/registry")}
          >
            {t("registry.profile.back")}
          </Button>
        }
      />

      <div className="metric-grid">
        <MetricCard
          label={t("registry.fleet.deviceCount")}
          value={fleet?.deviceCount ?? 0}
          icon="cpu"
          tone="blue"
        />
        <MetricCard
          label={t("registry.fleet.totalRepairs")}
          value={fleet?.totalRepairs ?? 0}
          icon="warning"
          tone="amber"
        />
        <MetricCard
          label={t("registry.fleet.totalDowntime")}
          value={formatNumber(fleet?.totalDowntimeHours ?? 0)}
          icon="clock"
          tone="purple"
        />
        <MetricCard
          label={t("registry.fleet.totalCost")}
          value={formatMoney(fleet?.totalCost ?? 0)}
          icon="chart"
          tone="green"
        />
      </div>

      <Card className="content-card" padding="md">
        <div className="cmms-report-filter">
          <JalaliDatePicker
            label={t("registry.analytics.from")}
            value={fromDate}
            onChange={setFromDate}
          />
          <JalaliDatePicker label={t("registry.analytics.to")} value={toDate} onChange={setToDate} />
          <SelectInput
            aria-label={t("registry.column.department")}
            value={department}
            onChange={(event) => setDepartment(event.target.value)}
            options={[
              { value: "", label: t("cmms.department.allUnits") },
              ...MAINTENANCE_DEPARTMENTS.map((item) => ({
                value: item,
                label: t(`cmms.department.${item}`),
              })),
            ]}
          />
          <SelectInput
            aria-label={t("registry.filter.criticality")}
            value={criticality}
            onChange={(event) => setCriticality(event.target.value)}
            options={[
              { value: "", label: t("registry.filter.allCriticalities") },
              ...EQUIPMENT_CRITICALITIES.map((level) => ({
                value: level,
                label: t(`registry.criticality.${level}`),
              })),
            ]}
          />
          <Button variant="secondary" icon="refresh" onClick={() => void refresh()}>
            {t("registry.analytics.apply")}
          </Button>
        </div>
        <DataTable
          columns={columns}
          data={fleet?.rows ?? []}
          rowKey={(row) => row.deviceId}
          loading={loading}
          pageSize={10}
          empty={{ title: t("registry.fleet.empty") }}
          onRowClick={(row) => navigate(`/app/maintenance/devices/${row.deviceId}/profile`)}
          exportName="tekarai-fleet-analytics"
        />
      </Card>

      <div className="registry-discipline-grid">
        <Card className="content-card" padding="md">
          <SectionHeader title={t("registry.fleet.topParts")} />
          {(fleet?.topParts ?? []).length === 0 ? (
            <EmptyState icon="layers" title={t("registry.fleet.empty")} />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("registry.parts.part")}</th>
                  <th>{t("registry.parts.usageCount")}</th>
                  <th>{t("registry.parts.usedQuantity")}</th>
                  <th>{t("registry.analytics.cost")}</th>
                </tr>
              </thead>
              <tbody>
                {(fleet?.topParts ?? []).map((part) => (
                  <tr key={part.partId}>
                    <td>
                      <strong>{part.partCode}</strong>
                      <div className="muted-cell">{part.partName}</div>
                    </td>
                    <td>{part.usageCount}</td>
                    <td>
                      {part.totalQuantity} {part.unit}
                    </td>
                    <td>{formatMoney(part.totalCost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card className="content-card" padding="md">
          <SectionHeader title={t("registry.fleet.topFailures")} />
          {(fleet?.topFailureTypes ?? []).length === 0 ? (
            <EmptyState icon="warning" title={t("registry.fleet.empty")} />
          ) : (
            <ul className="registry-checklist">
              {(fleet?.topFailureTypes ?? []).map((failure) => (
                <li key={failure.label}>
                  {failure.label} — {failure.count}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
