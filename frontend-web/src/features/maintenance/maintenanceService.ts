import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  DeviceMaintenanceReport,
  DeviceReportSummary,
  DeviceStatus,
  DeviceTimeline,
  DeviceTimelineAction,
  DeviceTimelineItem,
  DeviceTimelineSource,
  LabourEntry,
  MaintenanceAttachment,
  MaintenanceAttachmentCategory,
  MaintenanceDepartment,
  MaintenanceDevice,
  Priority,
  SparePart,
  WorkOrder,
  WorkOrderCostSummary,
  WorkOrderPartUsage,
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

interface MaintenanceAttachmentDto {
  id: string;
  targetType: "device" | "workOrder";
  targetId: string;
  category: MaintenanceAttachmentCategory;
  originalName: string;
  mimeType: string;
  sizeBytes: number;
  uploadedAt: string;
  downloadUrl: string;
}

interface SparePartDto {
  id: string;
  code: string;
  name: string;
  unit: string;
  quantityOnHand: string;
  minimumStock: string;
  unitCost: string;
  lowStock: boolean;
  createdAt: string;
  updatedAt: string;
}

interface WorkOrderPartUsageDto {
  id: string;
  workOrderId: string;
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  quantity: string;
  unitCost: string;
  totalCost: string;
  note: string;
  consumedAt: string;
}

interface LabourEntryDto {
  id: string;
  workOrderId: string;
  technicianName: string;
  hours: string;
  hourlyRate: string;
  totalCost: string;
  workedAt: string;
  note: string;
  createdAt: string;
}

interface WorkOrderCostSummaryDto {
  workOrderId: string;
  title: string;
  status: string;
  deviceId: string;
  assignedToName: string;
  labourHours: string;
  labourCost: string;
  partsCost: string;
  totalCost: string;
  labourEntries: LabourEntryDto[];
  partUsages: WorkOrderPartUsageDto[];
}

/** Money comes off the wire as decimal strings (see toCostSummary); numbers here. */
export interface MaintenanceCostReport {
  fromDate: string;
  toDate: string;
  generatedAt: string;
  workOrderCount: number;
  totalLabourHours: number;
  totalLabourCost: number;
  totalPartsCost: number;
  totalCost: number;
  byDevice: Array<{ key: string; label: string; workOrderCount: number; totalCost: number }>;
  byDepartment: Array<{ key: string; label: string; workOrderCount: number; totalCost: number }>;
  byTechnician: Array<{ technicianName: string; entryCount: number; hours: number; cost: number }>;
  itemCount: number;
}

