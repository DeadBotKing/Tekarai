import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { createRegistryService } from "../features/maintenance/registryService";
import {
  createDemoRegistryService,
  demoRegistryDevices,
  registerDemoDevice,
} from "../features/maintenance/registryDemoData";
import {
  EQUIPMENT_CRITICALITIES,
  MAINTENANCE_DEPARTMENTS,
  type DeviceStatus,
  type EquipmentCriticality,
  type MaintenanceDepartment,
  type MaintenanceDevice,
  type MaintenanceLocation,
} from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  MetricCard,
  PermissionGuard,
  SectionHeader,
  SelectInput,
  TextArea,
  TextInput,
} from "../shared/components/primitives";
import { JalaliDatePicker } from "../shared/components/JalaliDatePicker";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import { CreatableSelect } from "../shared/components/CreatableSelect";
import { mergeOptions } from "../features/maintenance/optionCatalog";

const DEVICE_STATUSES: DeviceStatus[] = [
  "operational",
  "underMaintenance",
  "outOfService",
  "retired",
];

const statusTone = (status: DeviceStatus): "success" | "info" | "danger" | "neutral" =>
  status === "operational"
    ? "success"
    : status === "underMaintenance"
      ? "info"
      : status === "outOfService"
        ? "danger"
        : "neutral";

const criticalityTone = (
  criticality: EquipmentCriticality,
): "danger" | "warning" | "info" | "neutral" =>
  criticality === "critical"
    ? "danger"
    : criticality === "high"
      ? "warning"
      : criticality === "medium"
        ? "info"
        : "neutral";

/**
 * The equipment registry: every machine and device in one searchable database,
 * with the "add machine" entry point and a link into each device file.
 */
