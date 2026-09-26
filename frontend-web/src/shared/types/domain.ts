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
  lowStock: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WorkOrderPartUsage {
  id: string;
  workOrderId: string;
  partId: string;
  partCode: string;
  partName: string;
  unit: string;
  quantity: number;
  note: string;
  consumedAt: string;
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
  overdue?: boolean;
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
export const LOCATION_KINDS: LocationKind[] = [
  "site",
  "building",
  "floor",
  "hall",
  "line",
  "area",
  "room",
];
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
}

export interface ChatDirectoryUser {
  id: string;
  displayName: string;
  email: string;
}

export interface SendMessageInput {
  body: string;
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
