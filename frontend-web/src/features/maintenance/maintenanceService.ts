import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  DeviceMaintenanceReport,
  DeviceReportSummary,
  DeviceStatus,
  MaintenanceDepartment,
  MaintenanceDevice,
  Priority,
  WorkOrder,
  WorkOrderHistoryAction,
  WorkOrderHistoryEntry,
  WorkOrderStatus,
  WorkOrderType,
} from "../../shared/types/domain";

/** Wire shape of a device DTO returned by /api/v1/maintenance/devices (Phase 21). */
interface DeviceDto {
  id: string;
  code: string;
  name: string;
  location: string;
  status: string;
  department: string;
  pmIntervalDays: number;
  lastPmDate: string;
  nextDueDate: string;
  pmDue: boolean;
  createdAt: string;
}

/** Wire shape of a work-order DTO returned by /api/v1/maintenance/work-orders. */
interface WorkOrderDto {
  id: string;
  deviceId: string;
  title: string;
  description: string;
  orderType: string;
  priority: string;
  status: string;
  department: string;
  requestedByName: string;
  assignedToName: string;
  resolutionNote: string;
  createdAt: string;
  closedAt: string;
  slaDueAt: string;
  overdue: boolean;
}

interface WorkOrderHistoryDto {
  id: string;
  workOrderId: string;
  action: string;
  fromStatus: string;
  toStatus: string;
  fromDepartment: string;
  toDepartment: string;
  actorName: string;
  note: string;
  createdAt: string;
}

interface DeviceReportSummaryDto {
  totalOrders: number;
  openOrders: number;
  completedOrders: number;
  overdueOrders: number;
  byStatus: Record<string, number>;
  byType: Record<string, number>;
  byPriority: Record<string, number>;
  mttrHours: number | null;
}

interface DeviceMaintenanceReportDto {
  device: DeviceDto;
  workOrders: WorkOrderDto[];
  summary: DeviceReportSummaryDto | null;
  generatedAt: string;
  fromDate: string;
  toDate: string;
}

const toReportSummary = (
  dto: DeviceReportSummaryDto | null,
): DeviceReportSummary | null =>
  dto
    ? {
        totalOrders: dto.totalOrders ?? 0,
        openOrders: dto.openOrders ?? 0,
        completedOrders: dto.completedOrders ?? 0,
        overdueOrders: dto.overdueOrders ?? 0,
        byStatus: dto.byStatus ?? {},
        byType: dto.byType ?? {},
        byPriority: dto.byPriority ?? {},
        mttrHours: dto.mttrHours ?? null,
      }
    : null;

const toDevice = (dto: DeviceDto): MaintenanceDevice => ({
  id: dto.id,
  code: dto.code,
  name: dto.name,
  location: dto.location ?? "",
  status: (dto.status as DeviceStatus) ?? "operational",
  department: (dto.department as MaintenanceDepartment) ?? "general",
  pmIntervalDays: dto.pmIntervalDays ?? 0,
  lastPmDate: dto.lastPmDate ?? "",
  nextDueDate: dto.nextDueDate ?? "",
  pmDue: Boolean(dto.pmDue),
  createdAt: dto.createdAt ?? "",
});

const toWorkOrder = (dto: WorkOrderDto): WorkOrder => ({
  id: dto.id,
  deviceId: dto.deviceId,
  title: dto.title,
  description: dto.description ?? "",
  orderType: (dto.orderType as WorkOrderType) ?? "corrective",
  priority: (dto.priority as Priority) ?? "normal",
  status: (dto.status as WorkOrderStatus) ?? "submitted",
  department: (dto.department as MaintenanceDepartment) ?? "general",
  requestedByName: dto.requestedByName ?? "",
  assignedToName: dto.assignedToName ?? "",
  resolutionNote: dto.resolutionNote ?? "",
  createdAt: dto.createdAt ?? "",
  closedAt: dto.closedAt ?? "",
  slaDueAt: dto.slaDueAt ?? "",
  overdue: Boolean(dto.overdue),
});

