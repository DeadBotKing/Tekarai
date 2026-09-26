import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  DeviceAnalytics,
  DeviceAssignment,
  DeviceAssignmentRole,
  DeviceBomItem,
  DeviceNameplate,
  DeviceProfile,
  DeviceSpecification,
  DeviceStatus,
  EquipmentCriticality,
  FailureModeCount,
  FleetAnalytics,
  FleetAnalyticsRow,
  LocationKind,
  MaintenanceDepartment,
  MaintenanceDevice,
  MaintenanceLocation,
  MaintenancePersonnel,
  MaintenanceTrendBucket,
  PartConsumption,
  PartUsageReport,
  PmExecution,
  PmFrequencyUnit,
  PmPlan,
  TechnicianStat,
} from "../../shared/types/domain";

/**
 * Phase 26 registry client.
 *
 * The backend serialises money/quantity columns as decimal *strings* so no
 * precision is lost on the wire; every mapper below converts them to numbers
 * exactly once, at this boundary, so pages never parse strings themselves.
 */

const num = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

const optionalNum = (value: unknown): number | null =>
  value === null || value === undefined || value === "" ? null : num(value);

const text = (value: unknown): string => (value === null || value === undefined ? "" : String(value));

interface LocationDto {
  id: string;
  code: string;
  name: string;
  kind: string;
  parentId: string;
  path: string;
  note: string;
  deviceCount: number;
}

interface PersonnelDto {
  id: string;
  personnelCode: string;
  fullName: string;
  specialty: string;
  unit: string;
  phone: string;
  shift: string;
  skills: string[];
  certifications: string[];
  active: boolean;
}

interface SpecificationDto {
  id: string;
  label: string;
  value: string;
  unit: string;
  sortOrder: number;
}

interface PmPlanDto {
  id: string;
  deviceId: string;
  title: string;
  discipline: string;
  description: string;
  checklist: string[];
  frequencyEvery: number;
  frequencyUnit: string;
  periodDays: number;
  estimatedMinutes: number;
  responsibleName: string;
  lastExecutedOn: string;
  nextDueOn: string;
  overdue: boolean;
  active: boolean;
}

interface PmExecutionDto {
  id: string;
  planId: string;
  deviceId: string;
  discipline: string;
  performedOn: string;
  dueOn: string;
  onTime: boolean;
  performedByName: string;
  durationMinutes: number;
  findings: string;
}

interface BomItemDto {
  id: string;
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  position: string;
  standardQuantity: string;
  note: string;
  quantityOnHand: string;
  minimumStock: string;
  lowStock: boolean;
  usageCount: number;
  usedQuantity: string;
  lastUsedAt: string;
}

interface AssignmentDto {
  id: string;
  role: string;
  personnelId: string;
  personnelName: string;
  unit: string;
  fromDate: string;
  toDate: string;
  current: boolean;
}

interface RegistryDeviceDto {
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
  manufacturer?: string;
  modelNumber?: string;
  serialNumber?: string;
  equipmentType?: string;
  criticality?: string;
  locationId?: string;
  locationPath?: string;
  parentDeviceId?: string;
  operatorUnit?: string;
  runningHours?: number;
}

interface FailureModeDto {
  label: string;
  count: number;
}

interface PartConsumptionDto {
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  usageCount: number;
  totalQuantity: string;
  totalCost: string;
  lastUsedAt: string;
  deviceCount: number;
}

interface TechnicianStatDto {
  name: string;
  totalOrders: number;
  correctiveOrders: number;
  preventiveOrders: number;
  completedOrders: number;
  openOrders: number;
  labourHours: number;
  averageRepairHours: number | null;
}

interface TrendBucketDto {
  label: string;
  failures: number;
  preventive: number;
  downtimeHours: number;
  cost: string;
}

