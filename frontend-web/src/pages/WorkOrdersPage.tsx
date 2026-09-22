import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices, demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import type {
  MaintenanceDepartment,
  MaintenanceDevice,
  Priority,
  WorkOrder,
  WorkOrderStatus,
  WorkOrderType,
} from "../shared/types/domain";
import { DataTable, type DataTableColumn } from "../shared/components/DataTable";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Avatar,
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
import { Icon } from "../shared/components/Icon";

const WO_STATUSES: WorkOrderStatus[] = [
  "submitted",
  "routed",
  "assigned",
  "inProgress",
  "onHold",
  "completed",
  "cancelled",
];
const WO_TYPES: WorkOrderType[] = ["corrective", "preventive", "inspection"];
const PRIORITIES: Priority[] = ["low", "normal", "high", "critical"];
const DEPARTMENTS: MaintenanceDepartment[] = [
  "general",
  "electrical",
  "mechanical",
  "facilities",
  "instrumentation",
];

// Allowed forward transitions mirror the backend WORK_ORDER_TRANSITIONS state machine.
const NEXT_STATUSES: Record<WorkOrderStatus, WorkOrderStatus[]> = {
  submitted: ["routed", "assigned", "cancelled"],
  routed: ["assigned", "onHold", "cancelled"],
  assigned: ["inProgress", "onHold", "cancelled"],
  inProgress: ["onHold", "completed", "cancelled"],
  onHold: ["inProgress", "cancelled"],
  completed: [],
  cancelled: [],
};

const statusTone = (
  status: WorkOrderStatus,
): "success" | "info" | "warning" | "danger" | "neutral" | "purple" =>
  status === "completed"
    ? "success"
    : status === "inProgress"
      ? "info"
      : status === "onHold"
        ? "warning"
        : status === "cancelled"
          ? "danger"
          : status === "assigned"
            ? "purple"
            : status === "routed"
              ? "info"
              : "neutral";

const priorityTone = (priority: Priority): "danger" | "warning" | "neutral" =>
  priority === "critical" ? "danger" : priority === "high" ? "warning" : "neutral";

