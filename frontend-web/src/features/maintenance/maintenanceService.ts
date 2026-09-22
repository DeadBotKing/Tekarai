import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  DeviceStatus,
  MaintenanceDevice,
  Priority,
  WorkOrder,
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
  requestedByName: string;
  assignedToName: string;
  resolutionNote: string;
  createdAt: string;
  closedAt: string;
}

const toDevice = (dto: DeviceDto): MaintenanceDevice => ({
  id: dto.id,
  code: dto.code,
  name: dto.name,
  location: dto.location ?? "",
  status: (dto.status as DeviceStatus) ?? "operational",
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
  requestedByName: dto.requestedByName ?? "",
  assignedToName: dto.assignedToName ?? "",
  resolutionNote: dto.resolutionNote ?? "",
  createdAt: dto.createdAt ?? "",
  closedAt: dto.closedAt ?? "",
});

export interface RegisterDeviceInput {
  code: string;
  name: string;
  location?: string;
  pmIntervalDays?: number;
}

export interface UpdateDeviceInput {
  name: string;
  location?: string;
  pmIntervalDays?: number;
}

export interface SubmitWorkOrderInput {
  deviceId: string;
  title: string;
  description?: string;
  orderType?: WorkOrderType;
  priority?: Priority;
  requestedByName?: string;
}

export interface MaintenanceService {
  listDevices: (
    filters?: { status?: string; search?: string },
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
  listWorkOrders: (
    filters?: { status?: string; deviceId?: string; search?: string },
    signal?: AbortSignal,
  ) => Promise<WorkOrder[]>;
  submitWorkOrder: (input: SubmitWorkOrderInput, signal?: AbortSignal) => Promise<WorkOrder>;
  assignWorkOrder: (
    id: string,
    assignedToName: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
  changeWorkOrderStatus: (
    id: string,
    target: WorkOrderStatus,
    resolutionNote?: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrder>;
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
        requestedByName: input.requestedByName ?? "",
      },
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
  changeWorkOrderStatus: async (id, target, resolutionNote = "", signal) => {
    const dto = await api.post<WorkOrderDto>(
      apiEndpoints.maintenance.workOrderStatus(id),
      { target, resolutionNote },
      { signal, retry: 0 },
    );
    return toWorkOrder(dto);
  },
});
