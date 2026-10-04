export type Status = "active" | "atRisk" | "completed" | "inProgress" | "onHold" | "pending" | "archived" | "queued" | "running" | "failed";
export type Priority = "low" | "normal" | "high" | "critical";

export interface Project {
  id: string;
  name: string;
  code: string;
  description: string;
  owner: string;
  status: Status;
  health: number;
  progress: number;
  dueDate: string;
  members: number;
  tasks: number;
  color: string;
}

export interface Task {
  id: string;
  title: string;
  project: string;
  status: "backlog" | "inProgress" | "review" | "done";
  priority: Priority;
  assignee: string;
  dueDate: string;
  estimate: string;
}

export interface DocumentRecord {
  id: string;
  name: string;
  type: "PDF" | "DOCX" | "XLSX" | "PNG" | "TXT";
  category: string;
  owner: string;
  modifiedAt: string;
  size: string;
  status: Status;
}

export interface Report {
  id: string;
  name: string;
  description: string;
  owner: string;
  lastRun: string;
  schedule: string;
  status: Status;
  coverage: number;
}

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  type: "task" | "project" | "security" | "system" | "insight";
  priority: Priority;
  createdAt: string;
  read: boolean;
  actionLabel?: string;
}

export interface ActivityItem {
  id: string;
  actor: string;
  action: string;
  resource: string;
  timestamp: string;
  tone: "blue" | "green" | "amber" | "purple";
}

// -- Phase 21: Maintenance / CMMS ------------------------------------------------
export type DeviceStatus = "operational" | "underMaintenance" | "outOfService" | "retired";
export type WorkOrderType = "corrective" | "preventive" | "inspection";
export type WorkOrderStatus =
  | "submitted"
  | "routed"
  | "assigned"
  | "inProgress"
  | "onHold"
  | "pendingApproval"
  | "completed"
  | "cancelled";

export type WorkOrderHistoryAction =
  | "submitted"
  | "routed"
  | "assigned"
  | "statusChanged"
  | "submittedForApproval"
  | "approved"
  | "rejected";

export interface DeviceReportSummary {
  totalOrders: number;
  openOrders: number;
  completedOrders: number;
  overdueOrders: number;
  byStatus: Record<string, number>;
  byType: Record<string, number>;
  byPriority: Record<string, number>;
  mttrHours: number | null;
}

export interface DeviceMaintenanceReport {
  device: MaintenanceDevice;
  workOrders: WorkOrder[];
  summary: DeviceReportSummary | null;
  generatedAt: string;
  fromDate: string;
  toDate: string;
}

export interface WorkOrderHistoryEntry {
  id: string;
  workOrderId: string;
  action: WorkOrderHistoryAction;
  fromStatus: string;
  toStatus: string;
  fromDepartment: string;
  toDepartment: string;
  actorName: string;
  note: string;
  createdAt: string;
}
export type DeviceTimelineSource = "device" | "workOrder";

export type DeviceTimelineAction =
  | "registered"
  | "updated"
  | "statusChanged"
  | "pmCompleted"
  | "workOrderRaised"
  | "workOrderClosed";

