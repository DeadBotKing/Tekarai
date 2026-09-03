# 05 — Relationship Catalog

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §29–31, §35
Every FK declares owner, dependent, cardinality, delete behavior, tenant
scope (spec §29). Delete behaviors: PROTECT · RESTRICT · SET_NULL ·
CASCADE* (justified only) — CASCADE is forbidden as a default (spec §31).
"SD" on the dependent = dependent row itself soft-deletes (no DB cascade).
Cross-tenant FKs are forbidden unless marked platform-level (08).

---

## 1. Platform Core · Tenancy · Configuration

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| Tenant → FeatureFlag | Tenant | FeatureFlag | 1:N | SD | platform → tenant |
| Feature → FeatureFlag | Feature | FeatureFlag | 1:N | PROTECT | platform |
| Lookup → LookupValue | Lookup | LookupValue | 1:N | PROTECT | same tenant |
| Tag → TagAssignment | Tag | TagAssignment | 1:N | CASCADE* | same tenant |
| CustomFieldDefinition → CustomFieldValue | CustomFieldDefinition | CustomFieldValue | 1:N | PROTECT | same tenant |
| (polymorphic) owner → TagAssignment/CustomFieldValue/Attachment/Address/ContactInformation | owning entity | platform record | N:1 per owner | owner SD (no cascade) | same tenant |

*TagAssignment/attachment rows are meaningless without their tag/owner —
the only justified CASCADE set in Platform Core.

## 2. Identity

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| User → UserRole / UserPermission / Session / AuthenticationMethod / SecurityEvent | User | each | 1:N | SD (session SD; SecurityEvent APPEND) | same tenant |
| Role → RolePermission | Role | RolePermission | 1:N | CASCADE* | same tenant |
| Permission → RolePermission / UserPermission | Permission | each | 1:N | PROTECT | platform |
| Role → UserRole | Role | UserRole | 1:N | PROTECT (role in use) | same tenant |
| base audit columns createdBy/updatedBy/deletedBy → User | User | any base entity | N:1 | **SET_NULL** (spec §35) | same tenant |

## 3. Organization

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| Tenant → Organization | Tenant | Organization | 1:N | SD | same tenant |
| Organization → OrganizationUnit / Position / Location / CostCenter | Organization | each | 1:N | SD | same tenant |
| OrganizationUnit → OrganizationUnit (parent) | parent unit | child units | 1:N | PROTECT (children exist) | same tenant |
| OrganizationUnit → Department / Division / Team | unit | typed unit | 1:1 | SD | same tenant |
| JobTitle → Position | JobTitle | Position | 1:N | SET_NULL | same tenant |
| OrganizationUnit → OrganizationHierarchy | unit | hierarchy rows | 1:N | APPEND | same tenant |
| CostCenter → Department | CostCenter | Department | 1:N | SET_NULL | same tenant |

## 4. Workforce + Performance

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| User → Employee (optional identity link) | User | Employee | 1:0..1 | SET_NULL (unlink only) | same tenant |
| Employee → Employment / Assignment / Manager / Contact / Address / Document / Skill / Certification | Employee | each | 1:N | SD (EmploymentHistory APPEND) | same tenant |
| Organization → Employment | Organization | Employment | 1:N | PROTECT | same tenant |
| Position → Employment | Position | Employment | 1:N | PROTECT | same tenant |
| OrganizationUnit → EmployeeAssignment | unit | assignment | 1:N | PROTECT | same tenant |
| Employee → EmployeeManager (manager) | Employee (manager) | reporting rows | 1:N | SD | same tenant |
| Skill → EmployeeSkill; Certification → EmployeeCertification | catalogue | link | 1:N | PROTECT | same tenant |
| EvaluationCycle → EmployeeEvaluation / EvaluationCriteria | cycle | each | 1:N | PROTECT | same tenant |
| Employee → EmployeeEvaluation | Employee | evaluation | 1:N | PROTECT | same tenant |
| EmployeeEvaluation → EvaluationScore | evaluation (aggregate root) | scores | 1:N | SD via root only (Phase 03 §6) | same tenant |
| EvaluationCriteria → EvaluationScore; reviewer(User/Employee) → EvaluationScore | each | scores | 1:N | PROTECT | same tenant |