interface DeviceAnalyticsDto {
  deviceId: string;
  fromDate: string;
  toDate: string;
  windowDays: number;
  totalOrders: number;
  repairCount: number;
  preventiveCount: number;
  inspectionCount: number;
  openOrders: number;
  completedOrders: number;
  repeatFailures: number;
  totalDowntimeHours: number;
  operatingHours: number;
  mtbfHours: number | null;
  mttrHours: number | null;
  availabilityPercent: number | null;
  pmScheduled: number;
  pmCompleted: number;
  pmOnTime: number;
  pmOverdue: number;
  pmCompliancePercent: number | null;
  labourCost: string;
  partsCost: string;
  totalCost: string;
  labourHours: number;
  partsUsedCount: number;
  partsUsedQuantity: string;
  lastFailureAt: string;
  lastRepairAt: string;
  byFailureType: FailureModeDto[];
  byFailedComponent: FailureModeDto[];
  byRootCause: FailureModeDto[];
  byDepartment: FailureModeDto[];
  byStatus: Record<string, number>;
  byType: Record<string, number>;
  byPriority: Record<string, number>;
  partConsumption: PartConsumptionDto[];
  technicians: TechnicianStatDto[];
  trend: TrendBucketDto[];
}

interface DeviceProfileDto {
  device: RegistryDeviceDto;
  nameplate: Record<string, string>;
  specifications: SpecificationDto[];
  pmPlans: PmPlanDto[];
  pmExecutions: PmExecutionDto[];
  bom: BomItemDto[];
  assignments: AssignmentDto[];
  location: LocationDto | null;
  locationPath: string;
  children: { id: string; code: string; name: string }[];
  analytics: DeviceAnalyticsDto | null;
  generatedAt: string;
}

interface FleetRowDto {
  deviceId: string;
  code: string;
  name: string;
  department: string;
  criticality: string;
  locationPath: string;
  status: string;
  repairCount: number;
  preventiveCount: number;
  repeatFailures: number;
  downtimeHours: number;
  mtbfHours: number | null;
  mttrHours: number | null;
  availabilityPercent: number | null;
  pmCompliancePercent: number | null;
  partsUsedQuantity: string;
  totalCost: string;
}

interface FleetAnalyticsDto {
  fromDate: string;
  toDate: string;
  generatedAt: string;
  deviceCount: number;
  totalRepairs: number;
  totalPreventive: number;
  totalDowntimeHours: number;
  totalCost: string;
  fleetMtbfHours: number | null;
  fleetMttrHours: number | null;
  fleetAvailabilityPercent: number | null;
  pmCompliancePercent: number | null;
  rows: FleetRowDto[];
  topParts: PartConsumptionDto[];
  topFailureTypes: FailureModeDto[];
  technicians: TechnicianStatDto[];
  trend: TrendBucketDto[];
}

interface PartUsageReportDto {
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  fromDate: string;
  toDate: string;
  totalUsageCount: number;
  totalQuantity: string;
  devices: {
    deviceId: string;
    deviceCode: string;
    deviceName: string;
    usageCount: number;
    totalQuantity: string;
    lastUsedAt: string;
  }[];
}

export const toLocation = (dto: LocationDto): MaintenanceLocation => ({
  id: dto.id,
  code: text(dto.code),
  name: text(dto.name),
  kind: (text(dto.kind) || "site") as LocationKind,
  parentId: text(dto.parentId),
  path: text(dto.path),
  note: text(dto.note),
  deviceCount: num(dto.deviceCount),
});

export const toPersonnel = (dto: PersonnelDto): MaintenancePersonnel => ({
  id: dto.id,
  personnelCode: text(dto.personnelCode),
  fullName: text(dto.fullName),
  specialty: (text(dto.specialty) || "general") as MaintenanceDepartment,
  unit: text(dto.unit),
  phone: text(dto.phone),
  shift: text(dto.shift),
  skills: dto.skills ?? [],
  certifications: dto.certifications ?? [],
  active: Boolean(dto.active),
});

export const toSpecification = (dto: SpecificationDto): DeviceSpecification => ({
  id: dto.id,
  label: text(dto.label),
  value: text(dto.value),
  unit: text(dto.unit),
  sortOrder: num(dto.sortOrder),
});

export const toPmPlan = (dto: PmPlanDto): PmPlan => ({
  id: dto.id,
  deviceId: dto.deviceId,
  title: text(dto.title),
  discipline: (text(dto.discipline) || "general") as MaintenanceDepartment,
  description: text(dto.description),
  checklist: dto.checklist ?? [],
  frequencyEvery: num(dto.frequencyEvery),
  frequencyUnit: (text(dto.frequencyUnit) || "month") as PmFrequencyUnit,
  periodDays: num(dto.periodDays),
  estimatedMinutes: num(dto.estimatedMinutes),
  responsibleName: text(dto.responsibleName),
  lastExecutedOn: text(dto.lastExecutedOn),
  nextDueOn: text(dto.nextDueOn),
  overdue: Boolean(dto.overdue),
  active: Boolean(dto.active),
});