export function EquipmentRegistryPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const maintenance = useMemo(() => createMaintenanceService(api), [api]);
  const registry = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );

  const [devices, setDevices] = useState<MaintenanceDevice[]>(
    runtimeConfig.demoMode ? demoRegistryDevices : [],
  );
  const [locations, setLocations] = useState<MaintenanceLocation[]>([]);
  const [loading, setLoading] = useState(!runtimeConfig.demoMode);
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [departmentFilter, setDepartmentFilter] = useState("all");
  const [criticalityFilter, setCriticalityFilter] = useState("all");
  const [locationFilter, setLocationFilter] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formDepartment, setFormDepartment] = useState<MaintenanceDepartment>("mechanical");
  const [formInterval, setFormInterval] = useState("30");
  const [formCriticality, setFormCriticality] = useState<EquipmentCriticality>("medium");
  const [formLocationId, setFormLocationId] = useState("");
  const [formManufacturer, setFormManufacturer] = useState("");
  const [formModel, setFormModel] = useState("");
  const [formSerial, setFormSerial] = useState("");
  const [formType, setFormType] = useState("");
  const [formYear, setFormYear] = useState("");
  const [formCapacity, setFormCapacity] = useState("");
  const [formPower, setFormPower] = useState("");
  const [formElectrical, setFormElectrical] = useState("");
  const [formOperatorUnit, setFormOperatorUnit] = useState("");
  const [formSupplier, setFormSupplier] = useState("");
  const [formInstalledOn, setFormInstalledOn] = useState("");
  const [formCost, setFormCost] = useState("");
  const [formRunningHours, setFormRunningHours] = useState("");
  const [formNotes, setFormNotes] = useState("");

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const [deviceList, locationList] = await Promise.all([
        runtimeConfig.demoMode
          ? Promise.resolve(demoRegistryDevices)
          : maintenance.listDevices(),
        registry.listLocations(),
      ]);
      setDevices(deviceList);
      setLocations(locationList);
    } catch {
      setToast(t("registry.common.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [maintenance, registry, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(
    () =>
      devices.filter((device) => {
        const criticality = device.criticality ?? "medium";
        return (
          (statusFilter === "all" || device.status === statusFilter) &&
          (departmentFilter === "all" || device.department === departmentFilter) &&
          (criticalityFilter === "all" || criticality === criticalityFilter) &&
          (locationFilter === "all" || device.locationId === locationFilter) &&
          `${device.code} ${device.name} ${device.manufacturer ?? ""} ${device.modelNumber ?? ""} ${
            device.locationPath || device.location
          }`
            .toLowerCase()
            .includes(search.toLowerCase())
        );
      }),
    [devices, search, statusFilter, departmentFilter, criticalityFilter, locationFilter],
  );

  const criticalCount = devices.filter((device) => device.criticality === "critical").length;
  const underMaintenanceCount = devices.filter(
    (device) => device.status === "underMaintenance",
  ).length;
  const dueCount = devices.filter((device) => device.pmDue).length;

  const resetForm = (): void => {
    setFormCode("");
    setFormName("");
    setFormDepartment("mechanical");
    setFormInterval("30");
    setFormCriticality("medium");
    setFormLocationId("");
    setFormManufacturer("");
    setFormModel("");
    setFormSerial("");
    setFormType("");
    setFormYear("");
    setFormCapacity("");
    setFormPower("");
    setFormElectrical("");
    setFormOperatorUnit("");
    setFormSupplier("");
    setFormInstalledOn("");
    setFormCost("");
    setFormRunningHours("");
    setFormNotes("");
  };

  const nameplateValues = (): Record<string, string> => ({
    manufacturer: formManufacturer.trim(),
    modelNumber: formModel.trim(),
    serialNumber: formSerial.trim(),
    assetType: formType.trim(),
    manufactureYear: formYear.trim(),
    capacity: formCapacity.trim(),
    powerRating: formPower.trim(),
    electricalSpec: formElectrical.trim(),
    criticality: formCriticality,
    locationId: formLocationId,
    operatorUnit: formOperatorUnit.trim(),
    supplier: formSupplier.trim(),
    installedOn: formInstalledOn,
    purchaseCost: formCost.trim() || "0",
    runningHours: formRunningHours.trim() || "0",
    notes: formNotes.trim(),
  });

  const submit = async (): Promise<void> => {
    if (!formCode.trim() || !formName.trim()) {
      setToast(t("registry.common.required"));
      return;
    }
    const location = locations.find((item) => item.id === formLocationId);
    setSaving(true);
    try {
      if (runtimeConfig.demoMode) {
        const device: MaintenanceDevice = {
          id: `dev-${Date.now()}`,
          code: formCode.trim(),
          name: formName.trim(),
          location: location?.path ?? "",
          status: "operational",
          department: formDepartment,
          pmIntervalDays: Number(formInterval) || 0,
          lastPmDate: "",
          nextDueDate: "",
          pmDue: false,
          createdAt: new Date().toISOString().slice(0, 10),
          manufacturer: formManufacturer.trim(),
          modelNumber: formModel.trim(),
          serialNumber: formSerial.trim(),
          equipmentType: formType.trim(),
          criticality: formCriticality,
          locationId: formLocationId,
          locationPath: location?.path ?? "",
          operatorUnit: formOperatorUnit.trim(),
          runningHours: Number(formRunningHours) || 0,
        };
        registerDemoDevice(device);
        setDevices((current) => [device, ...current]);
      } else {
        const created = await maintenance.registerDevice({
          code: formCode.trim(),
          name: formName.trim(),
          location: location?.path ?? "",
          department: formDepartment,
          pmIntervalDays: Number(formInterval) || 0,
        });
        await registry.updateNameplate(created.id, nameplateValues());
        await refresh();
      }
      setCreateOpen(false);
      resetForm();
      setToast(t("registry.saved"));
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("registry.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const columns: DataTableColumn<MaintenanceDevice>[] = [
    {
      key: "code",
      label: t("registry.column.code"),
      accessor: (row) => row.code,
      sortable: true,
      render: (row) => <strong>{row.code}</strong>,
    },
    { key: "name", label: t("registry.column.name"), accessor: (row) => row.name, sortable: true },
    {
      key: "equipmentType",
      label: t("registry.column.type"),
      accessor: (row) => row.equipmentType ?? "",
      render: (row) => (
        <span className="muted-cell">{row.equipmentType || t("registry.common.none")}</span>
      ),
    },
    {
      key: "manufacturer",
      label: t("registry.column.manufacturer"),
      accessor: (row) => row.manufacturer ?? "",
      render: (row) => (
        <span className="muted-cell">
          {[row.manufacturer, row.modelNumber].filter(Boolean).join(" / ") ||
            t("registry.common.none")}
        </span>
      ),
    },
    {
      key: "location",
      label: t("registry.column.location"),
      accessor: (row) => row.locationPath || row.location,
      sortable: true,
      render: (row) => (
        <span className="muted-cell">
          {row.locationPath || row.location || t("registry.common.none")}
        </span>
      ),
    },
    {
      key: "department",
      label: t("registry.column.department"),
      accessor: (row) => row.department,
      sortable: true,
      render: (row) => <Badge tone="neutral">{taxonomyLabel(t, "cmms.department.", row.department)}</Badge>,
    },
    {
      key: "criticality",
      label: t("registry.column.criticality"),
      accessor: (row) => row.criticality ?? "medium",
      sortable: true,
      render: (row) => (
        <Badge tone={criticalityTone(row.criticality ?? "medium")}>
          {taxonomyLabel(t, "registry.criticality.", row.criticality ?? "medium")}
        </Badge>
      ),
    },
    {
      key: "status",
      label: t("registry.column.status"),
      accessor: (row) => row.status,
      sortable: true,
      render: (row) => (
        <Badge tone={statusTone(row.status)} dot>
          {taxonomyLabel(t, "cmms.status.", row.status)}
        </Badge>
      ),
    },
    {
      key: "actions",
      label: t("registry.column.actions"),
      accessor: () => "",
      render: (row) => (
        <div className="cmms-row-actions">
          <Button
            variant="ghost"
            size="sm"
            icon="file"
            onClick={() => navigate(`/app/maintenance/devices/${row.id}/profile`)}
          >
            {t("registry.openProfile")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("registry.title")}
        subtitle={t("registry.subtitle")}
        actions={
          <div className="cmms-header-actions">
            <PermissionGuard permission={PERMISSIONS.maintenanceDeviceList}>
              <Button
                variant="secondary"
                icon="chart"
                onClick={() => navigate("/app/maintenance/fleet")}
              >
                {t("nav.registryFleet")}
              </Button>
            </PermissionGuard>
            <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
              <Button
                variant="secondary"
                icon="building"
                onClick={() => navigate("/app/maintenance/locations")}
              >
                {t("nav.registryLocations")}
              </Button>
              <Button
                variant="secondary"
                icon="users"
                onClick={() => navigate("/app/maintenance/personnel")}
              >
                {t("nav.registryPersonnel")}
              </Button>
              <Button variant="primary" icon="plus" onClick={() => setCreateOpen(true)}>
                {t("registry.add")}
              </Button>
            </PermissionGuard>
          </div>
        }
      />

      <div className="metric-grid">
        <MetricCard label={t("registry.metric.total")} value={devices.length} icon="cpu" tone="blue" />
        <MetricCard
          label={t("registry.metric.critical")}
          value={criticalCount}
          icon="shield"
          tone="purple"
        />
        <MetricCard
          label={t("registry.metric.underMaintenance")}
          value={underMaintenanceCount}
          icon="settings"
          tone="amber"
        />
        <MetricCard label={t("registry.metric.pmDue")} value={dueCount} icon="warning" tone="amber" />
      </div>

      <Card className="content-card" padding="md">
        <div className="cmms-report-filter">
          <TextInput
            aria-label={t("registry.search")}
            placeholder={t("registry.search")}
            icon="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <SelectInput
            aria-label={t("registry.column.status")}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            options={[
              { value: "all", label: t("cmms.status.all") },
              ...DEVICE_STATUSES.map((status) => ({
                value: status,
                label: taxonomyLabel(t, "cmms.status.", status),
              })),
            ]}
          />
          <SelectInput
            aria-label={t("registry.column.department")}
            value={departmentFilter}
            onChange={(event) => setDepartmentFilter(event.target.value)}
            options={[
              { value: "all", label: t("cmms.department.allUnits") },
              ...mergeOptions({
                canonical: MAINTENANCE_DEPARTMENTS,
                translate: (department) => taxonomyLabel(t, "cmms.department.", department),
                fromData: devices.map((item) => item.department),
                catalogKey: "device.department",
              }),
            ]}
          />
          <SelectInput
            aria-label={t("registry.filter.criticality")}
            value={criticalityFilter}
            onChange={(event) => setCriticalityFilter(event.target.value)}
            options={[
              { value: "all", label: t("registry.filter.allCriticalities") },
              ...mergeOptions({
                canonical: EQUIPMENT_CRITICALITIES,
                translate: (level) => taxonomyLabel(t, "registry.criticality.", level),
                fromData: devices.map((item) => item.criticality ?? ""),
                catalogKey: "device.criticality",
              }),
            ]}
          />
          <SelectInput
            aria-label={t("registry.filter.location")}
            value={locationFilter}
            onChange={(event) => setLocationFilter(event.target.value)}
            options={[
              { value: "all", label: t("registry.filter.allLocations") },
              ...locations.map((location) => ({ value: location.id, label: location.path })),
            ]}
          />
        </div>
        <DataTable
          columns={columns}
          data={filtered}
          rowKey={(row) => row.id}
          loading={loading}
          pageSize={10}
          empty={{ title: t("registry.empty") }}
          onRowClick={(row) => navigate(`/app/maintenance/devices/${row.id}/profile`)}
          exportName="tekarai-equipment-registry"
        />
      </Card>

      <Modal
        open={createOpen}
        title={t("registry.createTitle")}
        description={t("registry.createHint")}
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {t("registry.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" loading={saving} onClick={submit}>
              {t("registry.common.save")}
            </Button>
          </>
        }
      >
        <div className="form-grid form-grid--compact">
          <TextInput
            label={t("registry.column.code")}
            required
            value={formCode}
            onChange={(event) => setFormCode(event.target.value)}
            autoFocus
          />
          <TextInput
            label={t("registry.column.name")}
            required
            value={formName}
            onChange={(event) => setFormName(event.target.value)}
          />
          <CreatableSelect
            label={t("registry.column.department")}
            value={formDepartment}
            onChange={(value) => setFormDepartment(value as MaintenanceDepartment)}
            catalogKey="device.department"
            canonical={MAINTENANCE_DEPARTMENTS}
            options={mergeOptions({
              canonical: MAINTENANCE_DEPARTMENTS,
              translate: (department) => taxonomyLabel(t, "cmms.department.", department),
              fromData: devices.map((item) => item.department),
              catalogKey: "device.department",
              current: formDepartment,
            })}
          />
          <CreatableSelect
            label={t("registry.nameplate.criticality")}
            value={formCriticality}
            onChange={(value) => setFormCriticality(value as EquipmentCriticality)}
            catalogKey="device.criticality"
            canonical={EQUIPMENT_CRITICALITIES}
            options={mergeOptions({
              canonical: EQUIPMENT_CRITICALITIES,
              translate: (level) => taxonomyLabel(t, "registry.criticality.", level),
              fromData: devices.map((item) => item.criticality ?? ""),
              catalogKey: "device.criticality",
              current: formCriticality,
            })}
          />
          <SelectInput
            label={t("registry.nameplate.location")}
            value={formLocationId}
            onChange={(event) => setFormLocationId(event.target.value)}
            options={[
              { value: "", label: t("registry.nameplate.noLocation") },
              ...locations.map((location) => ({ value: location.id, label: location.path })),
            ]}
          />
          <TextInput
            label={t("cmms.device.pmInterval")}
            type="number"
            value={formInterval}
            onChange={(event) => setFormInterval(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.manufacturer")}
            value={formManufacturer}
            onChange={(event) => setFormManufacturer(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.modelNumber")}
            value={formModel}
            onChange={(event) => setFormModel(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.serialNumber")}
            value={formSerial}
            onChange={(event) => setFormSerial(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.assetType")}
            value={formType}
            onChange={(event) => setFormType(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.manufactureYear")}
            value={formYear}
            onChange={(event) => setFormYear(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.capacity")}
            value={formCapacity}
            onChange={(event) => setFormCapacity(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.powerRating")}
            value={formPower}
            onChange={(event) => setFormPower(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.electricalSpec")}
            value={formElectrical}
            onChange={(event) => setFormElectrical(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.operatorUnit")}
            value={formOperatorUnit}
            onChange={(event) => setFormOperatorUnit(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.supplier")}
            value={formSupplier}
            onChange={(event) => setFormSupplier(event.target.value)}
          />
          <JalaliDatePicker
            label={t("registry.nameplate.installedOn")}
            value={formInstalledOn}
            onChange={setFormInstalledOn}
          />
          <TextInput
            label={t("registry.nameplate.purchaseCost")}
            value={formCost}
            onChange={(event) => setFormCost(event.target.value)}
          />
          <TextInput
            label={t("registry.nameplate.runningHours")}
            value={formRunningHours}
            onChange={(event) => setFormRunningHours(event.target.value)}
          />
        </div>
        <TextArea
          label={t("registry.nameplate.notes")}
          value={formNotes}
          onChange={(event) => setFormNotes(event.target.value)}
        />
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