## 5. Projects + Tasks

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| Tenant → Project | Tenant | Project | 1:N | SD | same tenant |
| Project → ProjectMember / Phase / Milestone / Dependency / Budget / Risk / Issue / DocumentLink | Project | each | 1:N | SD | same tenant |
| ProjectRole → ProjectMember | ProjectRole | member row | 1:N | PROTECT | same tenant |
| Project → Task (loose contract ref) | Project | Task | 1:N | **SET_NULL** (Tasks stay independent, spec §13/§14) | same tenant |
| Task → Task (parent/subtask) | parent task | subtask | 1:N | SD | same tenant |
| TaskStatus/Priority/Type → Task | vocabulary | task | 1:N | PROTECT | same tenant |
| Task → Assignment / Dependency / Comment / Attachment / Checklist / TimeEntry / History | Task | each | 1:N | SD (Comment/TimeEntry/History APPEND) | same tenant |
| TaskChecklist → TaskChecklistItem | checklist | item | 1:N | CASCADE* (justified: meaningless alone) | same tenant |
| Task → TaskDependency(dependsOn) | depended-on task | dependency rows | 1:N | SD | same tenant |

## 6. Assets + Devices + Maintenance

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| AssetCategory → AssetType; AssetType → Asset | catalogue | each | 1:N | PROTECT | same tenant |
| AssetStatus → Asset | vocabulary | asset | 1:N | PROTECT | same tenant |
| Asset → Assignment / Location / Ownership / Lifecycle / DocumentLink / ValueHistory | Asset | each | 1:N | SD (Lifecycle/ValueHistory APPEND) | same tenant |
| Location → AssetLocation | Location | row | 1:N | PROTECT | same tenant |
| Asset → Device (optional) | Asset | Device | 1:0..N | SET_NULL (device survives) | same tenant |
| DeviceManufacturer → DeviceModel; DeviceModel → Device; DeviceType → Device; DeviceStatus → Device | catalogue | device | 1:N | PROTECT | same tenant |
| Device → Credential / Registration / Heartbeat / Telemetry / Configuration / Event | Device | each | 1:N | SD credential/registration/config; APPEND streams | same tenant |
| Asset/Device (targetType+targetId) → MaintenancePlan | target | plan | polymorphic 1:N | PROTECT | same tenant |
| MaintenancePlan → Schedule / WorkOrder | plan | each | 1:N | SD | same tenant |
| WorkOrder → Task / Event / Part / Cost / History | work order | each | 1:N | SD (Event/History APPEND) | same tenant |
| Employee → MaintenanceTechnician | Employee | technician | 1:0..1 | SD | same tenant |
| Employee → MaintenanceTask (technician) | Employee | task | 1:N | SET_NULL | same tenant |

## 7. Documents + Workflow

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| DocumentType/Category → Document; DocumentFolder → Document | catalogue/folder | document | 1:N | PROTECT | same tenant |
| Document → Version / Permission / Share / Metadata / Attachment / WorkflowLink | Document | each | 1:N | SD (versions immutable, never overwritten — spec §18) | same tenant |
| DocumentFolder → DocumentFolder (parent) | parent | child | 1:N | PROTECT | same tenant |
| Workflow → WorkflowVersion → WorkflowDefinition → Node/Transition | each parent | children | 1:N | SD (published versions PROTECT) | same tenant |
| WorkflowDefinition → WorkflowInstance | definition | instance | 1:N | PROTECT | same tenant |
| WorkflowInstance → State / Task / Action / Approval / History | instance | each | 1:N | SD (Action/History APPEND) | same tenant |
| WorkflowTask → WorkflowApproval | task | approvals | 1:N | SD | same tenant |
| (polymorphic) target → WorkflowInstance | any entity | instance | 1:N | SET_NULL on target hard-delete (never; SD default) | same tenant |