const toHistoryEntry = (dto: WorkOrderHistoryDto): WorkOrderHistoryEntry => ({
  id: dto.id,
  workOrderId: dto.workOrderId,
  action: (dto.action as WorkOrderHistoryAction) ?? "statusChanged",
  fromStatus: dto.fromStatus ?? "",
  toStatus: dto.toStatus ?? "",
  fromDepartment: dto.fromDepartment ?? "",
  toDepartment: dto.toDepartment ?? "",
  actorName: dto.actorName ?? "",
  note: dto.note ?? "",
  createdAt: dto.createdAt ?? "",
});

export interface RegisterDeviceInput {
  code: string;
  name: string;
  location?: string;
  department?: MaintenanceDepartment;
  pmIntervalDays?: number;
}

export interface UpdateDeviceInput {
  name: string;
  location?: string;
  department?: MaintenanceDepartment;
  pmIntervalDays?: number;
}

export interface SubmitWorkOrderInput {
  deviceId: string;
  title: string;
  description?: string;
  orderType?: WorkOrderType;
  priority?: Priority;
  department?: MaintenanceDepartment | "";
  requestedByName?: string;
}

export interface MaintenanceService {
  listDevices: (
    filters?: { status?: string; department?: string; search?: string },
    signal?: AbortSignal,
  ) => Promise<MaintenanceDevice[]>;
  registerDevice: (input: RegisterDeviceInput, signal?: AbortSignal) => Promise<MaintenanceDevice>;
  updateDevice: (
    id: string,
    input: UpdateDeviceInput,
    signal?: AbortSignal,
  ) => Promise<MaintenanceDevice>;
  changeDeviceStatus: (
    id: string,
    target: DeviceStatus,
    signal?: AbortSignal,
  ) => Promise<MaintenanceDevice>;
  recordPm: (
    id: string,
    performedOn: string,
    signal?: AbortSignal,
  ) => Promise<MaintenanceDevice>;
  listDuePm: (signal?: AbortSignal) => Promise<MaintenanceDevice[]>;
  generatePmWorkOrders: (signal?: AbortSignal) => Promise<WorkOrder[]>;
  listWorkOrders: (
    filters?: { status?: string; deviceId?: string; department?: string; search?: string },
    signal?: AbortSignal,
  ) => Promise<WorkOrder[]>;
  submitWorkOrder: (input: SubmitWorkOrderInput, signal?: AbortSignal) => Promise<WorkOrder>;
  routeWorkOrder: (
    id: string,
    department: MaintenanceDepartment,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
  assignWorkOrder: (
    id: string,
    assignedToName: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
  autoAssignWorkOrder: (id: string, signal?: AbortSignal) => Promise<WorkOrder>;
  changeWorkOrderStatus: (
    id: string,
    target: WorkOrderStatus,
    resolutionNote?: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
  approveWorkOrder: (
    id: string,
    note?: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
  rejectWorkOrder: (
    id: string,
    note?: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
  listWorkOrderHistory: (
    id: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrderHistoryEntry[]>;
  getDeviceReport: (
    deviceId: string,
    range?: { fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<DeviceMaintenanceReport>;
  downloadDeviceReport: (
    deviceId: string,
    format: "csv" | "xlsx",
    range?: { fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<Blob>;
}

export const createMaintenanceService = (api: ApiClient): MaintenanceService => ({
  listDevices: async (filters = {}, signal) => {
    const dtos = await api.get<DeviceDto[]>(apiEndpoints.maintenance.devices, {
      signal,
      query: { ...filters, page: 1, pageSize: 100 },
    });
    return dtos.map(toDevice);
  },
  registerDevice: async (input, signal) => {
    const dto = await api.post<DeviceDto>(
      apiEndpoints.maintenance.devices,
      {
        code: input.code,
        name: input.name,
        location: input.location ?? "",
        department: input.department ?? "general",
        pmIntervalDays: input.pmIntervalDays ?? 0,
      },
      { signal, retry: 0 },
    );
    return toDevice(dto);
  },
  updateDevice: async (id, input, signal) => {
    const dto = await api.patch<DeviceDto>(
      apiEndpoints.maintenance.device(id),
      {
        name: input.name,
        location: input.location ?? "",
        department: input.department ?? "general",
        pmIntervalDays: input.pmIntervalDays ?? 0,
      },
      { signal, retry: 0 },
    );
    return toDevice(dto);
  },
  changeDeviceStatus: async (id, target, signal) => {
    const dto = await api.post<DeviceDto>(
      apiEndpoints.maintenance.deviceStatus(id),
      { target },
      { signal, retry: 0 },
    );
    return toDevice(dto);
  },
  recordPm: async (id, performedOn, signal) => {
    const dto = await api.post<DeviceDto>(
      apiEndpoints.maintenance.devicePm(id),
      { performedOn },
      { signal, retry: 0 },
    );
    return toDevice(dto);
  },
  listDuePm: async (signal) => {
    const dtos = await api.get<DeviceDto[]>(apiEndpoints.maintenance.devicesDuePm, { signal });
    return dtos.map(toDevice);
  },
  generatePmWorkOrders: async (signal) => {
    const dtos = await api.post<WorkOrderDto[]>(
      apiEndpoints.maintenance.workOrdersGeneratePm,
      {},
      { signal, retry: 0 },
    );
    return dtos.map(toWorkOrder);
  },
  listWorkOrders: async (filters = {}, signal) => {
    const dtos = await api.get<WorkOrderDto[]>(apiEndpoints.maintenance.workOrders, {
      signal,
      query: { ...filters, page: 1, pageSize: 100 },
    });
    return dtos.map(toWorkOrder);
  },
  submitWorkOrder: async (input, signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrders,
      {
        deviceId: input.deviceId,
        title: input.title,
        description: input.description ?? "",
        orderType: input.orderType ?? "corrective",
        priority: input.priority ?? "normal",
        department: input.department ?? "",
        requestedByName: input.requestedByName ?? "",
      },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  routeWorkOrder: async (id, department, signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderRoute(id),
      { department },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  assignWorkOrder: async (id, assignedToName, signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderAssign(id),
      { assignedToName },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  autoAssignWorkOrder: async (id, signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderAssign(id),
      { auto: true },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  changeWorkOrderStatus: async (id, target, resolutionNote = "", signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderStatus(id),
      { target, resolutionNote },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  approveWorkOrder: async (id, note = "", signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderApprove(id),
      { note },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  rejectWorkOrder: async (id, note = "", signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderReject(id),
      { note },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
  listWorkOrderHistory: async (id, signal) => {
    const dtos = await api.get<WorkOrderHistoryDto[]>(
      apiEndpoints.maintenance.workOrderHistory(id),
      { signal },
    );
    return dtos.map(toHistoryEntry);
  },
  getDeviceReport: async (deviceId, range = {}, signal) => {
    const dto = await api.get<DeviceMaintenanceReportDto>(
      apiEndpoints.maintenance.deviceReport(deviceId),
      {
        query: {
          fromDate: range.fromDate ?? "",
          toDate: range.toDate ?? "",
        },
        signal,
      },
    );
    return {
      device: toDevice(dto.device),
      workOrders: (dto.workOrders ?? []).map(toWorkOrder),
      summary: toReportSummary(dto.summary),
      generatedAt: dto.generatedAt ?? "",
      fromDate: dto.fromDate ?? "",
      toDate: dto.toDate ?? "",
    };
  },
  downloadDeviceReport: (deviceId, format, range = {}, signal) =>
    api.download(apiEndpoints.maintenance.deviceReport(deviceId), {
      query: {
        export: format,
        fromDate: range.fromDate ?? "",
        toDate: range.toDate ?? "",
      },
      signal,
    }),
});