interface MaintenanceCostReportDto {
  fromDate: string;
  toDate: string;
  generatedAt: string;
  workOrderCount: number;
  totalLabourHours: string;
  totalLabourCost: string;
  totalPartsCost: string;
  totalCost: string;
  items: unknown[];
  byDevice: Array<{ key: string; label: string; workOrderCount: number; labourHours: string; labourCost: string; partsCost: string; totalCost: string }>;
  byDepartment: Array<{ key: string; label: string; workOrderCount: number; labourHours: string; labourCost: string; partsCost: string; totalCost: string }>;
  byTechnician: Array<{ technicianName: string; entryCount: number; hours: string; cost: string }>;
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

interface DeviceTimelineItemDto {
  id: string;
  source: string;
  action: string;
  at: string;
  fromStatus: string;
  toStatus: string;
  note: string;
  actorName: string;
  workOrderId: string;
  workOrderTitle: string;
  orderType: string;
  priority: string;
}

interface DeviceTimelineDto {
  device: DeviceDto;
  items: DeviceTimelineItemDto[];
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

const toSparePart = (dto: SparePartDto): SparePart => ({
  id: dto.id,
  code: dto.code,
  name: dto.name,
  unit: dto.unit,
  quantityOnHand: Number(dto.quantityOnHand),
  minimumStock: Number(dto.minimumStock),
  unitCost: Number(dto.unitCost ?? 0),
  lowStock: Boolean(dto.lowStock),
  createdAt: dto.createdAt ?? "",
  updatedAt: dto.updatedAt ?? "",
});

const toPartUsage = (dto: WorkOrderPartUsageDto): WorkOrderPartUsage => ({
  id: dto.id,
  workOrderId: dto.workOrderId,
  partId: dto.partId,
  partCode: dto.partCode,
  partName: dto.partName,
  unit: dto.unit,
  quantity: Number(dto.quantity),
  unitCost: Number(dto.unitCost ?? 0),
  totalCost: Number(dto.totalCost ?? 0),
  note: dto.note ?? "",
  consumedAt: dto.consumedAt ?? "",
});

const toLabourEntry = (dto: LabourEntryDto): LabourEntry => ({
  id: dto.id,
  workOrderId: dto.workOrderId,
  technicianName: dto.technicianName,
  hours: Number(dto.hours),
  hourlyRate: Number(dto.hourlyRate),
  totalCost: Number(dto.totalCost ?? 0),
  workedAt: dto.workedAt ?? "",
  note: dto.note ?? "",
  createdAt: dto.createdAt ?? "",
});

const toCostSummary = (dto: WorkOrderCostSummaryDto): WorkOrderCostSummary => ({
  workOrderId: dto.workOrderId,
  title: dto.title ?? "",
  status: dto.status ?? "",
  deviceId: dto.deviceId,
  assignedToName: dto.assignedToName ?? "",
  labourHours: Number(dto.labourHours ?? 0),
  labourCost: Number(dto.labourCost ?? 0),
  partsCost: Number(dto.partsCost ?? 0),
  totalCost: Number(dto.totalCost ?? 0),
  labourEntries: (dto.labourEntries ?? []).map(toLabourEntry),
  partUsages: (dto.partUsages ?? []).map(toPartUsage),
});

const toCostGroupEntry = (dto: {
  key: string;
  label: string;
  workOrderCount: number;
  totalCost: string;
}): { key: string; label: string; workOrderCount: number; totalCost: number } => ({
  key: dto.key ?? "",
  label: dto.label ?? "",
  workOrderCount: Number(dto.workOrderCount ?? 0),
  totalCost: Number(dto.totalCost ?? 0),
});

export const toMaintenanceCostReport = (dto: MaintenanceCostReportDto): MaintenanceCostReport => ({
  fromDate: dto.fromDate ?? "",
  toDate: dto.toDate ?? "",
  generatedAt: dto.generatedAt ?? "",
  workOrderCount: Number(dto.workOrderCount ?? 0),
  totalLabourHours: Number(dto.totalLabourHours ?? 0),
  totalLabourCost: Number(dto.totalLabourCost ?? 0),
  totalPartsCost: Number(dto.totalPartsCost ?? 0),
  totalCost: Number(dto.totalCost ?? 0),
  byDevice: (dto.byDevice ?? []).map(toCostGroupEntry),
  byDepartment: (dto.byDepartment ?? []).map(toCostGroupEntry),
  byTechnician: (dto.byTechnician ?? []).map((entry) => ({
    technicianName: entry.technicianName ?? "",
    entryCount: Number(entry.entryCount ?? 0),
    hours: Number(entry.hours ?? 0),
    cost: Number(entry.cost ?? 0),
  })),
  itemCount: (dto.items ?? []).length,
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

const toTimelineItem = (dto: DeviceTimelineItemDto): DeviceTimelineItem => ({
  id: dto.id,
  source: (dto.source as DeviceTimelineSource) ?? "device",
  action: (dto.action as DeviceTimelineAction) ?? "statusChanged",
  at: dto.at ?? "",
  fromStatus: dto.fromStatus ?? "",
  toStatus: dto.toStatus ?? "",
  note: dto.note ?? "",
  actorName: dto.actorName ?? "",
  workOrderId: dto.workOrderId ?? "",
  workOrderTitle: dto.workOrderTitle ?? "",
  orderType: dto.orderType ?? "",
  priority: dto.priority ?? "",
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

export interface CreateSparePartInput {
  code: string;
  name: string;
  unit?: string;
  quantityOnHand: number;
  minimumStock?: number;
  unitCost?: number;
}

export interface LogLabourEntryInput {
  technicianName: string;
  hours: number;
  hourlyRate?: number;
  workedAt?: string;
  note?: string;
}

export interface MaintenanceService {
  listAttachments: (
    targetType: "device" | "workOrder",
    targetId: string,
    signal?: AbortSignal,
  ) => Promise<MaintenanceAttachment[]>;
  uploadAttachment: (
    targetType: "device" | "workOrder",
    targetId: string,
    category: MaintenanceAttachmentCategory,
    file: File,
    onProgress?: (progress: number) => void,
    signal?: AbortSignal,
  ) => Promise<MaintenanceAttachment>;
  downloadAttachment: (id: string, signal?: AbortSignal) => Promise<Blob>;
  deleteAttachment: (id: string, signal?: AbortSignal) => Promise<void>;
  listSpareParts: (search?: string, signal?: AbortSignal) => Promise<SparePart[]>;
  createSparePart: (input: CreateSparePartInput, signal?: AbortSignal) => Promise<SparePart>;
  updateSparePart: (
    id: string,
    input: Omit<CreateSparePartInput, "code">,
    signal?: AbortSignal,
  ) => Promise<SparePart>;
  listWorkOrderParts: (id: string, signal?: AbortSignal) => Promise<WorkOrderPartUsage[]>;
  consumeSparePart: (
    workOrderId: string,
    partId: string,
    quantity: number,
    note?: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrderPartUsage>;
  // Time & cost tracking (ثبت زمان و هزینه).
  listLabourEntries: (id: string, signal?: AbortSignal) => Promise<LabourEntry[]>;
  logLabourEntry: (
    workOrderId: string,
    input: LogLabourEntryInput,
    signal?: AbortSignal,
  ) => Promise<LabourEntry>;
  deleteLabourEntry: (id: string, signal?: AbortSignal) => Promise<LabourEntry>;
  getWorkOrderCostSummary: (
    id: string,
    signal?: AbortSignal,
  ) => Promise<WorkOrderCostSummary>;
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
  /**
   * Download the work-order list as a file (گزارش خروجی) honouring the same
   * filters as the on-screen list; format ∈ csv | xlsx | pdf (Phase 28).
   */
  downloadWorkOrdersExport: (
    format: "csv" | "xlsx" | "pdf",
    filters?: { status?: string; deviceId?: string; department?: string; search?: string },
    signal?: AbortSignal,
  ) => Promise<Blob>;
  /** Tenant-wide time-and-cost report (زمان و هزینه) for dashboard KPIs. */
  getMaintenanceCostReport: (
    range?: { fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<MaintenanceCostReport>;
  /** Download the cost report as a file (CSV / Excel / PDF). */
  downloadCostReportExport: (
    format: "csv" | "xlsx" | "pdf",
    range?: { fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<Blob>;
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
    format: "csv" | "xlsx" | "pdf",
    range?: { fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<Blob>;
  getDeviceTimeline: (
    deviceId: string,
    signal?: AbortSignal,
  ) => Promise<DeviceTimeline>;
}

export const createMaintenanceService = (api: ApiClient): MaintenanceService => ({
  listAttachments: (targetType, targetId, signal) =>
    api.get<MaintenanceAttachmentDto[]>(
      targetType === "device"
        ? apiEndpoints.maintenance.deviceAttachments(targetId)
        : apiEndpoints.maintenance.workOrderAttachments(targetId),
      { signal },
    ),
  uploadAttachment: (targetType, targetId, category, file, onProgress, signal) =>
    api.upload<MaintenanceAttachmentDto>(
      targetType === "device"
        ? apiEndpoints.maintenance.deviceAttachments(targetId)
        : apiEndpoints.maintenance.workOrderAttachments(targetId),
      file,
      { fields: { category }, onProgress, signal },
    ),
  downloadAttachment: (id, signal) =>
    api.download(apiEndpoints.maintenance.maintenanceAttachmentDownload(id), { signal }),
  deleteAttachment: async (id, signal) => {
    await api.delete<null>(apiEndpoints.maintenance.maintenanceAttachment(id), {
      signal,
      retry: 0,
    });
  },
  listSpareParts: async (search = "", signal) => {
    const dtos = await api.get<SparePartDto[]>(apiEndpoints.maintenance.spareParts, {
      query: { search },
      signal,
    });
    return dtos.map(toSparePart);
  },
  createSparePart: async (input, signal) => {
    const dto = await api.post<SparePartDto>(
      apiEndpoints.maintenance.spareParts,
      input,
      { signal, retry: 0 },
    );
    return toSparePart(dto);
  },
  updateSparePart: async (id, input, signal) => {
    const dto = await api.patch<SparePartDto>(
      apiEndpoints.maintenance.sparePart(id),
      input,
      { signal, retry: 0 },
    );
    return toSparePart(dto);
  },
  listWorkOrderParts: async (id, signal) => {
    const dtos = await api.get<WorkOrderPartUsageDto[]>(
      apiEndpoints.maintenance.workOrderParts(id),
      { signal },
    );
    return dtos.map(toPartUsage);
  },
  consumeSparePart: async (workOrderId, partId, quantity, note = "", signal) => {
    const dto = await api.post<WorkOrderPartUsageDto>(
      apiEndpoints.maintenance.workOrderParts(workOrderId),
      { partId, quantity, note },
      { signal, retry: 0 },
    );
    return toPartUsage(dto);
  },
  listLabourEntries: async (id, signal) => {
    const dtos = await api.get<LabourEntryDto[]>(
      apiEndpoints.maintenance.workOrderLabour(id),
      { signal },
    );
    return dtos.map(toLabourEntry);
  },
  logLabourEntry: async (workOrderId, input, signal) => {
    const dto = await api.post<LabourEntryDto>(
      apiEndpoints.maintenance.workOrderLabour(workOrderId),
      {
        technicianName: input.technicianName,
        hours: String(input.hours),
        hourlyRate: String(input.hourlyRate ?? 0),
        workedAt: input.workedAt ?? "",
        note: input.note ?? "",
      },
      { signal, retry: 0 },
    );
    return toLabourEntry(dto);
  },
  deleteLabourEntry: async (id, signal) => {
    const dto = await api.delete<LabourEntryDto>(apiEndpoints.maintenance.labourEntry(id), {
      signal,
      retry: 0,
    });
    return toLabourEntry(dto);
  },
  getWorkOrderCostSummary: async (id, signal) => {
    const dto = await api.get<WorkOrderCostSummaryDto>(
      apiEndpoints.maintenance.workOrderCostSummary(id),
      { signal },
    );
    return toCostSummary(dto);
  },
  listDevices: async (filters = {}, signal) => {
    const all: DeviceDto[] = [];
    for (let page = 1; page <= 1000; page += 1) {
      const batch = await api.get<DeviceDto[]>(apiEndpoints.maintenance.devices, {
        signal,
        query: { ...filters, page, pageSize: 100 },
      });
      all.push(...batch);
      if (batch.length < 100) break;
    }
    return all.map(toDevice);
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
    const all: WorkOrderDto[] = [];
    for (let page = 1; page <= 1000; page += 1) {
      const batch = await api.get<WorkOrderDto[]>(apiEndpoints.maintenance.workOrders, {
        signal,
        query: { ...filters, page, pageSize: 100 },
      });
      all.push(...batch);
      if (batch.length < 100) break;
    }
    return all.map(toWorkOrder);
  },
  downloadWorkOrdersExport: (format, filters = {}, signal) =>
    api.download(apiEndpoints.maintenance.workOrders, {
      query: { ...filters, export: format },
      signal,
    }),
  getMaintenanceCostReport: async (range = {}, signal) => {
    const dto = await api.get<MaintenanceCostReportDto>(
      apiEndpoints.maintenance.maintenanceCostReport,
      {
        query: { fromDate: range.fromDate ?? "", toDate: range.toDate ?? "" },
        signal,
      },
    );
    return toMaintenanceCostReport(dto);
  },
  downloadCostReportExport: (format, range = {}, signal) =>
    api.download(apiEndpoints.maintenance.maintenanceCostReport, {
      query: {
        fromDate: range.fromDate ?? "",
        toDate: range.toDate ?? "",
        export: format,
      },
      signal,
    }),
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
  getDeviceTimeline: async (deviceId, signal) => {
    const dto = await api.get<DeviceTimelineDto>(
      apiEndpoints.maintenance.deviceTimeline(deviceId),
      { signal },
    );
    return {
      device: toDevice(dto.device),
      items: (dto.items ?? []).map(toTimelineItem),
      generatedAt: "",
    };
  },
});
