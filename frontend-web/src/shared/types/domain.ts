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
  | "instrumentation";

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
