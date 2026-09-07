export type Status = "active" | "atRisk" | "completed" | "inProgress" | "pending" | "archived" | "queued" | "running" | "failed";
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