export const toPmExecution = (dto: PmExecutionDto): PmExecution => ({
  id: dto.id,
  planId: dto.planId,
  deviceId: dto.deviceId,
  discipline: (text(dto.discipline) || "general") as MaintenanceDepartment,
  performedOn: text(dto.performedOn),
  dueOn: text(dto.dueOn),
  onTime: Boolean(dto.onTime),
  performedByName: text(dto.performedByName),
  durationMinutes: num(dto.durationMinutes),
  findings: text(dto.findings),
});

export const toBomItem = (dto: BomItemDto): DeviceBomItem => ({
  id: dto.id,
  partId: dto.partId,
  partCode: text(dto.partCode),
  partName: text(dto.partName),
  unit: text(dto.unit),
  position: text(dto.position),
  standardQuantity: num(dto.standardQuantity),
  note: text(dto.note),
  quantityOnHand: num(dto.quantityOnHand),
  minimumStock: num(dto.minimumStock),
  lowStock: Boolean(dto.lowStock),
  usageCount: num(dto.usageCount),
  usedQuantity: num(dto.usedQuantity),
  lastUsedAt: text(dto.lastUsedAt),
});

export const toAssignment = (dto: AssignmentDto): DeviceAssignment => ({
  id: dto.id,
  role: (text(dto.role) || "technician") as DeviceAssignmentRole,
  personnelId: text(dto.personnelId),
  personnelName: text(dto.personnelName),
  unit: text(dto.unit),
  fromDate: text(dto.fromDate),
  toDate: text(dto.toDate),
  current: Boolean(dto.current),
});

export const toNameplate = (raw: Record<string, unknown> | null | undefined): DeviceNameplate => ({
  manufacturer: text(raw?.manufacturer),
  modelNumber: text(raw?.modelNumber),
  serialNumber: text(raw?.serialNumber),
  assetType: text(raw?.assetType),
  manufactureYear: text(raw?.manufactureYear),
  capacity: text(raw?.capacity),
  powerRating: text(raw?.powerRating),
  electricalSpec: text(raw?.electricalSpec),
  criticality: (text(raw?.criticality) || "medium") as EquipmentCriticality,
  parentDeviceId: text(raw?.parentDeviceId),
  locationId: text(raw?.locationId),
  locationPath: text(raw?.locationPath),
  operatorUnit: text(raw?.operatorUnit),
  supplier: text(raw?.supplier),
  purchasedOn: text(raw?.purchasedOn),
  installedOn: text(raw?.installedOn),
  commissionedOn: text(raw?.commissionedOn),
  warrantyUntil: text(raw?.warrantyUntil),
  purchaseCost: text(raw?.purchaseCost) || "0",
  runningHours: text(raw?.runningHours) || "0",
  notes: text(raw?.notes),
});

export const toRegistryDevice = (dto: RegistryDeviceDto): MaintenanceDevice => ({
  id: dto.id,
  code: text(dto.code),
  name: text(dto.name),
  location: text(dto.location),
  status: (text(dto.status) || "operational") as DeviceStatus,
  department: (text(dto.department) || "general") as MaintenanceDepartment,
  pmIntervalDays: num(dto.pmIntervalDays),
  lastPmDate: text(dto.lastPmDate),
  nextDueDate: text(dto.nextDueDate),
  pmDue: Boolean(dto.pmDue),
  createdAt: text(dto.createdAt),
  manufacturer: text(dto.manufacturer),
  modelNumber: text(dto.modelNumber),
  serialNumber: text(dto.serialNumber),
  equipmentType: text(dto.equipmentType),
  criticality: (text(dto.criticality) || "medium") as EquipmentCriticality,
  locationId: text(dto.locationId),
  locationPath: text(dto.locationPath),
  parentDeviceId: text(dto.parentDeviceId),
  operatorUnit: text(dto.operatorUnit),
  runningHours: num(dto.runningHours),
});

