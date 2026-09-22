import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices } from "../features/maintenance/maintenanceDemoData";
import type { DeviceStatus, MaintenanceDepartment, MaintenanceDevice } from "../shared/types/domain";
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
  TextInput,
} from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

const DEVICE_STATUSES: DeviceStatus[] = [
  "operational",
  "underMaintenance",
  "outOfService",
  "retired",
];

const DEPARTMENTS: MaintenanceDepartment[] = [
  "general",
  "electrical",
  "mechanical",
  "facilities",
  "instrumentation",
];

const statusTone = (status: DeviceStatus): "success" | "info" | "danger" | "neutral" =>
  status === "operational"
    ? "success"
    : status === "underMaintenance"
      ? "info"
      : status === "outOfService"
        ? "danger"
        : "neutral";

export function MaintenanceDevicesPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [devices, setDevices] = useState<MaintenanceDevice[]>(
    runtimeConfig.demoMode ? demoDevices : [],
  );
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [departmentFilter, setDepartmentFilter] = useState("all");
  const [toast, setToast] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [editDevice, setEditDevice] = useState<MaintenanceDevice | null>(null);
  const [pmDevice, setPmDevice] = useState<MaintenanceDevice | null>(null);

  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formLocation, setFormLocation] = useState("");
  const [formDepartment, setFormDepartment] = useState<MaintenanceDepartment>("general");
  const [formInterval, setFormInterval] = useState("30");
  const [pmDate, setPmDate] = useState("2026-09-22");

  const refresh = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    try {
      setDevices(await service.listDevices());
    } catch {
      /* keep last known state */
    }
  }, [service]);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(
    () =>
      devices.filter(
        (device) =>
          (statusFilter === "all" || device.status === statusFilter) &&
          (departmentFilter === "all" || device.department === departmentFilter) &&
          `${device.code} ${device.name} ${device.location}`
            .toLowerCase()
            .includes(search.toLowerCase()),
      ),
    [devices, search, statusFilter, departmentFilter],
  );

  const openCreate = (): void => {
    setFormCode("");
    setFormName("");
    setFormLocation("");
    setFormDepartment("general");
    setFormInterval("30");
    setCreateOpen(true);
  };

  const openEdit = (device: MaintenanceDevice): void => {
    setFormName(device.name);
    setFormLocation(device.location);
    setFormDepartment(device.department);
    setFormInterval(String(device.pmIntervalDays));
    setEditDevice(device);
  };

  const registerDevice = async (): Promise<void> => {
    if (!formCode.trim() || !formName.trim()) return;
    if (runtimeConfig.demoMode) {
      const device: MaintenanceDevice = {
        id: `dev-${Date.now()}`,
        code: formCode.trim(),
        name: formName.trim(),
        location: formLocation.trim(),
        status: "operational",
        department: formDepartment,
        pmIntervalDays: Number(formInterval) || 0,
        lastPmDate: "",
        nextDueDate: "",
        pmDue: false,
        createdAt: "2026-09-22",
      };
      setDevices((current) => [device, ...current]);
      setCreateOpen(false);
      setToast(t("cmms.device.createSuccess"));
      return;
    }
    try {
      await service.registerDevice({
        code: formCode.trim(),
        name: formName.trim(),
        location: formLocation.trim(),
        department: formDepartment,
        pmIntervalDays: Number(formInterval) || 0,
      });
      setCreateOpen(false);
      setToast(t("cmms.device.createSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.device.saveFailed"));
    }
  };

  const saveEdit = async (): Promise<void> => {
    if (!editDevice || !formName.trim()) return;
    if (runtimeConfig.demoMode) {
      setDevices((current) =>
        current.map((item) =>
          item.id === editDevice.id
            ? {
                ...item,
                name: formName.trim(),
                location: formLocation.trim(),
                department: formDepartment,
                pmIntervalDays: Number(formInterval) || 0,
              }
            : item,
        ),
      );
      setEditDevice(null);
      setToast(t("cmms.device.updateSuccess"));
      return;
    }
    try {
      await service.updateDevice(editDevice.id, {
        name: formName.trim(),
        location: formLocation.trim(),
        department: formDepartment,
        pmIntervalDays: Number(formInterval) || 0,
      });
      setEditDevice(null);
      setToast(t("cmms.device.updateSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.device.saveFailed"));
    }
  };

  const changeStatus = async (device: MaintenanceDevice, target: DeviceStatus): Promise<void> => {
    if (runtimeConfig.demoMode) {
      setDevices((current) =>
        current.map((item) => (item.id === device.id ? { ...item, status: target } : item)),
      );
      setToast(t("cmms.device.statusSuccess"));
      return;
    }
    try {
      await service.changeDeviceStatus(device.id, target);
      setToast(t("cmms.device.statusSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.device.saveFailed"));
    }
  };

  const recordPm = async (): Promise<void> => {
    if (!pmDevice) return;
    if (runtimeConfig.demoMode) {
      setDevices((current) =>
        current.map((item) =>
          item.id === pmDevice.id ? { ...item, lastPmDate: pmDate, pmDue: false } : item,
        ),
      );
      setPmDevice(null);
      setToast(t("cmms.device.pmSuccess"));
      return;
    }
    try {
      await service.recordPm(pmDevice.id, pmDate);
      setPmDevice(null);
      setToast(t("cmms.device.pmSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.device.saveFailed"));
    }
  };

  const totalDevices = devices.length;
  const dueCount = devices.filter((device) => device.pmDue).length;
  const operationalCount = devices.filter((device) => device.status === "operational").length;

  const columns: DataTableColumn<MaintenanceDevice>[] = [
    {
      key: "code",
      label: t("cmms.device.code"),
      accessor: (row) => row.code,
      sortable: true,
      render: (row) => <strong>{row.code}</strong>,
    },
    { key: "name", label: t("cmms.device.name"), accessor: (row) => row.name, sortable: true },
    {
      key: "location",
      label: t("cmms.device.location"),
      accessor: (row) => row.location,
      render: (row) => <span className="muted-cell">{row.location || t("cmms.common.none")}</span>,
    },
    {
      key: "department",
      label: t("cmms.device.department"),
      accessor: (row) => row.department,
      sortable: true,
      render: (row) => <Badge tone="neutral">{t(`cmms.department.${row.department}`)}</Badge>,
    },
    {
      key: "status",
      label: t("cmms.device.status"),
      accessor: (row) => row.status,
      sortable: true,
      render: (row) => (
        <Badge tone={statusTone(row.status)} dot>
          {t(`cmms.status.${row.status}`)}
        </Badge>
      ),
    },
    {
      key: "nextDueDate",
      label: t("cmms.device.nextPm"),
      accessor: (row) => row.nextDueDate,
      sortable: true,
      render: (row) =>
        row.nextDueDate ? (
          <span className={row.pmDue ? "cmms-due" : ""}>
            {row.pmDue && <Icon name="warning" size={14} />} {row.nextDueDate}
          </span>
        ) : (
          <span className="muted-cell">{t("cmms.common.none")}</span>
        ),
    },
    {
      key: "actions",
      label: "",
      accessor: () => "",
      render: (row) => (
        <div className="cmms-row-actions">
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button variant="ghost" size="sm" icon="edit" onClick={() => openEdit(row)}>
              {t("cmms.device.editTitle")}
            </Button>
            <Button variant="ghost" size="sm" icon="check" onClick={() => setPmDevice(row)}>
              {t("cmms.device.recordPm")}
            </Button>
          </PermissionGuard>
        </div>
      ),
    },
  ];

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("cmms.devices.title")}
        subtitle={t("cmms.devices.subtitle")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button variant="primary" icon="plus" onClick={openCreate}>
              {t("cmms.devices.new")}
            </Button>
          </PermissionGuard>
        }
      />

      <div className="metric-grid">
        <MetricCard label={t("cmms.metric.totalDevices")} value={totalDevices} icon="cpu" tone="blue" />
        <MetricCard label={t("cmms.metric.operational")} value={operationalCount} icon="checkCircle" tone="green" />
        <MetricCard label={t("cmms.metric.duePm")} value={dueCount} icon="warning" tone="amber" />
      </div>

      <Card className="content-card" padding="none">
        <div className="view-toolbar">
          <div className="list-toolbar">
            <div className="search-box">
              <Icon name="search" size={16} />
              <input
                value={search}
                aria-label={t("cmms.devices.search")}
                placeholder={t("cmms.devices.search")}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <SelectInput
              aria-label={t("cmms.device.status")}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              options={[
                { value: "all", label: t("cmms.common.all") },
                ...DEVICE_STATUSES.map((status) => ({
                  value: status,
                  label: t(`cmms.status.${status}`),
                })),
              ]}
            />
            <SelectInput
              aria-label={t("cmms.device.department")}
              value={departmentFilter}
              onChange={(event) => setDepartmentFilter(event.target.value)}
              options={[
                { value: "all", label: t("cmms.department.allUnits") },
                ...DEPARTMENTS.map((department) => ({
                  value: department,
                  label: t(`cmms.department.${department}`),
                })),
              ]}
            />
          </div>
        </div>
        <DataTable
          columns={columns}
          data={filtered}
          rowKey={(row) => row.id}
          search=""
          empty={{ title: t("cmms.devices.empty") }}
          exportName="tekarai-devices"
        />
      </Card>

      <Modal
        open={createOpen}
        title={t("cmms.device.registerTitle")}
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={registerDevice}>
              {t("cmms.device.save")}
            </Button>
          </>
        }
      >
        <TextInput
          label={t("cmms.device.code")}
          required
          value={formCode}
          onChange={(event) => setFormCode(event.target.value)}
          autoFocus
        />
        <TextInput
          label={t("cmms.device.name")}
          required
          value={formName}
          onChange={(event) => setFormName(event.target.value)}
        />
        <div className="form-grid form-grid--compact">
          <TextInput
            label={t("cmms.device.location")}
            value={formLocation}
            onChange={(event) => setFormLocation(event.target.value)}
          />
          <TextInput
            label={t("cmms.device.pmInterval")}
            type="number"
            value={formInterval}
            onChange={(event) => setFormInterval(event.target.value)}
          />
        </div>
        <SelectInput
          label={t("cmms.device.department")}
          value={formDepartment}
          onChange={(event) => setFormDepartment(event.target.value as MaintenanceDepartment)}
          options={DEPARTMENTS.map((department) => ({
            value: department,
            label: t(`cmms.department.${department}`),
          }))}
        />
      </Modal>

      <Modal
        open={Boolean(editDevice)}
        title={t("cmms.device.editTitle")}
        onClose={() => setEditDevice(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditDevice(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={saveEdit}>
              {t("cmms.device.save")}
            </Button>
          </>
        }
      >
        {editDevice && (
          <>
            <TextInput
              label={t("cmms.device.name")}
              required
              value={formName}
              onChange={(event) => setFormName(event.target.value)}
            />
            <div className="form-grid form-grid--compact">
              <TextInput
                label={t("cmms.device.location")}
                value={formLocation}
                onChange={(event) => setFormLocation(event.target.value)}
              />
              <TextInput
                label={t("cmms.device.pmInterval")}
                type="number"
                value={formInterval}
                onChange={(event) => setFormInterval(event.target.value)}
              />
            </div>
            <SelectInput
              label={t("cmms.device.department")}
              value={formDepartment}
              onChange={(event) => setFormDepartment(event.target.value as MaintenanceDepartment)}
              options={DEPARTMENTS.map((department) => ({
                value: department,
                label: t(`cmms.department.${department}`),
              }))}
            />
            <SelectInput
              label={t("cmms.device.changeStatus")}
              value={editDevice.status}
              onChange={(event) => changeStatus(editDevice, event.target.value as DeviceStatus)}
              options={DEVICE_STATUSES.map((status) => ({
                value: status,
                label: t(`cmms.status.${status}`),
              }))}
            />
          </>
        )}
      </Modal>

      <Modal
        open={Boolean(pmDevice)}
        title={t("cmms.device.recordPmTitle")}
        onClose={() => setPmDevice(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPmDevice(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={recordPm}>
              {t("cmms.device.recordPm")}
            </Button>
          </>
        }
      >
        {pmDevice && (
          <>
            <p className="detail-panel__description">
              {pmDevice.code} — {pmDevice.name}
            </p>
            <TextInput
              label={t("cmms.device.performedOn")}
              type="date"
              value={pmDate}
              onChange={(event) => setPmDate(event.target.value)}
            />
          </>
        )}
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
