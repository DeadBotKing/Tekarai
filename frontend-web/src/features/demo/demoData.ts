import type { TokenPair } from "../../core/api/apiTypes";
import type { UserSession } from "../../core/auth/sessionStore";
import type { ActivityItem, AppNotification, DocumentRecord, Project, Report, Task } from "../../shared/types/domain";
import type { IntelligenceData } from "../../shared/types/intelligence";

export interface LoginCredentials {
  tenantCode: string;
  identifier: string;
  password: string;
}

const token = (label: string): string => {
  const entropy = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `demo.${label}.${entropy}`;
};

export const demoLogin = async (_credentials: LoginCredentials): Promise<{ tokens: TokenPair; user: UserSession }> => {
  await new Promise((resolve) => window.setTimeout(resolve, 260));
  return {
    tokens: { accessToken: token("access"), refreshToken: token("refresh"), tokenType: "Bearer", expiresIn: 900 },
    user: {
      id: "user-platform-admin",
      displayName: "Maya Chen",
      email: "maya.chen@example.test",
      role: "Platform Administrator",
      permissions: ["*"],
    },
  };
};

export const demoLogout = async (): Promise<void> => {
  await new Promise((resolve) => window.setTimeout(resolve, 90));
};

export const demoProjects: Project[] = [
  { id: "project-nova", name: "Nova Plant Modernization", code: "NOVA-24", description: "Modernize production planning and asset visibility across three sites.", owner: "Maya Chen", status: "inProgress", health: 88, progress: 72, dueDate: "2026-10-18", members: 18, tasks: 46, color: "#2878ff" },
  { id: "project-atlas", name: "Atlas Quality System", code: "ATLAS-11", description: "A governed quality workflow for engineering and validation teams.", owner: "Jon Bell", status: "active", health: 94, progress: 58, dueDate: "2026-11-02", members: 12, tasks: 29, color: "#27b27e" },
  { id: "project-orbit", name: "Orbit Energy Reporting", code: "ORBIT-07", description: "Unify operational energy data and compliance reporting.", owner: "Sara Novak", status: "atRisk", health: 63, progress: 41, dueDate: "2026-09-29", members: 9, tasks: 21, color: "#e6a23c" },
  { id: "project-bridge", name: "Bridge Supplier Portal", code: "BRIDGE-18", description: "Create a secure supplier collaboration experience.", owner: "Owen Wright", status: "completed", health: 98, progress: 100, dueDate: "2026-08-22", members: 7, tasks: 34, color: "#8b5cf6" },
  { id: "project-helix", name: "Helix Service Enablement", code: "HELIX-03", description: "Standardize service handoffs, escalations and customer insight.", owner: "Leila Haddad", status: "pending", health: 76, progress: 16, dueDate: "2026-12-10", members: 14, tasks: 17, color: "#ec6b9d" },
];

export const demoTasks: Task[] = [
  { id: "task-1", title: "Validate equipment data contract", project: "Nova Plant Modernization", status: "inProgress", priority: "high", assignee: "Maya Chen", dueDate: "2026-09-10", estimate: "2d" },
  { id: "task-2", title: "Review supplier risk report", project: "Orbit Energy Reporting", status: "review", priority: "critical", assignee: "Sara Novak", dueDate: "2026-09-08", estimate: "4h" },
  { id: "task-3", title: "Publish quality workflow v2", project: "Atlas Quality System", status: "backlog", priority: "normal", assignee: "Jon Bell", dueDate: "2026-09-14", estimate: "1d" },
  { id: "task-4", title: "Close acceptance evidence", project: "Bridge Supplier Portal", status: "done", priority: "normal", assignee: "Owen Wright", dueDate: "2026-08-22", estimate: "3h" },
  { id: "task-5", title: "Map escalation ownership", project: "Helix Service Enablement", status: "inProgress", priority: "high", assignee: "Leila Haddad", dueDate: "2026-09-16", estimate: "1d" },
  { id: "task-6", title: "Add German notification templates", project: "Atlas Quality System", status: "backlog", priority: "low", assignee: "Maya Chen", dueDate: "2026-09-22", estimate: "5h" },
  { id: "task-7", title: "Reconcile monthly energy readings", project: "Orbit Energy Reporting", status: "inProgress", priority: "high", assignee: "Jon Bell", dueDate: "2026-09-11", estimate: "2d" },
  { id: "task-8", title: "Run workspace access review", project: "Nova Plant Modernization", status: "done", priority: "critical", assignee: "Maya Chen", dueDate: "2026-09-03", estimate: "1h" },
];