const toFailureMode = (dto: FailureModeDto): FailureModeCount => ({
  label: text(dto.label),
  count: num(dto.count),
});

const toPartConsumption = (dto: PartConsumptionDto): PartConsumption => ({
  partId: dto.partId,
  partCode: text(dto.partCode),
  partName: text(dto.partName),
  unit: text(dto.unit),
  usageCount: num(dto.usageCount),
  totalQuantity: num(dto.totalQuantity),
  totalCost: num(dto.totalCost),
  lastUsedAt: text(dto.lastUsedAt),
  deviceCount: num(dto.deviceCount),
});

const toTechnician = (dto: TechnicianStatDto): TechnicianStat => ({
  name: text(dto.name),
  totalOrders: num(dto.totalOrders),
  correctiveOrders: num(dto.correctiveOrders),
  preventiveOrders: num(dto.preventiveOrders),
  completedOrders: num(dto.completedOrders),
  openOrders: num(dto.openOrders),
  labourHours: num(dto.labourHours),
  averageRepairHours: optionalNum(dto.averageRepairHours),
});

const toTrendBucket = (dto: TrendBucketDto): MaintenanceTrendBucket => ({
  label: text(dto.label),
  failures: num(dto.failures),
  preventive: num(dto.preventive),
  downtimeHours: num(dto.downtimeHours),
  cost: num(dto.cost),
});

export const toDeviceAnalytics = (dto: DeviceAnalyticsDto): DeviceAnalytics => ({
  deviceId: text(dto.deviceId),
  fromDate: text(dto.fromDate),
  toDate: text(dto.toDate),
  windowDays: num(dto.windowDays),
  totalOrders: num(dto.totalOrders),
  repairCount: num(dto.repairCount),
  preventiveCount: num(dto.preventiveCount),
  inspectionCount: num(dto.inspectionCount),
  openOrders: num(dto.openOrders),
  completedOrders: num(dto.completedOrders),
  repeatFailures: num(dto.repeatFailures),
  totalDowntimeHours: num(dto.totalDowntimeHours),
  operatingHours: num(dto.operatingHours),
  mtbfHours: optionalNum(dto.mtbfHours),
  mttrHours: optionalNum(dto.mttrHours),
  availabilityPercent: optionalNum(dto.availabilityPercent),
  pmScheduled: num(dto.pmScheduled),
  pmCompleted: num(dto.pmCompleted),
  pmOnTime: num(dto.pmOnTime),
  pmOverdue: num(dto.pmOverdue),
  pmCompliancePercent: optionalNum(dto.pmCompliancePercent),
  labourCost: num(dto.labourCost),
  partsCost: num(dto.partsCost),
  totalCost: num(dto.totalCost),
  labourHours: num(dto.labourHours),
  partsUsedCount: num(dto.partsUsedCount),
  partsUsedQuantity: num(dto.partsUsedQuantity),
  lastFailureAt: text(dto.lastFailureAt),
  lastRepairAt: text(dto.lastRepairAt),
  byFailureType: (dto.byFailureType ?? []).map(toFailureMode),
  byFailedComponent: (dto.byFailedComponent ?? []).map(toFailureMode),
  byRootCause: (dto.byRootCause ?? []).map(toFailureMode),
  byDepartment: (dto.byDepartment ?? []).map(toFailureMode),
  byStatus: dto.byStatus ?? {},
  byType: dto.byType ?? {},
  byPriority: dto.byPriority ?? {},
  partConsumption: (dto.partConsumption ?? []).map(toPartConsumption),
  technicians: (dto.technicians ?? []).map(toTechnician),
  trend: (dto.trend ?? []).map(toTrendBucket),
});

export const toDeviceProfile = (dto: DeviceProfileDto): DeviceProfile => ({
  device: toRegistryDevice(dto.device),
  nameplate: toNameplate(dto.nameplate),
  specifications: (dto.specifications ?? []).map(toSpecification),
  pmPlans: (dto.pmPlans ?? []).map(toPmPlan),
  pmExecutions: (dto.pmExecutions ?? []).map(toPmExecution),
  bom: (dto.bom ?? []).map(toBomItem),
  assignments: (dto.assignments ?? []).map(toAssignment),
  location: dto.location ? toLocation(dto.location) : null,
  locationPath: text(dto.locationPath),
  children: dto.children ?? [],
  analytics: dto.analytics ? toDeviceAnalytics(dto.analytics) : null,
  generatedAt: text(dto.generatedAt),
});