export interface DeviceTimelineItem {
  id: string;
  source: DeviceTimelineSource;
  action: DeviceTimelineAction;
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

export interface DeviceTimeline {
  device: MaintenanceDevice;
  items: DeviceTimelineItem[];
  generatedAt: string;
}

export type MaintenanceDepartment =
  | "general"
  | "electrical"
  | "mechanical"
  | "facilities"
  | "instrumentation"
  | "hydraulic"
  | "pneumatic"
  // Phase 26.1: a plant may add its own discipline from any department dropdown.
  | (string & {});

/** The seven maintenance disciplines a PM plan can belong to (Phase 26). */
export const MAINTENANCE_DEPARTMENTS: MaintenanceDepartment[] = [
  "mechanical",
  "electrical",
  "instrumentation",
  "general",
  "hydraulic",
  "pneumatic",
  "facilities",
];

/**
 * Everyday stocking units shown in the spare-part unit picker. The list is a
 * convenience default, not a closed enum — plants add their own units («رول»،
 * «حلقه»، ...) through the picker's «افزودن مورد جدید» entry and they are kept
 * alongside these in the local option catalogue ("part.unit").
 */
export const PART_UNITS: string[] = [
  "عدد",
  "دستگاه",
  "جفت",
  "ست",
  "متر",
  "سانتی‌متر",
  "متر مربع",
  "کیلوگرم",
  "گرم",
  "لیتر",
  "قوطی",
  "بسته",
  "باکس",
  "کارتن",
  "کیسه",
  "رول",
  "حلقه",
  "گالن",
];

export interface MaintenanceDevice {
  id: string;
  code: string;
  name: string;
  location: string;
  status: DeviceStatus;
  department: MaintenanceDepartment;
  pmIntervalDays: number;
  lastPmDate: string;
  nextDueDate: string;
  pmDue: boolean;
  createdAt: string;
  /** Registry master data; blank for devices never edited in the registry. */
  manufacturer?: string;
  modelNumber?: string;
  serialNumber?: string;
  equipmentType?: string;
  criticality?: EquipmentCriticality;
  locationId?: string;
  locationPath?: string;
  parentDeviceId?: string;
  operatorUnit?: string;
  runningHours?: number;
}

export type MaintenanceAttachmentCategory = "failurePhoto" | "manual" | "invoice" | "other";

export interface MaintenanceAttachment {
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

export interface SparePart {
  id: string;
  code: string;
  name: string;
  unit: string;
  quantityOnHand: number;
  minimumStock: number;
  unitCost: number;
  lowStock: boolean;
  createdAt: string;
  updatedAt: string;
}

export type PartTransactionType = "RECEIPT" | "ISSUE" | "RETURN" | "ADJUSTMENT";

export interface PartTransaction {
  id: string;
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  transactionType: PartTransactionType;
  typeLabel: string;
  quantity: number;
  balanceAfter: number;
  note: string;
  reference: string;
  actorId: string;
  createdAt: string;
}

export interface RecordPartTransactionInput {
  transactionType: PartTransactionType;
  quantity: number;
  note?: string;
  reference?: string;
}

export interface WorkOrderPartUsage {
  id: string;
  workOrderId: string;
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  quantity: number;
  unitCost: number;
  totalCost: number;
  note: string;
  consumedAt: string;
}

export interface LabourEntry {
  id: string;
  workOrderId: string;
  technicianName: string;
  hours: number;
  hourlyRate: number;
  totalCost: number;
  workedAt: string;
  note: string;
  createdAt: string;
}

export interface WorkOrderCostSummary {
  workOrderId: string;
  title: string;
  status: string;
  deviceId: string;
  assignedToName: string;
  labourHours: number;
  labourCost: number;
  partsCost: number;
  totalCost: number;
  labourEntries: LabourEntry[];
  partUsages: WorkOrderPartUsage[];
}

export interface WorkOrder {
  id: string;
  deviceId: string;
  title: string;
  description: string;
  orderType: WorkOrderType;
  priority: Priority;
  status: WorkOrderStatus;
  department: MaintenanceDepartment;
  requestedByName: string;
  assignedToName: string;
  resolutionNote: string;
  createdAt: string;
  closedAt: string;
  slaDueAt?: string;
  overdue?: boolean;  // -- Phase 26 closure facts (گزارشنامه‌ی خرابی) — فقط برای کارهای بسته‌شده پر می‌شود
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
  labourHours?: number;
  labourCost?: number;
  partsCost?: number;
}

// -- Phase 26: equipment registry -------------------------------------------------
/**
 * Phase 26.1 — open vocabularies.
 *
 * The union lists the codes the product ships with (and keeps editor
 * autocomplete working); `(string & {})` keeps any value the plant adds from a
 * dropdown at run time assignable. The API validates shape, not membership.
 */
export type EquipmentCriticality = "vital" | "high" | "medium" | "low" | (string & {});
export type LocationKind =
  | "site"
  | "building"
  | "floor"
  | "hall"
  | "line"
  | "system"
  | "room"
  | "area"
  | (string & {});
export type PmFrequencyUnit = "day" | "week" | "month" | "runningHour";
export type DeviceAssignmentRole =
  | "operator"
  | "responsible"
  | "technician"
  | "deputy"
  | (string & {});

export const EQUIPMENT_CRITICALITIES: EquipmentCriticality[] = [
  "vital",
  "high",
  "medium",
  "low",
];
/** Ordered site → building → floor → hall → line → system, then the
 *  subdivisions a plant slots in wherever it needs them. */
export const LOCATION_KINDS: LocationKind[] = [
  "site",
  "building",
  "floor",
  "hall",
  "line",
  "system",
  "area",
  "room",
];
export const ASSET_LEVELS: AssetLevel[] = ["mainEquipment", "subEquipment", "component"];
export const PM_FREQUENCY_UNITS: PmFrequencyUnit[] = ["day", "week", "month", "runningHour"];
export const DEVICE_ASSIGNMENT_ROLES: DeviceAssignmentRole[] = [
  "operator",
  "responsible",
  "technician",
  "deputy",
];

export interface MaintenanceLocation {
  id: string;
  code: string;
  name: string;
  kind: LocationKind;
  parentId: string;
  path: string;
  note: string;
  deviceCount: number;
}

export interface MaintenancePersonnel {
  id: string;
  personnelCode: string;
  fullName: string;
  specialty: MaintenanceDepartment;
  unit: string;
  phone: string;
  shift: string;
  skills: string[];
  certifications: string[];
  active: boolean;
}

export interface DeviceSpecification {
  id: string;
  label: string;
  value: string;
  unit: string;
  sortOrder: number;
}

export interface PmPlan {
  id: string;
  deviceId: string;
  title: string;
  discipline: MaintenanceDepartment;
  description: string;
  checklist: string[];
  frequencyEvery: number;
  frequencyUnit: PmFrequencyUnit;
  periodDays: number;
  estimatedMinutes: number;
  responsibleName: string;
  lastExecutedOn: string;
  nextDueOn: string;
  overdue: boolean;
  active: boolean;
}

/**
 * One cell of the PM calendar (برنامه‌ی زمان‌بندی PM) — either a named plan row
 * or a legacy device-level PM for devices that carry no plan. `dueOn` is empty
 * for never-executed plans (the calendar shows those in an undated strip).
 */
export interface PmScheduleItem {
  id: string;
  source: "plan" | "device";
  planId: string;
  deviceId: string;
  deviceCode: string;
  deviceName: string;
  title: string;
  discipline: MaintenanceDepartment | "";
  responsibleName: string;
  estimatedMinutes: number;
  periodDays: number;
  dueOn: string;
  overdue: boolean;
}

export interface PmExecution {
  id: string;
  planId: string;
  deviceId: string;
  discipline: MaintenanceDepartment;
  performedOn: string;
  dueOn: string;
  onTime: boolean;
  performedByName: string;
  durationMinutes: number;
  findings: string;
}

export interface DeviceBomItem {
  id: string;
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  position: string;
  standardQuantity: number;
  note: string;
  quantityOnHand: number;
  minimumStock: number;
  lowStock: boolean;
  usageCount: number;
  usedQuantity: number;
  lastUsedAt: string;
}

export interface DeviceAssignment {
  id: string;
  role: DeviceAssignmentRole;
  personnelId: string;
  personnelName: string;
  unit: string;
  fromDate: string;
  toDate: string;
  current: boolean;
}

/** تجهیز اصلی ← زیرتجهیز ← قطعه — the equipment half of the asset chain. */
export type AssetLevel = "mainEquipment" | "subEquipment" | "component";

/** One node of the asset tree: a location above, a device below. */
export interface AssetTreeNode {
  id: string;
  nodeType: "location" | "device";
  code: string;
  name: string;
  kind: string;
  assetLevel: string;
  status: string;
  criticality: string;
  path: string;
  costCenterCode: string;
  costCenterName: string;
  installedOn: string;
  retiredOn: string;
  deviceCount: number;
  children: AssetTreeNode[];
}

export interface AssetTree {
  roots: AssetTreeNode[];
  unplacedDevices: AssetTreeNode[];
  counts: { locations: number; devices: number; unplacedDevices: number };
}

/** A link in an asset's upstream chain — a parent device or a location. */
export interface AssetAncestorNode {
  id: string;
  code: string;
  name: string;
  nodeType: "location" | "device";
  kind?: string;
  assetLevel?: string;
}

export interface AssetAncestry {
  device: {
    id: string;
    code: string;
    name: string;
    assetLevel: string;
    status: string;
    locationPath: string;
    costCenterCode: string;
    costCenterName: string;
    installedOn: string;
    retiredOn: string;
  };
  deviceChain: AssetAncestorNode[];
  locationChain: AssetAncestorNode[];
  children: Array<{
    id: string;
    code: string;
    name: string;
    assetLevel: string;
    status: string;
  }>;
  descendantCount: number;
  previousLocation: {
    locationId?: string;
    locationPath?: string;
    movedOn?: string;
    reason?: string;
  };
}

/** One row of the transfer ledger. */
export interface AssetMovement {
  id: string;
  deviceId: string;
  fromLocationId: string;
  fromLocationPath: string;
  toLocationId: string;
  toLocationPath: string;
  fromParentDeviceId: string;
  toParentDeviceId: string;
  movedOn: string;
  reason: string;
  performedBy: string;
  note: string;
  createdAt: string;
}

export interface DeviceNameplate {
  manufacturer: string;
  modelNumber: string;
  serialNumber: string;
  assetType: string;
  manufactureYear: string;
  capacity: string;
  powerRating: string;
  electricalSpec: string;
  criticality: EquipmentCriticality;
  assetLevel: string;
  costCenterCode: string;
  costCenterName: string;
  parentDeviceId: string;
  locationId: string;
  locationPath: string;
  operatorUnit: string;
  supplier: string;
  purchasedOn: string;
  installedOn: string;
  commissionedOn: string;
  warrantyUntil: string;
  purchaseCost: string;
  runningHours: string;
  notes: string;
}

export interface FailureModeCount {
  label: string;
  count: number;
}

export interface PartConsumption {
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  usageCount: number;
  totalQuantity: number;
  totalCost: number;
  lastUsedAt: string;
  deviceCount: number;
}

export interface TechnicianStat {
  name: string;
  totalOrders: number;
  correctiveOrders: number;
  preventiveOrders: number;
  completedOrders: number;
  openOrders: number;
  labourHours: number;
  averageRepairHours: number | null;
}

export interface MaintenanceTrendBucket {
  label: string;
  failures: number;
  preventive: number;
  downtimeHours: number;
  cost: number;
}

export interface DeviceAnalytics {
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
  labourCost: number;
  partsCost: number;
  totalCost: number;
  labourHours: number;
  partsUsedCount: number;
  partsUsedQuantity: number;
  lastFailureAt: string;
  lastRepairAt: string;
  byFailureType: FailureModeCount[];
  byFailedComponent: FailureModeCount[];
  byRootCause: FailureModeCount[];
  byDepartment: FailureModeCount[];
  byStatus: Record<string, number>;
  byType: Record<string, number>;
  byPriority: Record<string, number>;
  partConsumption: PartConsumption[];
  technicians: TechnicianStat[];
  trend: MaintenanceTrendBucket[];
}

export interface DeviceProfile {
  device: MaintenanceDevice;
  nameplate: DeviceNameplate;
  specifications: DeviceSpecification[];
  pmPlans: PmPlan[];
  pmExecutions: PmExecution[];
  bom: DeviceBomItem[];
  assignments: DeviceAssignment[];
  location: MaintenanceLocation | null;
  locationPath: string;
  children: { id: string; code: string; name: string }[];
  analytics: DeviceAnalytics | null;
  generatedAt: string;
}

export interface FleetAnalyticsRow {
  deviceId: string;
  code: string;
  name: string;
  department: MaintenanceDepartment;
  criticality: EquipmentCriticality;
  locationPath: string;
  status: DeviceStatus;
  repairCount: number;
  preventiveCount: number;
  repeatFailures: number;
  downtimeHours: number;
  mtbfHours: number | null;
  mttrHours: number | null;
  availabilityPercent: number | null;
  pmCompliancePercent: number | null;
  partsUsedQuantity: number;
  totalCost: number;
}

export interface FleetAnalytics {
  fromDate: string;
  toDate: string;
  generatedAt: string;
  deviceCount: number;
  totalRepairs: number;
  totalPreventive: number;
  totalDowntimeHours: number;
  totalCost: number;
  fleetMtbfHours: number | null;
  fleetMttrHours: number | null;
  fleetAvailabilityPercent: number | null;
  pmCompliancePercent: number | null;
  rows: FleetAnalyticsRow[];
  topParts: PartConsumption[];
  topFailureTypes: FailureModeCount[];
  technicians: TechnicianStat[];
  trend: MaintenanceTrendBucket[];
}

export interface PartUsageReportRow {
  deviceId: string;
  deviceCode: string;
  deviceName: string;
  usageCount: number;
  totalQuantity: number;
  lastUsedAt: string;
}

export interface PartUsageReport {
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  fromDate: string;
  toDate: string;
  totalUsageCount: number;
  totalQuantity: number;
  devices: PartUsageReportRow[];
}

// -- Chat / communication (Phase 27) ------------------------------------------

/** A conversation is direct (two people), a private group, or an open channel. */
export type ConversationType = "DIRECT" | "GROUP" | "CHANNEL";
export type ParticipantRole = "OWNER" | "ADMIN" | "MODERATOR" | "MEMBER" | "GUEST";
export type ChannelVisibility = "PUBLIC" | "PRIVATE" | "RESTRICTED";

export const CONVERSATION_TYPES: ConversationType[] = ["DIRECT", "GROUP", "CHANNEL"];
export const PARTICIPANT_ROLES: ParticipantRole[] = [
  "OWNER",
  "ADMIN",
  "MODERATOR",
  "MEMBER",
  "GUEST",
];
/** Quick reactions offered under every message. */
export const QUICK_REACTIONS = ["👍", "❤️", "😊", "🎉", "👏", "🙏"];

export interface Conversation {
  id: string;
  type: ConversationType;
  name: string;
  description: string;
  topic: string;
  visibility: string;
  isActive: boolean;
  archivedAt: string;
  createdAt: string;
  lastMessageAt: string;
  lastMessagePreview: string;
  unreadCount: number;
}

export interface ConversationParticipant {
  id: string;
  conversationId: string;
  userId: string;
  displayName: string;
  role: ParticipantRole;
  joinedAt: string;
  leftAt: string;
  isMuted: boolean;
  isActive: boolean;
}

export interface MessageReaction {
  reaction: string;
  userId: string;
}

export interface ChatAttachment {
  fileName: string;
  mimeType: string;
  sizeBytes: number;
  checksum?: string;
  storageKey?: string;
  scanStatus?: string;
  classification?: "PUBLIC" | "INTERNAL" | "CONFIDENTIAL" | "RESTRICTED";
  /** نمایش‌دهنده‌ی نقطه‌ی دسترسی رسانه (URL یا documentRef بک‌اند) */
  documentRef?: string;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  senderId: string;
  senderName: string;
  messageType: string;
  body: string;
  createdAt: string;
  replyToId: string;
  editedAt: string;
  deleted: boolean;
  pending?: boolean;
  failed?: boolean;
  reactions: MessageReaction[];
  attachments?: ChatAttachment[];
}

export interface ChatDirectoryUser {
  id: string;
  displayName: string;
  email: string;
}

export interface SendMessageInput {
  body: string;
  messageType?: "TEXT" | "IMAGE" | "AUDIO" | "FILE";
  attachments?: ChatAttachment[];
  replyToId?: string;
  clientRequestId?: string;
}

export interface CreateConversationInput {
  kind: "direct" | "group" | "channel";
  peerUserId?: string;
  name?: string;
  description?: string;
  memberIds?: string[];
  code?: string;
  topic?: string;
  visibility?: ChannelVisibility;
}

// =====================================================================================
// Meter readings — ثبت قرائت دستی و سنسوری
// =====================================================================================

/** A counter accumulates (running hours, kWh); a gauge is a spot value (°C, mm/s). */
export type MeterKind = "cumulative" | "gauge";

/** Who produced the number: a person at the machine, or a gateway/PLC. */
export type MeterCaptureMode = "manual" | "sensor";

/**
 * Confidence in a single observation. Only `good` and `estimated` feed derived
 * values (running hours, PM triggers); the others are kept but not trusted.
 */
export type MeterQuality = "good" | "suspect" | "estimated" | "bad";

/** How a PM plan decides it is time: a date, a meter interval, or a threshold. */
export type PmTriggerType = "calendar" | "meter" | "condition";

export type MeterStatus = "ok" | "warning" | "due" | "unknown";

/** Definition of something measured on a device. */
export interface MeterPoint {
  id: string;
  deviceId: string;
  code: string;
  name: string;
  unit: string;
  kind: MeterKind;
  sensorKey: string;
  drivesRunningHours: boolean;
  active: boolean;
  /** Counter capacity before it wraps to zero; null when it never wraps. */
  rolloverMaximum: number | null;
  minimumValue: number | null;
  maximumValue: number | null;
  /** Plausibility guard used to flag impossible jumps between readings. */
  maximumStepPerHour: number | null;
  lastValue: number | null;
  lastReadingAt: string;
  lastCaptureMode: MeterCaptureMode | "";
  readingCount: number;
}

/** One observation. Immutable: a mistake is fixed by appending a correction. */
export interface MeterReading {
  id: string;
  deviceId: string;
  meterPointId: string;
  meterCode: string;
  meterName: string;
  unit: string;
  value: number;
  /** Consumption since the previous trusted reading; null when unknown. */
  delta: number | null;
  capturedAt: string;
  captureMode: MeterCaptureMode;
  quality: MeterQuality;
  rolloverApplied: boolean;
  note: string;
  sensorKey: string;
  recordedByName: string;
  provenance: string;
  correctsReadingId: string;
  supersededByReadingId: string;
  createdAt: string;
}

export interface MeterPointSummary {
  meterPointId: string;
  code: string;
  name: string;
  unit: string;
  kind: MeterKind;
  readingCount: number;
  manualCount: number;
  sensorCount: number;
  suspectCount: number;
  firstValue: number | null;
  lastValue: number | null;
  minimumValue: number | null;
  maximumValue: number | null;
  averageValue: number | null;
  /** Total accumulated amount over the window; null for a gauge. */
  totalConsumption: number | null;
  firstCapturedAt: string;
  lastCapturedAt: string;
}

/** A meter- or condition-driven PM plan with its live distance to the trigger. */
export interface MeterPmStatusRow {
  planId: string;
  deviceId: string;
  deviceCode: string;
  deviceName: string;
  title: string;
  discipline: string;
  triggerType: PmTriggerType;
  metricType: string;
  metricUnit: string;
  /** Meter units between two services (meter trigger only). */
  interval: number | null;
  thresholdOperator: string;
  thresholdValue: number | null;
  currentValue: number | null;
  dueAtValue: number | null;
  remaining: number | null;
  lastReadingAt: string;
  status: MeterStatus;
  /** Why the status is `unknown`: "noReadings", "noBaseline", … */
  reason: string;
}

export interface SaveMeterPointInput {
  code: string;
  name: string;
  unit?: string;
  kind?: MeterKind;
  sensorKey?: string;
  drivesRunningHours?: boolean;
  active?: boolean;
  rolloverMaximum?: string;
  minimumValue?: string;
  maximumValue?: string;
  maximumStepPerHour?: string;
  note?: string;
}

export interface RecordMeterReadingInput {
  /** Address the meter either by its code on the device or by its id. */
  meterCode?: string;
  meterPointId?: string;
  /** Sent as a string so a large hour meter never loses precision. */
  value: string;
  capturedAt?: string;
  quality?: MeterQuality;
  note?: string;
}

/** Outcome of one sample inside a gateway batch; partial success is normal. */
export interface MeterIngestResult {
  index: number;
  status: "accepted" | "duplicate" | "rejected";
  readingId: string;
  meterPointId: string;
  sensorKey: string;
  quality: MeterQuality | "";
  delta: number | null;
  errorCode: string;
  message: string;
}

export interface MeterIngestBatch {
  accepted: number;
  duplicates: number;
  rejected: number;
  received: number;
  results: MeterIngestResult[];
}
