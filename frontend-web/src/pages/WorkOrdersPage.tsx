import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { formatJalali } from "../core/localization/jalali";
import type { TranslationKey } from "../core/localization/i18n";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices, demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import type {
  MaintenanceDepartment,
  MaintenanceDevice,
  Priority,
  SparePart,
  WorkOrder,
  WorkOrderPartUsage,
  WorkOrderHistoryEntry,
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
  "pendingApproval",
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
  inProgress: ["onHold", "pendingApproval", "cancelled"],
  onHold: ["inProgress", "cancelled"],
  // Completion/return from pendingApproval happens only via the approve/reject
  // endpoints (which enforce the approve permission), never the public status route.
  pendingApproval: ["cancelled"],
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
        : status === "pendingApproval"
          ? "purple"
          : status === "cancelled"
            ? "danger"
            : status === "assigned"
              ? "purple"
              : status === "routed"
                ? "info"
                : "neutral";

const priorityTone = (priority: Priority): "danger" | "warning" | "neutral" =>
  priority === "critical" ? "danger" : priority === "high" ? "warning" : "neutral";

const WO_STATUS_SET = new Set<string>([
  "submitted",
  "routed",
  "assigned",
  "inProgress",
  "onHold",
  "pendingApproval",
  "completed",
  "cancelled",
]);

const statusLabel = (
  t: (key: TranslationKey) => string,
  status: string,
): string =>
  WO_STATUS_SET.has(status)
    ? t(`cmms.woStatus.${status as WorkOrderStatus}`)
    : status;

const formatDateTime = (value: string): string =>
  value ? formatJalali(value, { withTime: true }) : "";

export function WorkOrdersPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const [orders, setOrders] = useState<WorkOrder[]>(runtimeConfig.demoMode ? demoWorkOrders : []);
  const [devices, setDevices] = useState<MaintenanceDevice[]>(
    runtimeConfig.demoMode ? demoDevices : [],
  );
  // Deep-link support: the maintenance dashboard links here with ?status= / ?department=
  // so clicking a chart segment lands on the matching, pre-filtered list.
  const initialFilters = useMemo(() => {
    if (typeof window === "undefined") return { status: "all", department: "all" };
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status");
    const department = params.get("department");
    return {
      status: status && WO_STATUSES.includes(status as WorkOrderStatus) ? status : "all",
      department:
        department && DEPARTMENTS.includes(department as MaintenanceDepartment)
          ? department
          : "all",
    };
  }, []);
  const [view, setView] = useState<"list" | "board">("list");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialFilters.status);
  const [departmentFilter, setDepartmentFilter] = useState(initialFilters.department);
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
  const [approveOrder, setApproveOrder] = useState<WorkOrder | null>(null);
  const [rejectOrder, setRejectOrder] = useState<WorkOrder | null>(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [history, setHistory] = useState<WorkOrderHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [parts, setParts] = useState<SparePart[]>([]);
  const [partUsage, setPartUsage] = useState<WorkOrderPartUsage[]>([]);
  const [inventoryOpen, setInventoryOpen] = useState(false);
  const [partCode, setPartCode] = useState("");
  const [partName, setPartName] = useState("");
  const [partUnit, setPartUnit] = useState("عدد");
  const [partStock, setPartStock] = useState("0");
  const [partMinimum, setPartMinimum] = useState("0");
  const [consumePartId, setConsumePartId] = useState("");
  const [consumeQuantity, setConsumeQuantity] = useState("1");
  const [consumeNote, setConsumeNote] = useState("");

  const deviceNames = useMemo(
    () => new Map(devices.map((device) => [device.id, `${device.code} — ${device.name}`])),
    [devices],
  );

  const refresh = useCallback(async (): Promise<void> => {
    if (runtimeConfig.demoMode) return;
    try {
      const [woList, deviceList, partList] = await Promise.all([
        service.listWorkOrders(),
        service.listDevices().catch(() => [] as MaintenanceDevice[]),
        service.listSpareParts().catch(() => [] as SparePart[]),
      ]);
      setOrders(woList);
      setDevices(deviceList);
      setParts(partList);
    } catch {
      /* keep last known state */
    }
  }, [service]);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!activeOrder) {
      setHistory([]);
      return;
    }
    if (runtimeConfig.demoMode) {
      setHistory([]);
      return;
    }
    const controller = new AbortController();
    setHistoryLoading(true);
    service
      .listWorkOrderHistory(activeOrder.id, controller.signal)
      .then((entries) => setHistory(entries))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
    return () => controller.abort();
  }, [activeOrder, service]);

  useEffect(() => {
    if (!activeOrder || runtimeConfig.demoMode) {
      setPartUsage([]);
      return;
    }
    const controller = new AbortController();
    service
      .listWorkOrderParts(activeOrder.id, controller.signal)
      .then(setPartUsage)
      .catch(() => setPartUsage([]));
    return () => controller.abort();
  }, [activeOrder, service]);

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

  const autoAssign = async (order: WorkOrder): Promise<void> => {
    if (runtimeConfig.demoMode) {
      setToast(t("cmms.wo.autoAssignDemo"));
      return;
    }
    try {
      await service.autoAssignWorkOrder(order.id);
      setToast(t("cmms.wo.autoAssignSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const approve = async (): Promise<void> => {
    if (!approveOrder) return;
    if (runtimeConfig.demoMode) {
      setOrders((current) =>
        current.map((item) =>
          item.id === approveOrder.id ? { ...item, status: "completed" } : item,
        ),
      );
      setApproveOrder(null);
      setDecisionNote("");
      setToast(t("cmms.wo.approveSuccess"));
      return;
    }
    try {
      await service.approveWorkOrder(approveOrder.id, decisionNote.trim());
      setApproveOrder(null);
      setDecisionNote("");
      setToast(t("cmms.wo.approveSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const reject = async (): Promise<void> => {
    if (!rejectOrder) return;
    if (runtimeConfig.demoMode) {
      setOrders((current) =>
        current.map((item) =>
          item.id === rejectOrder.id ? { ...item, status: "inProgress" } : item,
        ),
      );
      setRejectOrder(null);
      setDecisionNote("");
      setToast(t("cmms.wo.rejectSuccess"));
      return;
    }
    try {
      await service.rejectWorkOrder(rejectOrder.id, decisionNote.trim());
      setRejectOrder(null);
      setDecisionNote("");
      setToast(t("cmms.wo.rejectSuccess"));
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("cmms.wo.saveFailed"));
    }
  };

  const createPart = async (): Promise<void> => {
    if (!partCode.trim() || !partName.trim()) return;
    if (runtimeConfig.demoMode) {
      setParts((current) => [
        ...current,
        {
          id: `part-${Date.now()}`,
          code: partCode.trim().toUpperCase(),
          name: partName.trim(),
          unit: partUnit.trim() || "عدد",
          quantityOnHand: Number(partStock),
          minimumStock: Number(partMinimum),
          lowStock: Number(partStock) <= Number(partMinimum),
          createdAt: new Date().toISOString(),
          updatedAt: "",
        },
      ]);
      setPartCode("");
      setPartName("");
      setToast("قطعه با موفقیت در انبار ثبت شد.");
      return;
    }
    try {
      await service.createSparePart({
        code: partCode.trim(),
        name: partName.trim(),
        unit: partUnit.trim() || "عدد",
        quantityOnHand: Number(partStock),
        minimumStock: Number(partMinimum),
      });
      setPartCode("");
      setPartName("");
      setPartStock("0");
      setPartMinimum("0");
      setToast("قطعه با موفقیت در انبار ثبت شد.");
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "ثبت قطعه انجام نشد.");
    }
  };

  const consumePart = async (): Promise<void> => {
    if (!activeOrder || !consumePartId || Number(consumeQuantity) <= 0) return;
    const selectedPart = parts.find((part) => part.id === consumePartId);
    const requestedQuantity = Number(consumeQuantity);
    if (!selectedPart || selectedPart.quantityOnHand < requestedQuantity) {
      setToast("موجودی قطعه کافی نیست.");
      return;
    }
    if (runtimeConfig.demoMode) {
      setParts((current) => current.map((part) =>
        part.id === selectedPart.id
          ? {
              ...part,
              quantityOnHand: part.quantityOnHand - requestedQuantity,
              lowStock: part.quantityOnHand - requestedQuantity <= part.minimumStock,
            }
          : part,
      ));
      setPartUsage((current) => [{
        id: `usage-${Date.now()}`,
        workOrderId: activeOrder.id,
        partId: selectedPart.id,
        partCode: selectedPart.code,
        partName: selectedPart.name,
        unit: selectedPart.unit,
        quantity: requestedQuantity,
        note: consumeNote.trim(),
        consumedAt: new Date().toISOString(),
      }, ...current]);
      setConsumeQuantity("1");
      setConsumeNote("");
      setToast("قطعه مصرفی ثبت و از موجودی انبار کسر شد.");
      return;
    }
    try {
      await service.consumeSparePart(
        activeOrder.id,
        consumePartId,
        Number(consumeQuantity),
        consumeNote.trim(),
      );
      const [usage, inventory] = await Promise.all([
        service.listWorkOrderParts(activeOrder.id),
        service.listSpareParts(),
      ]);
      setPartUsage(usage);
      setParts(inventory);
      setConsumeQuantity("1");
      setConsumeNote("");
      setToast("قطعه مصرفی ثبت و از موجودی انبار کسر شد.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "موجودی قطعه کافی نیست.");
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
              <Button variant="secondary" icon="layers" onClick={() => setInventoryOpen(true)}>
                انبار قطعات
              </Button>
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
        open={inventoryOpen}
        title="انبار قطعات یدکی"
        onClose={() => setInventoryOpen(false)}
        footer={
          <Button variant="secondary" onClick={() => setInventoryOpen(false)}>
            {t("cmms.common.close")}
          </Button>
        }
      >
        <PermissionGuard permission={PERMISSIONS.maintenanceInventoryManage}>
          <div className="form-grid form-grid--compact">
            <TextInput label="کد قطعه" required value={partCode} onChange={(event) => setPartCode(event.target.value)} />
            <TextInput label="نام قطعه" required value={partName} onChange={(event) => setPartName(event.target.value)} />
            <TextInput label="واحد" value={partUnit} onChange={(event) => setPartUnit(event.target.value)} />
            <TextInput label="موجودی اولیه" type="number" min="0" step="0.001" value={partStock} onChange={(event) => setPartStock(event.target.value)} />
            <TextInput label="حداقل موجودی" type="number" min="0" step="0.001" value={partMinimum} onChange={(event) => setPartMinimum(event.target.value)} />
            <Button variant="primary" icon="plus" onClick={createPart}>ثبت قطعه</Button>
          </div>
        </PermissionGuard>
        <div className="cmms-timeline">
          <h4 className="cmms-timeline__title">موجودی فعلی</h4>
          {parts.length === 0 ? (
            <p className="detail-panel__description">هنوز قطعه‌ای در انبار ثبت نشده است.</p>
          ) : (
            <div className="detail-stats">
              {parts.map((part) => (
                <div key={part.id}>
                  <span>{part.code} — {part.name}</span>
                  <strong>
                    {part.quantityOnHand} {part.unit}{" "}
                    {part.lowStock && <Badge tone="danger">کمبود موجودی</Badge>}
                  </strong>
                </div>
              ))}
            </div>
          )}
        </div>
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
              {activeOrder.slaDueAt && (
                <div>
                  <span>{t("cmms.wo.slaDue")}</span>
                  <strong>
                    {formatDateTime(activeOrder.slaDueAt)}{" "}
                    {activeOrder.overdue && (
                      <Badge tone="danger" dot>
                        {t("cmms.wo.overdue")}
                      </Badge>
                    )}
                  </strong>
                </div>
              )}
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
                <div className="cmms-transition-row">
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
                  <Button
                    variant="secondary"
                    icon="sparkles"
                    onClick={() => {
                      const current = activeOrder;
                      setActiveOrder(null);
                      void autoAssign(current);
                    }}
                  >
                    {t("cmms.wo.autoAssign")}
                  </Button>
                </div>
              )}
            </PermissionGuard>

            <PermissionGuard permission={PERMISSIONS.maintenanceWorkOrderApprove}>
              {activeOrder.status === "pendingApproval" && (
                <div className="cmms-transition-row">
                  <Button
                    variant="primary"
                    icon="check"
                    onClick={() => {
                      setDecisionNote("");
                      setApproveOrder(activeOrder);
                      setActiveOrder(null);
                    }}
                  >
                    {t("cmms.wo.approve")}
                  </Button>
                  <Button
                    variant="danger"
                    icon="close"
                    onClick={() => {
                      setDecisionNote("");
                      setRejectOrder(activeOrder);
                      setActiveOrder(null);
                    }}
                  >
                    {t("cmms.wo.reject")}
                  </Button>
                </div>
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

            <div className="cmms-timeline">
              <h4 className="cmms-timeline__title">قطعات مصرفی</h4>
              <PermissionGuard permission={PERMISSIONS.maintenanceInventoryConsume}>
                <div className="form-grid form-grid--compact">
                  <SelectInput
                    label="قطعه انبار"
                    value={consumePartId}
                    onChange={(event) => setConsumePartId(event.target.value)}
                    options={[
                      { value: "", label: "انتخاب قطعه" },
                      ...parts
                        .filter((part) => part.quantityOnHand > 0)
                        .map((part) => ({
                          value: part.id,
                          label: `${part.code} — ${part.name} (${part.quantityOnHand} ${part.unit})`,
                        })),
                    ]}
                  />
                  <TextInput
                    label="مقدار مصرف"
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={consumeQuantity}
                    onChange={(event) => setConsumeQuantity(event.target.value)}
                  />
                  <TextInput
                    label="یادداشت"
                    value={consumeNote}
                    onChange={(event) => setConsumeNote(event.target.value)}
                  />
                  <Button variant="secondary" icon="minus" onClick={consumePart}>
                    ثبت مصرف و کسر موجودی
                  </Button>
                </div>
              </PermissionGuard>
              {partUsage.length === 0 ? (
                <p className="detail-panel__description">هنوز قطعه‌ای برای این درخواست ثبت نشده است.</p>
              ) : (
                <ol className="cmms-timeline__list">
                  {partUsage.map((usage) => (
                    <li key={usage.id} className="cmms-timeline__item">
                      <span className="cmms-timeline__dot" />
                      <div className="cmms-timeline__body">
                        <div className="cmms-timeline__head">
                          <strong>{usage.partCode} — {usage.partName}</strong>
                          <span>{usage.quantity} {usage.unit}</span>
                        </div>
                        <div className="cmms-timeline__meta">
                          <span>{formatDateTime(usage.consumedAt)}</span>
                        </div>
                        {usage.note && <p className="cmms-timeline__note">{usage.note}</p>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div className="cmms-timeline">
              <h4 className="cmms-timeline__title">{t("cmms.wo.timeline")}</h4>
              {historyLoading ? (
                <p className="detail-panel__description">{t("cmms.common.loading")}</p>
              ) : history.length === 0 ? (
                <p className="detail-panel__description">{t("cmms.wo.timelineEmpty")}</p>
              ) : (
                <ol className="cmms-timeline__list">
                  {history.map((entry) => (
                    <li key={entry.id} className="cmms-timeline__item">
                      <span className="cmms-timeline__dot" />
                      <div className="cmms-timeline__body">
                        <div className="cmms-timeline__head">
                          <strong>{t(`cmms.historyAction.${entry.action}`)}</strong>
                          <span className="muted-cell">{formatDateTime(entry.createdAt)}</span>
                        </div>
                        <div className="cmms-timeline__meta">
                          {entry.fromStatus && entry.toStatus && (
                            <span>
                              {statusLabel(t, entry.fromStatus)}
                              {" → "}
                              {statusLabel(t, entry.toStatus)}
                            </span>
                          )}
                          {entry.actorName && <span>· {entry.actorName}</span>}
                        </div>
                        {entry.note && (
                          <p className="cmms-timeline__note">{entry.note}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(approveOrder)}
        title={t("cmms.wo.approveTitle")}
        onClose={() => setApproveOrder(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setApproveOrder(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="primary" icon="check" onClick={approve}>
              {t("cmms.wo.approve")}
            </Button>
          </>
        }
      >
        <p className="detail-panel__description">{t("cmms.wo.approveHelp")}</p>
        <TextArea
          label={t("cmms.wo.decisionNote")}
          value={decisionNote}
          onChange={(event) => setDecisionNote(event.target.value)}
          autoFocus
        />
      </Modal>

      <Modal
        open={Boolean(rejectOrder)}
        title={t("cmms.wo.rejectTitle")}
        onClose={() => setRejectOrder(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejectOrder(null)}>
              {t("cmms.common.cancel")}
            </Button>
            <Button variant="danger" icon="close" onClick={reject}>
              {t("cmms.wo.reject")}
            </Button>
          </>
        }
      >
        <p className="detail-panel__description">{t("cmms.wo.rejectHelp")}</p>
        <TextArea
          label={t("cmms.wo.decisionNote")}
          value={decisionNote}
          onChange={(event) => setDecisionNote(event.target.value)}
          autoFocus
        />
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