const toFleetRow = (dto: FleetRowDto): FleetAnalyticsRow => ({
  deviceId: dto.deviceId,
  code: text(dto.code),
  name: text(dto.name),
  department: (text(dto.department) || "general") as MaintenanceDepartment,
  criticality: (text(dto.criticality) || "medium") as EquipmentCriticality,
  locationPath: text(dto.locationPath),
  status: (text(dto.status) || "operational") as DeviceStatus,
  repairCount: num(dto.repairCount),
  preventiveCount: num(dto.preventiveCount),
  repeatFailures: num(dto.repeatFailures),
  downtimeHours: num(dto.downtimeHours),
  mtbfHours: optionalNum(dto.mtbfHours),
  mttrHours: optionalNum(dto.mttrHours),
  availabilityPercent: optionalNum(dto.availabilityPercent),
  pmCompliancePercent: optionalNum(dto.pmCompliancePercent),
  partsUsedQuantity: num(dto.partsUsedQuantity),
  totalCost: num(dto.totalCost),
});

export const toFleetAnalytics = (dto: FleetAnalyticsDto): FleetAnalytics => ({
  fromDate: text(dto.fromDate),
  toDate: text(dto.toDate),
  generatedAt: text(dto.generatedAt),
  deviceCount: num(dto.deviceCount),
  totalRepairs: num(dto.totalRepairs),
  totalPreventive: num(dto.totalPreventive),
  totalDowntimeHours: num(dto.totalDowntimeHours),
  totalCost: num(dto.totalCost),
  fleetMtbfHours: optionalNum(dto.fleetMtbfHours),
  fleetMttrHours: optionalNum(dto.fleetMttrHours),
  fleetAvailabilityPercent: optionalNum(dto.fleetAvailabilityPercent),
  pmCompliancePercent: optionalNum(dto.pmCompliancePercent),
  rows: (dto.rows ?? []).map(toFleetRow),
  topParts: (dto.topParts ?? []).map(toPartConsumption),
  topFailureTypes: (dto.topFailureTypes ?? []).map(toFailureMode),
  technicians: (dto.technicians ?? []).map(toTechnician),
  trend: (dto.trend ?? []).map(toTrendBucket),
});

export const toPartUsageReport = (dto: PartUsageReportDto): PartUsageReport => ({
  partId: text(dto.partId),
  partCode: text(dto.partCode),
  partName: text(dto.partName),
  unit: text(dto.unit),
  fromDate: text(dto.fromDate),
  toDate: text(dto.toDate),
  totalUsageCount: num(dto.totalUsageCount),
  totalQuantity: num(dto.totalQuantity),
  devices: (dto.devices ?? []).map((row) => ({
    deviceId: row.deviceId,
    deviceCode: text(row.deviceCode),
    deviceName: text(row.deviceName),
    usageCount: num(row.usageCount),
    totalQuantity: num(row.totalQuantity),
    lastUsedAt: text(row.lastUsedAt),
  })),
});

export interface SaveLocationInput {
  code?: string;
  name: string;
  kind: LocationKind;
  parentId?: string;
  note?: string;
}

export interface SavePersonnelInput {
  personnelCode?: string;
  fullName: string;
  specialty: MaintenanceDepartment;
  unit?: string;
  phone?: string;
  shift?: string;
  skills?: string[];
  certifications?: string[];
  active?: boolean;
}

export interface SavePmPlanInput {
  title: string;
  discipline: MaintenanceDepartment;
  description?: string;
  checklist?: string[];
  frequencyEvery: number;
  frequencyUnit: PmFrequencyUnit;
  estimatedMinutes?: number;
  responsibleName?: string;
  active?: boolean;
}

export interface RecordPmExecutionInput {
  performedOn?: string;
  performedByName?: string;
  durationMinutes?: number;
  findings?: string;
}

export interface SaveBomItemInput {
  partId: string;
  position?: string;
  standardQuantity?: string;
  note?: string;
}

export interface AssignmentRowInput {
  personnelId?: string;
  personnelName?: string;
  role: DeviceAssignmentRole;
  unit?: string;
  fromDate?: string;
  toDate?: string;
}