## 8. Communication + Notification + Audit

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| Conversation → ConversationMember / Message | conversation | each | 1:N | SD | same tenant |
| ConversationType → Conversation | vocabulary | conversation | 1:N | PROTECT | platform |
| Message → Attachment / Reaction / ReadReceipt | message | each | 1:N | SD | same tenant |
| Message → Message (reply/thread) | parent | reply | 1:N | SET_NULL | same tenant |
| Conversation → Channel (profile) | conversation | channel | 1:0..1 | SD | same tenant |
| Channel → ChannelMember | channel | member | 1:N | SD | same tenant |
| Conversation → VoiceCall / GroupCall / VideoMeeting | conversation | call/meeting | 1:0..N | SD | same tenant |
| VoiceCall → VoiceCallParticipant; VideoMeeting → MeetingParticipant / MeetingSession | parent | participants/sessions | 1:N | SD | same tenant |
| MeetingSession → ScreenShareSession / MeetingRecording | session | each | 1:N | SD | same tenant |
| User → Presence | user | presence rows | 1:N | SD | same tenant |
| PresenceStatus → Presence | vocabulary | presence | 1:N | PROTECT | platform |
| NotificationTemplate → Notification | template | notification | 1:N | PROTECT | same tenant |
| Notification → NotificationRecipient / NotificationDelivery | notification | each | 1:N | SD (Delivery APPEND) | same tenant |
| NotificationChannel → NotificationDelivery | vocabulary | delivery | 1:N | PROTECT | platform |
| User → NotificationPreference | user | preference | 1:N | SD | same tenant |
| Tenant → AuditEvent; actor User → AuditEvent | tenant/actor | audit rows | 1:N | APPEND (never deleted; SET_NULL if actor purged) | same tenant |

## 9. Reporting · Analytics · AI · Integration

| Relationship | Owner | Dependent | Cardinality | Delete | Tenant scope |
|---|---|---|---|---|---|
| ReportDefinition → Parameter / Execution / Schedule / Access | definition | each | 1:N | SD | same tenant |
| ReportExecution → ReportOutput | execution | outputs | 1:N | SD | same tenant |
| MetricDefinition → MetricValue; KpiDefinition → KpiValue | definition | values | 1:N | APPEND | same tenant |
| Dashboard → DashboardWidget | dashboard | widget | 1:N | CASCADE* (justified: layout-part) | same tenant |
| Dashboard/Scope → AnalyticsSnapshot | owner | snapshots | 1:N | APPEND | same tenant |
| AiProvider → AiModel → AiModelVersion | each parent | children | 1:N | SD | platform registry |
| AiModelVersion → AiAgent | version | agent | 1:N | PROTECT | platform → tenant |
| AiAgent → AiAgentExecution | agent | executions | 1:N | APPEND | same tenant |
| AiRequest → AiResponse | request | response | 1:1 | SD | same tenant |
| AiConversation → AiMessage | conversation | messages | 1:N | APPEND | same tenant |
| AiKnowledgeSource → AiKnowledgeDocument → AiEmbedding | each parent | children | 1:N | SD doc; APPEND embeddings | same tenant |
| IntegrationType → Integration | vocabulary | integration | 1:N | PROTECT | platform |
| Integration → Credential / Endpoint / Connection / Mapping / Job / Event / Error | integration | each | 1:N | SD (Execution/Error APPEND) | same tenant |
| IntegrationJob → IntegrationExecution | job | executions | 1:N | APPEND | same tenant |

## 10. Many-to-Many Resolutions (spec §30 — no blind M2M)

| M↔N | Intermediate entity (carries) |
|---|---|
| Project ↔ User/Employee | ProjectMember (role, joinedAt, leftAt, allocationPct) |
| Task ↔ User | TaskAssignment (role, assignedAt, removedAt) |
| User ↔ Role | UserRole (scopeType, scopeId, grantedBy/At) |
| Role ↔ Permission | RolePermission (—) |
| User ↔ Permission | UserPermission (effect, scope) |
| Conversation ↔ User | ConversationMember (role, joinedAt, mutedUntil) |
| Channel ↔ User | ChannelMember (role, joinedAt) |
| Employee ↔ Skill | EmployeeSkill (level, verifiedBy) |
| Employee ↔ Certification | EmployeeCertification (issuedAt, expiresAt) |
| Project ↔ Project (dependency) | ProjectDependency (type) |
| Task ↔ Task (dependency) | TaskDependency (type, lag) |
| Document ↔ Subject | DocumentPermission (permissionLevel) |
| Tag ↔ any | TagAssignment (ownerType, ownerId) |
| CustomFieldDefinition ↔ any | CustomFieldValue (typed value) |

## 11. CASCADE Justification Register (spec §31 — every CASCADE listed)

| FK | Why CASCADE is justified |
|---|---|
| Role→RolePermission, Permission→RolePermission | pure link rows, meaningless alone |
| TaskChecklist→TaskChecklistItem | item is a layout child of its checklist |
| Tag→TagAssignment | link row without tag has no meaning |
| Dashboard→DashboardWidget | widget is a layout part of its dashboard |

All other dependents: SD / PROTECT / SET_NULL / APPEND per tables above.
Any new CASCADE requires an entry here (review gate).