export function WorkOrdersPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [orders, setOrders] = useState<WorkOrder[]>(runtimeConfig.demoMode ? demoWorkOrders : []);
  const [devices, setDevices] = useState<MaintenanceDevice[]>(
    runtimeConfig.demoMode ? demoDevices : [],
  );
  const [view, setView] = useState<"list" | "board">("list");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [departmentFilter, setDepartmentFilter] = useState("all");
  const [toast, setToast] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [activeOrder, setActiveOrder] = useState<WorkOrder | null>(null);
  const [assignOrder, setAssignOrder] = useState<WorkOrder | null>(null);
  const [routeOrder, setRouteOrder] = useState<WorkOrder | null>(null);

  const [formDevice, setFormDevice] = useState("");
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formType, setFormType] = useState<WorkOrderType>("corrective");
  const [formPriority, setFormPriority] = useState<Priority>("normal");
  const [formDepartment, setFormDepartment] = useState<MaintenanceDepartment | "">("");
  const [formRequestedBy, setFormRequestedBy] = useState("");
  const [technicianName, setTechnicianName] = useState("");
  const [routeDepartment, setRouteDepartment] = useState<MaintenanceDepartment>("general");

  const deviceNames = useMemo(
    () => new Map(devices.map((device) => [device.id, `${device.code} — ${device.name}`])),
    [devices],
  );

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
    }
  }, [service]);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(
    () =>
      orders.filter(
        (order) =>
          (statusFilter === "all" || order.status === statusFilter) &&
          (departmentFilter === "all" || order.department === departmentFilter) &&
          `${order.title} ${order.requestedByName} ${order.assignedToName}`
            .toLowerCase()
            .includes(search.toLowerCase()),
      ),
    [orders, search, statusFilter, departmentFilter],
  );

  const openCreate = (): void => {
    setFormDevice(devices[0]?.id ?? "");
    setFormTitle("");
    setFormDescription("");
    setFormType("corrective");
    setFormPriority("normal");
    setFormDepartment("");
    setFormRequestedBy("");
    setCreateOpen(true);
  };

  const submitOrder = async (): Promise<void> => {
    if (!formDevice || !formTitle.trim()) return;
    // A work order inherits the device's department unless one is chosen.
    const selectedDevice = devices.find((device) => device.id === formDevice);
    const resolvedDepartment: MaintenanceDepartment =
      formDepartment || selectedDevice?.department || "general";
    if (runtimeConfig.demoMode) {
      const order: WorkOrder = {
        id: `wo-${Date.now()}`,
        deviceId: formDevice,
        title: formTitle.trim(),
        description: formDescription.trim(),
        orderType: formType,
        priority: formPriority,
        status: "submitted",
        department: resolvedDepartment,
        requestedByName: formRequestedBy.trim(),
        assignedToName: "",
        resolutionNote: "",
        createdAt: "2026-09-22",
        closedAt: "",
      };
      setOrders((current) => [order, ...current]);
      setCreateOpen(false);
      setToast(t("cmms.wo.createSuccess"));
      return;
    }
    try {
      await service.submitWorkOrder({
        deviceId: formDevice,
        title: formTitle.trim(),
        description: formDescription.trim(),
        orderType: formType,
        priority: formPriority,
        department: formDepartment,
        requestedByName: formRequestedBy.trim(),
      });
      setCreateOpen(false);
      setToast(t("cmms.wo.createSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const assign = async (): Promise<void> => {
    if (!assignOrder || !technicianName.trim()) return;
    if (runtimeConfig.demoMode) {
      setOrders((current) =>
        current.map((item) =>
          item.id === assignOrder.id
            ? { ...item, status: "assigned", assignedToName: technicianName.trim() }
            : item,
        ),
      );
      setAssignOrder(null);
      setTechnicianName("");
      setToast(t("cmms.wo.assignSuccess"));
      return;
    }
    try {
      await service.assignWorkOrder(assignOrder.id, technicianName.trim());
      setAssignOrder(null);
      setTechnicianName("");
      setToast(t("cmms.wo.assignSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const route = async (): Promise<void> => {
    if (!routeOrder) return;
    if (runtimeConfig.demoMode) {
      setOrders((current) =>
        current.map((item) =>
          item.id === routeOrder.id
            ? { ...item, status: "routed", department: routeDepartment, assignedToName: "" }
            : item,
        ),
      );
      setRouteOrder(null);
      setToast(t("cmms.wo.routeSuccess"));
      return;
    }
    try {
      await service.routeWorkOrder(routeOrder.id, routeDepartment);
      setRouteOrder(null);
      setToast(t("cmms.wo.routeSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const generatePm = async (): Promise<void> => {
    if (runtimeConfig.demoMode) {
      setToast(t("cmms.wo.generatePmDemo"));
      return;
    }
    try {
      const created = await service.generatePmWorkOrders();
      setToast(
        created.length > 0
          ? t("cmms.wo.generatePmSuccess").replace("{count}", String(created.length))
          : t("cmms.wo.generatePmNone"),
      );
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const changeStatus = async (order: WorkOrder, target: WorkOrderStatus): Promise<void> => {
    if (runtimeConfig.demoMode) {
      setOrders((current) =>
        current.map((item) => (item.id === order.id ? { ...item, status: target } : item)),
      );
      setToast(t("cmms.wo.statusSuccess"));
      return;
    }
    try {
      await service.changeWorkOrderStatus(order.id, target);
      setToast(t("cmms.wo.statusSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const openCount = orders.filter(
    (order) => order.status !== "completed" && order.status !== "cancelled",
  ).length;
  const inProgressCount = orders.filter((order) => order.status === "inProgress").length;

  const columns: DataTableColumn<WorkOrder>[] = [
    {
      key: "title",
      label: t("cmms.wo.woTitle"),
      accessor: (row) => row.title,
      sortable: true,
      width: "26%",
      render: (row) => (
        <button type="button" className="link-cell" onClick={() => setActiveOrder(row)}>
          <span className={`task-priority-dot task-priority-dot--${row.priority}`} />
          {row.title}
        </button>
      ),
    },
    {
      key: "device",
      label: t("cmms.wo.device"),
      accessor: (row) => deviceNames.get(row.deviceId) ?? row.deviceId,
      render: (row) => (
        <span className="muted-cell">{deviceNames.get(row.deviceId) ?? row.deviceId}</span>
      ),
    },
    {
      key: "orderType",
      label: t("cmms.wo.type"),
      accessor: (row) => row.orderType,
      sortable: true,
      render: (row) => <Badge tone="info">{t(`cmms.type.${row.orderType}`)}</Badge>,
    },
    {
      key: "department",
      label: t("cmms.wo.department"),
      accessor: (row) => row.department,
      sortable: true,
      render: (row) => <Badge tone="neutral">{t(`cmms.department.${row.department}`)}</Badge>,
    },
    {
      key: "status",
      label: t("cmms.wo.status"),
      accessor: (row) => row.status,
      sortable: true,
      render: (row) => (
        <Badge tone={statusTone(row.status)} dot>
          {t(`cmms.woStatus.${row.status}`)}
        </Badge>
      ),
    },
    {
      key: "priority",
      label: t("cmms.wo.priority"),
      accessor: (row) => row.priority,
      sortable: true,
      render: (row) => <Badge tone={priorityTone(row.priority)}>{t(`cmms.priority.${row.priority}`)}</Badge>,
    },
    {
      key: "assignedToName",
      label: t("cmms.wo.assignedTo"),
      accessor: (row) => row.assignedToName,
      render: (row) =>
        row.assignedToName ? (
          <div className="person-cell">
            <Avatar name={row.assignedToName} size="sm" tone="purple" />
            <span>{row.assignedToName}</span>
          </div>
        ) : (
          <span className="muted-cell">{t("cmms.common.none")}</span>
        ),
    },
  ];

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("cmms.wo.title")}
        subtitle={t("cmms.wo.subtitle")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceWorkOrderCreate}>
            <div className="cmms-header-actions">
              <Button variant="secondary" icon="refresh" onClick={generatePm}>
                {t("cmms.wo.generatePm")}
              </Button>
              <Button variant="primary" icon="plus" onClick={openCreate}>
                {t("cmms.wo.new")}
              </Button>
            </div>
          </PermissionGuard>
        }
      />

      <div className="metric-grid">
        <MetricCard label={t("cmms.metric.openWo")} value={openCount} icon="checkSquare" tone="amber" />
        <MetricCard label={t("cmms.woStatus.inProgress")} value={inProgressCount} icon="activity" tone="blue" />
        <MetricCard label={t("cmms.metric.totalDevices")} value={devices.length} icon="cpu" tone="purple" />
      </div>

      <Card className="content-card" padding="none">
        <div className="view-toolbar">
          <div className="segmented-control" role="tablist" aria-label={t("cmms.wo.title")}>
            {(["list", "board"] as const).map((item) => (
              <button
                key={item}
                role="tab"
                aria-selected={view === item}
                className={view === item ? "is-active" : ""}
                onClick={() => setView(item)}
              >
                {item === "list" ? t("cmms.wo.list") : t("cmms.wo.board")}
              </button>
            ))}
          </div>
          <div className="list-toolbar">
            <div className="search-box">
              <Icon name="search" size={16} />
              <input
                value={search}
                aria-label={t("cmms.wo.search")}
                placeholder={t("cmms.wo.search")}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <SelectInput
              aria-label={t("cmms.wo.status")}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              options={[
                { value: "all", label: t("cmms.common.all") },
                ...WO_STATUSES.map((status) => ({
                  value: status,
                  label: t(`cmms.woStatus.${status}`),
                })),
              ]}
            />
            <SelectInput
              aria-label={t("cmms.wo.department")}
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
        {view === "list" ? (
          <DataTable
            columns={columns}
            data={filtered}
            rowKey={(row) => row.id}
            search=""
            empty={{ title: t("cmms.wo.empty") }}
            exportName="tekarai-work-orders"
          />
        ) : (
          <WorkOrderBoard orders={filtered} onOpen={setActiveOrder} deviceNames={deviceNames} />
        )}
      </Card>

      <Modal
        open={createOpen}
        title={t("cmms.wo.createTitle")}
        onClose={() => setCreateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={submitOrder}>
              {t("cmms.wo.save")}
            </Button>
          </>
        }
      >
        <SelectInput
          label={t("cmms.wo.device")}
          value={formDevice}
          onChange={(event) => setFormDevice(event.target.value)}
          options={devices.map((device) => ({
            value: device.id,
            label: `${device.code} — ${device.name}`,
          }))}
        />
        <TextInput
          label={t("cmms.wo.woTitle")}
          required
          value={formTitle}
          onChange={(event) => setFormTitle(event.target.value)}
          autoFocus
        />
        <TextArea
          label={t("cmms.wo.description")}
          value={formDescription}
          onChange={(event) => setFormDescription(event.target.value)}
        />
        <div className="form-grid form-grid--compact">
          <SelectInput
            label={t("cmms.wo.type")}
            value={formType}
            onChange={(event) => setFormType(event.target.value as WorkOrderType)}
            options={WO_TYPES.map((type) => ({ value: type, label: t(`cmms.type.${type}`) }))}
          />
          <SelectInput
            label={t("cmms.wo.priority")}
            value={formPriority}
            onChange={(event) => setFormPriority(event.target.value as Priority)}
            options={PRIORITIES.map((priority) => ({
              value: priority,
              label: t(`cmms.priority.${priority}`),
            }))}
          />
        </div>
        <SelectInput
          label={t("cmms.wo.department")}
          value={formDepartment}
          onChange={(event) => setFormDepartment(event.target.value as MaintenanceDepartment | "")}
          options={[
            { value: "", label: t("cmms.wo.departmentInherit") },
            ...DEPARTMENTS.map((department) => ({
              value: department,
              label: t(`cmms.department.${department}`),
            })),
          ]}
        />
        <TextInput
          label={t("cmms.wo.requestedBy")}
          value={formRequestedBy}
          onChange={(event) => setFormRequestedBy(event.target.value)}
        />
      </Modal>

      <Modal
        open={Boolean(assignOrder)}
        title={t("cmms.wo.assignTitle")}
        onClose={() => setAssignOrder(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignOrder(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={assign}>
              {t("cmms.wo.assign")}
            </Button>
          </>
        }
      >
        <TextInput
          label={t("cmms.wo.technicianName")}
          required
          value={technicianName}
          onChange={(event) => setTechnicianName(event.target.value)}
          autoFocus
        />
      </Modal>

      <Modal
        open={Boolean(routeOrder)}
        title={t("cmms.wo.routeTitle")}
        onClose={() => setRouteOrder(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRouteOrder(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={route}>
              {t("cmms.wo.route")}
            </Button>
          </>
        }
      >
        <p className="detail-panel__description">{t("cmms.wo.routeHelp")}</p>
        <SelectInput
          label={t("cmms.wo.department")}
          value={routeDepartment}
          onChange={(event) => setRouteDepartment(event.target.value as MaintenanceDepartment)}
          options={DEPARTMENTS.map((department) => ({
            value: department,
            label: t(`cmms.department.${department}`),
          }))}
        />
      </Modal>

      <Modal
        open={Boolean(activeOrder)}
        title={activeOrder?.title ?? t("cmms.wo.detailTitle")}
        onClose={() => setActiveOrder(null)}
        footer={
          <Button variant="secondary" onClick={() => setActiveOrder(null)}>
            {t("cmms.common.close")}
          </Button>
        }
      >
        {activeOrder && (
          <div className="detail-panel">
            <div className="detail-stats">
              <div>
                <span>{t("cmms.wo.device")}</span>
                <strong>{deviceNames.get(activeOrder.deviceId) ?? activeOrder.deviceId}</strong>
              </div>
              <div>
                <span>{t("cmms.wo.type")}</span>
                <strong>{t(`cmms.type.${activeOrder.orderType}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.wo.status")}</span>
                <strong>{t(`cmms.woStatus.${activeOrder.status}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.wo.department")}</span>
                <strong>{t(`cmms.department.${activeOrder.department}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.wo.priority")}</span>
                <strong>{t(`cmms.priority.${activeOrder.priority}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.wo.requestedBy")}</span>
                <strong>{activeOrder.requestedByName || t("cmms.common.none")}</strong>
              </div>
              <div>
                <span>{t("cmms.wo.assignedTo")}</span>
                <strong>{activeOrder.assignedToName || t("cmms.common.none")}</strong>
              </div>
            </div>
            {activeOrder.description && (
              <p className="detail-panel__description">{activeOrder.description}</p>
            )}
            {activeOrder.resolutionNote && (
              <p className="detail-panel__description">
                {t("cmms.wo.resolution")}: {activeOrder.resolutionNote}
              </p>
            )}

            <PermissionGuard permission={PERMISSIONS.maintenanceWorkOrderRoute}>
              {(activeOrder.status === "submitted" || activeOrder.status === "routed") && (
                <Button
                  variant="secondary"
                  icon="send"
                  onClick={() => {
                    setRouteDepartment(activeOrder.department);
                    setRouteOrder(activeOrder);
                    setActiveOrder(null);
                  }}
                >
                  {t("cmms.wo.route")}
                </Button>
              )}
            </PermissionGuard>

            <PermissionGuard permission={PERMISSIONS.maintenanceWorkOrderAssign}>
              {(activeOrder.status === "submitted" || activeOrder.status === "routed") && (
                <Button
                  variant="secondary"
                  icon="user"
                  onClick={() => {
                    setAssignOrder(activeOrder);
                    setActiveOrder(null);
                  }}
                >
                  {t("cmms.wo.assign")}
                </Button>
              )}
            </PermissionGuard>

            <PermissionGuard permission={PERMISSIONS.maintenanceWorkOrderUpdate}>
              {NEXT_STATUSES[activeOrder.status].length > 0 && (
                <div className="cmms-transition-row">
                  {NEXT_STATUSES[activeOrder.status].map((target) => (
                    <Button
                      key={target}
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const current = activeOrder;
                        setActiveOrder(null);
                        void changeStatus(current, target);
                      }}
                    >
                      {t(`cmms.woStatus.${target}`)}
                    </Button>
                  ))}
                </div>
              )}
            </PermissionGuard>
          </div>
        )}
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}

function WorkOrderBoard({
  orders,
  onOpen,
  deviceNames,
}: {
  orders: WorkOrder[];
  onOpen: (order: WorkOrder) => void;
  deviceNames: Map<string, string>;
}): JSX.Element {
  const { t } = useLocalization();
  const boardColumns: WorkOrderStatus[] = [
    "submitted",
    "routed",
    "assigned",
    "inProgress",
    "onHold",
    "completed",
  ];
  return (
    <div className="kanban">
      {boardColumns.map((column) => (
        <section className="kanban-column" key={column}>
          <header>
            <h3>{t(`cmms.woStatus.${column}`)}</h3>
            <span>{orders.filter((order) => order.status === column).length}</span>
          </header>
          <div className="kanban-column__body">
            {orders
              .filter((order) => order.status === column)
              .map((order) => (
                <button
                  type="button"
                  className="task-card"
                  key={order.id}
                  onClick={() => onOpen(order)}
                >
                  <div className="task-card__top">
                    <Badge tone={priorityTone(order.priority)}>
                      {t(`cmms.priority.${order.priority}`)}
                    </Badge>
                    <Icon name="more" size={15} />
                  </div>
                  <strong>{order.title}</strong>
                  <span>{deviceNames.get(order.deviceId) ?? order.deviceId}</span>
                  <div className="task-card__bottom">
                    <Avatar
                      name={order.assignedToName || order.requestedByName || "?"}
                      size="sm"
                      tone="purple"
                    />
                    <span>{t(`cmms.type.${order.orderType}`)}</span>
                  </div>
                </button>
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}