export interface SpecificationRowInput {
  label: string;
  value?: string;
  unit?: string;
  sortOrder?: number;
}

export interface AnalyticsRange {
  fromDate?: string;
  toDate?: string;
}

export interface FleetFilters extends AnalyticsRange {
  department?: string;
  criticality?: string;
  locationId?: string;
}

export interface WorkOrderClosureInput {
  failureType?: string;
  failedComponent?: string;
  failureSymptom?: string;
  rootCause?: string;
  actionTaken?: string;
  repeatFailure?: boolean;
  failureReportedAt?: string;
  repairStartedAt?: string;
  repairFinishedAt?: string;
  returnedToServiceAt?: string;
  downtimeMinutes?: number;
  labourHours?: string;
  labourCost?: string;
  partsCost?: string;
}

export interface RegistryService {
  listLocations: (search?: string, signal?: AbortSignal) => Promise<MaintenanceLocation[]>;
  createLocation: (input: SaveLocationInput, signal?: AbortSignal) => Promise<MaintenanceLocation>;
  updateLocation: (
    id: string,
    input: SaveLocationInput,
    signal?: AbortSignal,
  ) => Promise<MaintenanceLocation>;
  deleteLocation: (id: string, signal?: AbortSignal) => Promise<void>;
  listPersonnel: (
    filters?: { search?: string; specialty?: string },
    signal?: AbortSignal,
  ) => Promise<MaintenancePersonnel[]>;
  createPersonnel: (
    input: SavePersonnelInput,
    signal?: AbortSignal,
  ) => Promise<MaintenancePersonnel>;
  updatePersonnel: (
    id: string,
    input: SavePersonnelInput,
    signal?: AbortSignal,
  ) => Promise<MaintenancePersonnel>;
  deletePersonnel: (id: string, signal?: AbortSignal) => Promise<void>;
  getDeviceProfile: (
    deviceId: string,
    range?: AnalyticsRange,
    signal?: AbortSignal,
  ) => Promise<DeviceProfile>;
  updateNameplate: (
    deviceId: string,
    values: Partial<DeviceNameplate>,
    signal?: AbortSignal,
  ) => Promise<DeviceNameplate>;
  saveSpecifications: (
    deviceId: string,
    rows: SpecificationRowInput[],
    signal?: AbortSignal,
  ) => Promise<DeviceSpecification[]>;
  listPmPlans: (deviceId: string, signal?: AbortSignal) => Promise<PmPlan[]>;
  createPmPlan: (
    deviceId: string,
    input: SavePmPlanInput,
    signal?: AbortSignal,
  ) => Promise<PmPlan>;
  updatePmPlan: (planId: string, input: SavePmPlanInput, signal?: AbortSignal) => Promise<PmPlan>;
  deletePmPlan: (planId: string, signal?: AbortSignal) => Promise<void>;
  recordPmExecution: (
    planId: string,
    input: RecordPmExecutionInput,
    signal?: AbortSignal,
  ) => Promise<PmExecution>;
  addBomItem: (
    deviceId: string,
    input: SaveBomItemInput,
    signal?: AbortSignal,
  ) => Promise<DeviceBomItem>;
  removeBomItem: (deviceId: string, partId: string, signal?: AbortSignal) => Promise<void>;
  saveAssignments: (
    deviceId: string,
    rows: AssignmentRowInput[],
    signal?: AbortSignal,
  ) => Promise<DeviceAssignment[]>;
  getDeviceAnalytics: (
    deviceId: string,
    range?: AnalyticsRange,
    signal?: AbortSignal,
  ) => Promise<DeviceAnalytics>;
  getFleetAnalytics: (filters?: FleetFilters, signal?: AbortSignal) => Promise<FleetAnalytics>;
  getPartUsageReport: (
    partId: string,
    range?: AnalyticsRange,
    signal?: AbortSignal,
  ) => Promise<PartUsageReport>;
  recordClosureDetails: (
    workOrderId: string,
    input: WorkOrderClosureInput,
    signal?: AbortSignal,
  ) => Promise<Record<string, unknown>>;
}