export const demoDocuments: DocumentRecord[] = [
  { id: "doc-1", name: "Nova architecture handoff.pdf", type: "PDF", category: "Architecture", owner: "Maya Chen", modifiedAt: "2026-09-05", size: "2.4 MB", status: "active" },
  { id: "doc-2", name: "Q3 validation matrix.xlsx", type: "XLSX", category: "Quality", owner: "Jon Bell", modifiedAt: "2026-09-04", size: "824 KB", status: "active" },
  { id: "doc-3", name: "Supplier onboarding guide.docx", type: "DOCX", category: "Operations", owner: "Sara Novak", modifiedAt: "2026-09-02", size: "1.1 MB", status: "active" },
  { id: "doc-4", name: "Energy reporting data dictionary.txt", type: "TXT", category: "Data", owner: "Owen Wright", modifiedAt: "2026-08-30", size: "48 KB", status: "active" },
  { id: "doc-5", name: "Service escalation map.png", type: "PNG", category: "Service", owner: "Leila Haddad", modifiedAt: "2026-08-28", size: "680 KB", status: "archived" },
  { id: "doc-6", name: "Tenant security review.pdf", type: "PDF", category: "Governance", owner: "Maya Chen", modifiedAt: "2026-08-26", size: "3.8 MB", status: "active" },
];

export const demoReports: Report[] = [
  { id: "report-1", name: "Portfolio health", description: "Delivery, risk and resource health across active projects.", owner: "Maya Chen", lastRun: "Today, 09:14", schedule: "Every morning", status: "active", coverage: 92 },
  { id: "report-2", name: "Open work ageing", description: "Aging and throughput of operational tasks.", owner: "Jon Bell", lastRun: "Yesterday, 17:20", schedule: "Every Monday", status: "active", coverage: 76 },
  { id: "report-3", name: "Access governance review", description: "Memberships, permissions and recent access changes.", owner: "Maya Chen", lastRun: "Sep 01, 2026", schedule: "Monthly", status: "pending", coverage: 100 },
  { id: "report-4", name: "Energy compliance pack", description: "Evidence and trends for energy reporting controls.", owner: "Sara Novak", lastRun: "Aug 30, 2026", schedule: "On demand", status: "completed", coverage: 84 },
];

export const demoNotifications: AppNotification[] = [
  { id: "notification-1", title: "Project health changed", body: "Orbit Energy Reporting moved to At risk after the latest analysis.", type: "insight", priority: "high", createdAt: "12 minutes ago", read: false, actionLabel: "Review insight" },
  { id: "notification-2", title: "Task needs review", body: "Supplier risk report is ready for your approval.", type: "task", priority: "critical", createdAt: "48 minutes ago", read: false, actionLabel: "Open task" },
  { id: "notification-3", title: "Document uploaded", body: "Q3 validation matrix.xlsx was added to Atlas Quality System.", type: "project", priority: "normal", createdAt: "2 hours ago", read: false, actionLabel: "View document" },
  { id: "notification-4", title: "Access review completed", body: "The monthly workspace access review has been completed successfully.", type: "security", priority: "normal", createdAt: "Yesterday", read: true },
  { id: "notification-5", title: "Analysis package ready", body: "The Nova project intelligence context package is ready for agents.", type: "system", priority: "normal", createdAt: "Yesterday", read: true, actionLabel: "Open context" },
];

export const demoActivity: ActivityItem[] = [
  { id: "activity-1", actor: "Maya Chen", action: "updated the health review for", resource: "Nova Plant Modernization", timestamp: "12 min ago", tone: "blue" },
  { id: "activity-2", actor: "Jon Bell", action: "completed", resource: "Q3 validation matrix", timestamp: "42 min ago", tone: "green" },
  { id: "activity-3", actor: "Sara Novak", action: "uploaded a document to", resource: "Orbit Energy Reporting", timestamp: "2 hr ago", tone: "purple" },
  { id: "activity-4", actor: "System", action: "detected an insight in", resource: "Orbit Energy Reporting", timestamp: "3 hr ago", tone: "amber" },
  { id: "activity-5", actor: "Owen Wright", action: "approved the release of", resource: "Bridge Supplier Portal", timestamp: "Yesterday", tone: "green" },
];