export const createRegistryService = (api: ApiClient): RegistryService => ({
  listLocations: async (search = "", signal) => {
    const dtos = await api.get<LocationDto[]>(apiEndpoints.maintenance.locations, {
      query: { search },
      signal,
    });
    return dtos.map(toLocation);
  },
  createLocation: async (input, signal) => {
    const dto = await api.post<LocationDto>(
      apiEndpoints.maintenance.locations,
      {
        code: input.code ?? "",
        name: input.name,
        kind: input.kind,
        parentId: input.parentId ?? "",
        note: input.note ?? "",
      },
      { signal, retry: 0 },
    );
    return toLocation(dto);
  },
  updateLocation: async (id, input, signal) => {
    const dto = await api.patch<LocationDto>(
      apiEndpoints.maintenance.location(id),
      {
        code: input.code ?? "",
        name: input.name,
        kind: input.kind,
        parentId: input.parentId ?? "",
        note: input.note ?? "",
      },
      { signal, retry: 0 },
    );
    return toLocation(dto);
  },
  deleteLocation: async (id, signal) => {
    await api.delete<unknown>(apiEndpoints.maintenance.location(id), { signal, retry: 0 });
  },
  listPersonnel: async (filters = {}, signal) => {
    const dtos = await api.get<PersonnelDto[]>(apiEndpoints.maintenance.personnel, {
      query: { search: filters.search ?? "", specialty: filters.specialty ?? "" },
      signal,
    });
    return dtos.map(toPersonnel);
  },
  createPersonnel: async (input, signal) => {
    const dto = await api.post<PersonnelDto>(
      apiEndpoints.maintenance.personnel,
      {
        personnelCode: input.personnelCode ?? "",
        fullName: input.fullName,
        specialty: input.specialty,
        unit: input.unit ?? "",
        phone: input.phone ?? "",
        shift: input.shift ?? "",
        skills: input.skills ?? [],
        certifications: input.certifications ?? [],
        active: input.active ?? true,
      },
      { signal, retry: 0 },
    );
    return toPersonnel(dto);
  },
  updatePersonnel: async (id, input, signal) => {
    const dto = await api.patch<PersonnelDto>(
      apiEndpoints.maintenance.personnelMember(id),
      {
        personnelCode: input.personnelCode ?? "",
        fullName: input.fullName,
        specialty: input.specialty,
        unit: input.unit ?? "",
        phone: input.phone ?? "",
        shift: input.shift ?? "",
        skills: input.skills ?? [],
        certifications: input.certifications ?? [],
        active: input.active ?? true,
      },
      { signal, retry: 0 },
    );
    return toPersonnel(dto);
  },
  deletePersonnel: async (id, signal) => {
    await api.delete<unknown>(apiEndpoints.maintenance.personnelMember(id), {
      signal,
      retry: 0,
    });
  },
  getDeviceProfile: async (deviceId, range = {}, signal) => {
    const dto = await api.get<DeviceProfileDto>(
      apiEndpoints.maintenance.deviceProfile(deviceId),
      { query: { fromDate: range.fromDate ?? "", toDate: range.toDate ?? "" }, signal },
    );
    return toDeviceProfile(dto);
  },
  updateNameplate: async (deviceId, values, signal) => {
    const raw = await api.patch<Record<string, string>>(
      apiEndpoints.maintenance.deviceNameplate(deviceId),
      values,
      { signal, retry: 0 },
    );
    return toNameplate(raw);
  },
  saveSpecifications: async (deviceId, rows, signal) => {
    const dtos = await api.put<SpecificationDto[]>(
      apiEndpoints.maintenance.deviceSpecifications(deviceId),
      {
        rows: rows.map((row, index) => ({
          label: row.label,
          value: row.value ?? "",
          unit: row.unit ?? "",
          sortOrder: row.sortOrder ?? index,
        })),
      },
      { signal, retry: 0 },
    );
    return dtos.map(toSpecification);
  },
  listPmPlans: async (deviceId, signal) => {
    const dtos = await api.get<PmPlanDto[]>(apiEndpoints.maintenance.devicePmPlans(deviceId), {
      signal,
    });
    return dtos.map(toPmPlan);
  },
  createPmPlan: async (deviceId, input, signal) => {
    const dto = await api.post<PmPlanDto>(
      apiEndpoints.maintenance.devicePmPlans(deviceId),
      {
        title: input.title,
        discipline: input.discipline,
        description: input.description ?? "",
        checklist: input.checklist ?? [],
        frequencyEvery: input.frequencyEvery,
        frequencyUnit: input.frequencyUnit,
        estimatedMinutes: input.estimatedMinutes ?? 0,
        responsibleName: input.responsibleName ?? "",
        active: input.active ?? true,
      },
      { signal, retry: 0 },
    );
    return toPmPlan(dto);
  },
  updatePmPlan: async (planId, input, signal) => {
    const dto = await api.patch<PmPlanDto>(
      apiEndpoints.maintenance.pmPlan(planId),
      {
        title: input.title,
        discipline: input.discipline,
        description: input.description ?? "",
        checklist: input.checklist ?? [],
        frequencyEvery: input.frequencyEvery,
        frequencyUnit: input.frequencyUnit,
        estimatedMinutes: input.estimatedMinutes ?? 0,
        responsibleName: input.responsibleName ?? "",
        active: input.active ?? true,
      },
      { signal, retry: 0 },
    );
    return toPmPlan(dto);
  },
  deletePmPlan: async (planId, signal) => {
    await api.delete<unknown>(apiEndpoints.maintenance.pmPlan(planId), { signal, retry: 0 });
  },
  recordPmExecution: async (planId, input, signal) => {
    const dto = await api.post<PmExecutionDto>(
      apiEndpoints.maintenance.pmPlanExecutions(planId),
      {
        performedOn: input.performedOn ?? "",
        performedByName: input.performedByName ?? "",
        durationMinutes: input.durationMinutes ?? 0,
        findings: input.findings ?? "",
      },
      { signal, retry: 0 },
    );
    return toPmExecution(dto);
  },
  addBomItem: async (deviceId, input, signal) => {
    const dto = await api.post<BomItemDto>(
      apiEndpoints.maintenance.deviceBom(deviceId),
      {
        partId: input.partId,
        position: input.position ?? "",
        standardQuantity: input.standardQuantity ?? "1",
        note: input.note ?? "",
      },
      { signal, retry: 0 },
    );
    return toBomItem(dto);
  },
  removeBomItem: async (deviceId, partId, signal) => {
    await api.delete<unknown>(apiEndpoints.maintenance.deviceBomItem(deviceId, partId), {
      signal,
      retry: 0,
    });
  },
  saveAssignments: async (deviceId, rows, signal) => {
    const dtos = await api.put<AssignmentDto[]>(
      apiEndpoints.maintenance.deviceAssignments(deviceId),
      {
        rows: rows.map((row) => ({
          personnelId: row.personnelId ?? "",
          personnelName: row.personnelName ?? "",
          role: row.role,
          unit: row.unit ?? "",
          fromDate: row.fromDate ?? "",
          toDate: row.toDate ?? "",
        })),
      },
      { signal, retry: 0 },
    );
    return dtos.map(toAssignment);
  },
  getDeviceAnalytics: async (deviceId, range = {}, signal) => {
    const dto = await api.get<DeviceAnalyticsDto>(
      apiEndpoints.maintenance.deviceAnalytics(deviceId),
      { query: { fromDate: range.fromDate ?? "", toDate: range.toDate ?? "" }, signal },
    );
    return toDeviceAnalytics(dto);
  },
  getFleetAnalytics: async (filters = {}, signal) => {
    const dto = await api.get<FleetAnalyticsDto>(apiEndpoints.maintenance.fleetAnalytics, {
      query: {
        fromDate: filters.fromDate ?? "",
        toDate: filters.toDate ?? "",
        department: filters.department ?? "",
        criticality: filters.criticality ?? "",
        locationId: filters.locationId ?? "",
      },
      signal,
    });
    return toFleetAnalytics(dto);
  },
  getPartUsageReport: async (partId, range = {}, signal) => {
    const dto = await api.get<PartUsageReportDto>(
      apiEndpoints.maintenance.partUsageReport(partId),
      { query: { fromDate: range.fromDate ?? "", toDate: range.toDate ?? "" }, signal },
    );
    return toPartUsageReport(dto);
  },
  recordClosureDetails: (workOrderId, input, signal) =>
    api.patch<Record<string, unknown>>(
      apiEndpoints.maintenance.workOrderClosure(workOrderId),
      input,
      { signal, retry: 0 },
    ),
});