export const demoIntelligence: IntelligenceData = {
  projectId: "project-nova",
  projectName: "Nova Plant Modernization",
  state: "ready",
  lastAnalysis: "2026-09-05T08:42:00Z",
  analysisVersion: "analysis-17.4",
  healthScore: 88,
  healthBreakdown: [
    { label: "Architecture", score: 91, detail: "Layer direction is consistent across 18 modules." },
    { label: "Testing", score: 82, detail: "Coverage is healthy; two integration paths need evidence." },
    { label: "Dependencies", score: 86, detail: "No circular dependency detected." },
    { label: "Documentation", score: 94, detail: "Core rules and handoff documents are current." },
    { label: "Maintainability", score: 87, detail: "Three high-change files merit review." },
  ],
  filesAnalyzed: 184,
  languages: [
    { name: "Python", percentage: 54, loc: 23840 },
    { name: "TypeScript", percentage: 27, loc: 11980 },
    { name: "SQL", percentage: 9, loc: 3820 },
    { name: "Markdown", percentage: 7, loc: 2740 },
    { name: "Other", percentage: 3, loc: 1160 },
  ],
  architecture: [
    { layer: "Presentation", modules: 8, score: 95 },
    { layer: "Application", modules: 14, score: 89 },
    { layer: "Domain", modules: 11, score: 92 },
    { layer: "Infrastructure", modules: 18, score: 78 },
  ],
  dependencies: [
    { name: "Django", type: "external", version: "6.0", risk: "low" },
    { name: "React", type: "external", version: "19.1", risk: "low" },
    { name: "projectIntelligence", type: "internal", version: "0.17.0", risk: "low" },
    { name: "sharedKernel", type: "internal", version: "0.17.0", risk: "medium" },
    { name: "Celery", type: "external", version: "5.5", risk: "medium" },
    { name: "legacyReports", type: "internal", version: "0.4.2", risk: "high" },
  ],
  changes: [
    { path: "backend/apps/projectIntelligence/application/services/intelligenceServices.py", kind: "modified", author: "Maya Chen", timestamp: "2 hr ago" },
    { path: "frontend-web/src/features/intelligence/IntelligencePage.tsx", kind: "added", author: "Tekarai Agent", timestamp: "Yesterday" },
    { path: "docs/ArchitectureHandoff.md", kind: "modified", author: "Jon Bell", timestamp: "Yesterday" },
    { path: "legacyReports/adapter.py", kind: "deleted", author: "Maya Chen", timestamp: "Sep 02" },
  ],
  insights: [
    { id: "insight-1", severity: "high", title: "High-change infrastructure adapter", what: "The storage adapter changed 12 times in the last 30 days.", why: "Frequent changes increase regression and release coordination risk.", evidence: "Git history: 12 commits; 4 callers; 2 missing integration fixtures.", confidence: 0.94, source: "GitAnalyzer + ArchitectureAnalyzer" },
    { id: "insight-2", severity: "medium", title: "Documentation and code are slightly out of sync", what: "The handoff names an older analyzer version.", why: "Agents may select stale context when the version is ambiguous.", evidence: "docs/ArchitectureHandoff.md: v0.16 vs current analyzer: v0.17.", confidence: 0.88, source: "DocumentationAnalyzer" },
    { id: "insight-3", severity: "low", title: "Two integration paths need evidence", what: "Notification delivery paths lack a current fixture.", why: "The absence limits confidence in the delivery contract.", evidence: "TestAnalyzer: 2 paths without matching integration fixture.", confidence: 0.82, source: "TestAnalyzer" },
  ],
  recommendations: [
    { id: "recommendation-1", priority: "high", title: "Add storage-adapter contract fixtures", problem: "High-change adapter has incomplete integration evidence.", benefit: "Reduce regression risk and make analyzer findings reproducible.", risk: "Low; adds test and fixture maintenance.", status: "review" },
    { id: "recommendation-2", priority: "medium", title: "Refresh architecture handoff version", problem: "Documentation references a stale analyzer version.", benefit: "Improves agent context accuracy and handoff continuity.", risk: "Low; documentation-only change.", status: "new" },
    { id: "recommendation-3", priority: "low", title: "Add notification path examples", problem: "Two delivery paths have no fixture.", benefit: "Makes integration coverage visible to future reviewers.", risk: "Low.", status: "deferred" },
  ],
  contextFiles: [
    "backend/apps/projectIntelligence/application/services/intelligenceServices.py",
    "backend/apps/projectIntelligence/domain/services/intelligenceEngines.py",
    "backend/apps/sharedKernel/application/requestContext.py",
    "docs/ArchitectureHandoff.md",
    "backend/tests/integration/testPhase17ApiContract.py",
  ],
};
