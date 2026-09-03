# 04 — Entity Catalog (spec §51: 17 attributes per entity)

**Status:** DESIGN (Phase 04) · **Total entities: 195** (188 Core + 7 Industry-Extension)
Reading guide — the 17 §51 attributes are recorded as follows:

- **Entity Name** — column `Entity`
- **Domain / Owner** — the section heading (owner context per Phase 03)
- **Purpose / Fields** — column `Purpose` + full key-field groups in
  `03DatabaseDictionary.md` (same entity names)
- **Primary Key** — column `PK` (UUID everywhere, spec §3)
- **Tenant Owned?** — `T` (✓ = tenant-owned)
- **Base Entity?** — `B` (full = «base» · app = «append» reduced base)
- **Foreign Keys / Relationships** — column `FKs →` (cardinality inline;
  complete registry: `05RelationshipCatalog.md`)
- **Indexes** — **standard set implied on every tenant-owned base entity**:
  `(tenantId)`, `(tenantId, isActive)`, `(tenantId, createdAt)` + FK indexes
  (`06IndexStrategy.md` §2); column lists only *additional* indexes
- **Unique Constraints** — column `Unique` (tenant-aware form; full list
  `07ConstraintCatalog.md`)
- **Delete Policy** — `Del`: SD soft-delete · PROTECT · SET_NULL ·
  CASCADE* (justified exceptions only, spec §31) · APPEND (immutable,
  retention-purge only)
- **Audit Required?** — `Aud`: ✓ audit events · △ security/log stream · —
- **Soft Delete?** — `SD` ✓/✗
- **Retention Policy** — `Ret`: L long · M medium · S short · C configurable
  (`10DataRetentionPolicy.md`)
- **Notes** — `Notes` (incl. concurrency/versioning decisions, spec §47)

Naming notes: spec PascalCase acronyms map to the project standard as
`AIModel→AiModel`, `AIProvider→AiProvider`, … and `WinCCServer→WinCcServer`,
`WinCCTag→WinCcTag`, … (compound-safe identifiers; ADR-001 camelCase
discipline). Both forms refer to the same entity.

---

## Platform Core · Tenancy · Configuration (owner: Platform Core / Tenancy / Configuration)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tenant | isolation boundary root | UUID | — | full | SD | ✓ | ✓ | L | — | code (global) | (code) | status enum; closing a tenant is a lifecycle event, never hard delete |
| SystemSetting | system runtime setting | UUID | — | full | SD | ✓ | ✓ | L | — | (scope,key) | — | isSecret values never returned raw |
| Feature | registered feature | UUID | — | full | SD | ✓ | ✓ | L | — | code | — | registry populated by code/deployment |
| FeatureFlag | flag per scope | UUID | ✓ | full | SD | ✓ | ✓ | M | featureId →Feature N:1 | (tenantId,featureId,scope) | (tenantId,enabled) | scope system/tenant |
| Configuration | scoped config entries | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,scope,key) | — | complements env settings (ADR-009) |
| Lookup | controlled list group | UUID | ✓ | full | SD | ✓ | ✓ | M | — | (tenantId,code) | — | controlled vocabulary (§37) |
| LookupValue | list entry | UUID | ✓ | full | SD | △ | ✓ | M | lookupId →Lookup N:1 | (tenantId,lookupId,code) | — | sortOrder controlled |
| Tag | taxonomy tag | UUID | ✓ | full | SD | — | ✓ | M | — | (tenantId,name) | — | |
| TagAssignment | polymorphic tag link | UUID | ✓ | app | APPEND | — | ✗ | M | tagId →Tag N:1 | (tagId,ownerType,ownerId) | (ownerType,ownerId) | untag = new negative or purge policy; immutable facts |
| CustomFieldDefinition | extension field schema | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | (tenantId,targetType) | §42: never replaces modelling |
| CustomFieldValue | extension field data | UUID | ✓ | full | SD | △ | ✓ | L | definitionId →CustomFieldDefinition N:1 | (definitionId,ownerType,ownerId) | (ownerType,ownerId) | value typed by definition |
| Attachment | file metadata | UUID | ✓ | full | SD | △ | ✓ | M/L | — | — | (ownerType,ownerId) | binary in object storage (§40) |
| Address | reusable address | UUID | ✓ | full | SD | — | ✓ | L | — | — | (ownerType,ownerId) | geo coordinates VO |
| ContactInformation | reusable contact | UUID | ✓ | full | SD | — | ✓ | L | — | — | (ownerType,ownerId) | type enum |

## Identity (owner: Identity)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| User | auth principal | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,username),(tenantId,email) | (tenantId,status) | ≠ Employee (spec §10); passwordHash only; userType enum |
| Role | role definition | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | — | isSystem roles undeletable (PROTECT effective) |
| Permission | permission catalogue | UUID | — | full | PROTECT | ✓ | ✓ | L | — | code (global) | (resource) | global catalogue shared by tenants |
| RolePermission | role↔permission | UUID | — | full | CASCADE* | △ | ✓ | L | roleId, permissionId | (roleId,permissionId) | — | *meaningless without role/permission |
| UserRole | user↔role scoped | UUID | ✓ | full | SD | ✓ | ✓ | L | userId, roleId | (userId,roleId,scopeType,scopeId) | (roleId) | grant/revocation audited |
| UserPermission | direct permission | UUID | ✓ | full | SD | ✓ | ✓ | L | userId, permissionId | (userId,permissionId,scope) | — | effect allow/deny |
| Session | session/token | UUID | ✓ | full | SD | △ | ✓ | S/M | userId | (userId,tokenHash) | (tenantId,expiresAt) | tokenHash only, never raw; purge expired (Ret S) |
| AuthenticationMethod | MFA factor | UUID | ✓ | full | SD | ✓ | ✓ | M | userId | (userId,methodType) | — | secretRef, never inline secret |
| AccessPolicy | policy rule | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,subjectType,subjectId) | (tenantId,resource) | priority ordered |
| SecurityEvent | security stream | UUID | ✓ | app | APPEND | △ | ✗ | L | userId | — | (tenantId,eventType,occurredAt),(userId,occurredAt) | append-only security telemetry |

## Organization (owner: Organization)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Organization | legal entity root | UUID | ✓ | full | SD | ✓ | ✓ | L | parentOrgId →Organization N:1 | (tenantId,code) | (tenantId,status) | legal metadata structured |
| OrganizationUnit | generic hierarchy node | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationId; parentId →OrganizationUnit | (tenantId,organizationId,code) | (parentId) | acyclic check (07 §3); unitType enum |
| Department | typed unit | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationUnitId; costCenterId | (tenantId,code) | — | headUserId SET_NULL |
| Division | typed unit | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationUnitId | (tenantId,code) | — | |
| Team | typed unit | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationUnitId | (tenantId,code) | — | |
| Position | position definition | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationId; jobTitleId | (tenantId,code) | (organizationId) | assignments live in Workforce |
| JobTitle | title catalogue | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | — | |
| Location | site | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationId; addressId | (tenantId,code) | — | |
| CostCenter | cost center | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationId | (tenantId,code) | — | |
| OrganizationHierarchy | temporal hierarchy | UUID | ✓ | app | APPEND | ✓ | ✗ | L | unitId; parentId | (unitId,validFrom) | (parentId,validFrom) | §36 temporal facts |

## Workforce / HR (owner: Workforce)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Employee | person record | UUID | ✓ | full | SD | ✓ | ✓ | L | userId →User 1:1 optional | (tenantId,employeeNumber) | (tenantId,status),(userId) | ≠ User; nationalId stored as secretRef (privacy) |
| Employment | employment record | UUID | ✓ | full | SD | ✓ | ✓ | L | employeeId; organizationId; positionId | (employeeId,startDate,type) | (organizationId),(positionId) | one active per employee (07 §3) |
| EmploymentHistory | employment facts | UUID | ✓ | app | APPEND | ✓ | ✗ | L | employmentId | — | (employmentId,changedAt) | |
| EmployeeAssignment | temporal unit assignment | UUID | ✓ | full | SD | ✓ | ✓ | L | employeeId; organizationUnitId | (employeeId,organizationUnitId,startDate) | (organizationUnitId,startDate) | §36 temporal; overlap check |
| EmployeeManager | reporting relationship | UUID | ✓ | full | SD | ✓ | ✓ | L | employeeId; managerId | (employeeId,managerId,validFrom) | (managerId) | temporal |
| EmployeeContact | contacts | UUID | ✓ | full | SD | — | ✓ | M | employeeId | (employeeId,type,value) | — | |
| EmployeeAddress | addresses | UUID | ✓ | full | SD | — | ✓ | L | employeeId; addressId | (employeeId,addressId) | — | temporal |
| EmployeeDocument | doc link | UUID | ✓ | full | SD | △ | ✓ | L | employeeId; documentId | (employeeId,documentId,documentRole) | (documentId) | |
| EmployeeSkill | skill level | UUID | ✓ | full | SD | — | ✓ | M | employeeId; skillId | (employeeId,skillId) | (skillId) | level enum |
| Skill | skill catalogue | UUID | ✓ | full | SD | — | ✓ | M | — | (tenantId,code) | — | |
| EmployeeCertification | certification | UUID | ✓ | full | SD | — | ✓ | M | employeeId; certificationId | (employeeId,certificationId,issuedAt) | (certificationId) | expiry tracked |
| Certification | cert catalogue | UUID | ✓ | full | SD | — | ✓ | M | — | (tenantId,code) | — | |

## Performance (owner: Performance)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EvaluationCycle | evaluation period | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | (tenantId,status),(tenantId,periodType,startDate) | period enum d/w/m/q/y; no overlapping open cycle (07 §3) |
| EmployeeEvaluation | evaluation aggregate root | UUID | ✓ | full | SD | ✓ | ✓ | L | evaluationCycleId; employeeId | (evaluationCycleId,employeeId) | (employeeId),(status) | aggregate root (Phase 03 §6) |
| EvaluationCriteria | criteria per cycle | UUID | ✓ | full | SD | ✓ | ✓ | L | evaluationCycleId | (evaluationCycleId,code) | — | weightPercentage; Σweights=100 (07 §3) |
| EvaluationScore | score per criterion/reviewer | UUID | ✓ | full | SD | ✓ | ✓ | L | evaluationId; criteriaId; reviewerId | (evaluationId,criteriaId,reviewerId) | (reviewerId) | editable + every change audited (spec §12); version col (optimistic lock) |

## Project (owner: Projects)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Project | project root | UUID | ✓ | full | SD | ✓ | ✓ | L | organizationUnitId | (tenantId,code) | (tenantId,status),(tenantId,createdAt) | budget Decimal+currency (§38); version col |
| ProjectMember | M↔N with data | UUID | ✓ | full | SD | ✓ | ✓ | M | projectId; userId; employeeId; projectRoleId | (projectId,userId) | (userId) | §30 intermediate entity (role/joinedAt/leftAt) |
| ProjectRole | role catalogue | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | — | |
| ProjectPhase | phases | UUID | ✓ | full | SD | ✓ | ✓ | L | projectId | (projectId,order) | — | ordered |
| ProjectMilestone | milestones | UUID | ✓ | full | SD | ✓ | ✓ | L | projectId; phaseId | (projectId,name) | (dueDate) | |
| ProjectDependency | project deps | UUID | ✓ | full | SD | △ | ✓ | M | projectId; dependsOnProjectId | (projectId,dependsOnProjectId) | (dependsOnProjectId) | acyclic (07 §3) |
| ProjectBudget | budget lines | UUID | ✓ | full | SD | ✓ | ✓ | L | projectId | (projectId,fiscalPeriod) | — | Decimal only |
| ProjectRisk | risk register | UUID | ✓ | full | SD | ✓ | ✓ | M | projectId | (projectId,title) | (status) | probability/impact enums |
| ProjectIssue | issue register | UUID | ✓ | full | SD | ✓ | ✓ | M | projectId | (projectId,title) | (status,severity) | |
| ProjectDocument | doc link | UUID | ✓ | full | SD | △ | ✓ | L | projectId; documentId | (projectId,documentId,documentRole) | (documentId) | |

## Task (owner: Tasks)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Task | task root | UUID | ✓ | full | SD | ✓ | ✓ | L | projectId (loose ref); statusId; priorityId; typeId; parentTaskId | (tenantId,code) | (projectId,status),(assignee via assignment),(tenantId,deadline) | deadline ≥ start (07); dependency graph acyclic; version col |
| TaskStatus | status vocabulary | UUID | ✓ | full | PROTECT | △ | ✓ | L | — | (tenantId,code) | — | lifecycle order |
| TaskPriority | priority vocabulary | UUID | ✓ | full | PROTECT | — | ✓ | L | — | (tenantId,code) | — | |
| TaskType | type vocabulary | UUID | ✓ | full | PROTECT | — | ✓ | L | — | (tenantId,code) | — | defaultWorkflow ref |
| TaskAssignment | task↔user data | UUID | ✓ | full | SD | ✓ | ✓ | M | taskId; userId | (taskId,userId,assignedAt) | (userId,assignedAt) | removedAt temporal |
| TaskDependency | task deps | UUID | ✓ | full | SD | △ | ✓ | M | taskId; dependsOnTaskId | (taskId,dependsOnTaskId) | (dependsOnTaskId) | acyclic (07 §3) |
| TaskComment | comments | UUID | ✓ | app | APPEND | △ | ✗ | M | taskId; userId; parentId | — | (taskId,createdAt) | edit = new revision, history kept |
| TaskAttachment | attachments | UUID | ✓ | full | SD | △ | ✓ | M | taskId; attachmentId | (taskId,attachmentId) | — | |
| TaskChecklist | checklists | UUID | ✓ | full | SD | △ | ✓ | M | taskId | (taskId,title) | — | |
| TaskChecklistItem | items | UUID | ✓ | full | CASCADE* | △ | ✓ | M | checklistId | (checklistId,label) | — | *meaningless without checklist (spec §31) |
| TaskTimeEntry | time tracking | UUID | ✓ | app | APPEND | △ | ✗ | M/L | taskId; userId | — | (taskId,startedAt),(userId,startedAt) | minutes Decimal |
| TaskHistory | activity stream | UUID | ✓ | app | APPEND | ✓ | ✗ | L | taskId; actorId | — | (taskId,changedAt) | before/after snapshots |

## Asset (owner: Assets)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Asset | asset root | UUID | ✓ | full | SD | ✓ | ✓ | L | categoryId; typeId; statusId | (tenantId,code) | (tenantId,status),(tenantId,typeId) | physical/digital/financial/operational enum |
| AssetCategory | categories | UUID | ✓ | full | PROTECT | △ | ✓ | L | parentId | (tenantId,code) | — | tree |
| AssetType | types | UUID | ✓ | full | PROTECT | △ | ✓ | L | categoryId | (tenantId,categoryId,code) | — | |
| AssetStatus | status vocabulary | UUID | ✓ | full | PROTECT | △ | ✓ | L | — | (tenantId,code) | — | |
| AssetAssignment | custody temporal | UUID | ✓ | full | SD | ✓ | ✓ | L | assetId; holderType/Id | (assetId,holderType,holderId,startDate) | (holderType,holderId) | §36 |
| AssetLocation | location temporal | UUID | ✓ | full | SD | △ | ✓ | L | assetId; locationId | (assetId,locationId,validFrom) | (locationId) | |
| AssetOwnership | ownership temporal | UUID | ✓ | full | SD | ✓ | ✓ | L | assetId; ownerType/Id | (assetId,ownerType,ownerId,validFrom) | — | share percentage Σ≤100 (07 §3) |
| AssetLifecycle | lifecycle events | UUID | ✓ | app | APPEND | ✓ | ✗ | L | assetId; actorId | — | (assetId,eventDate) | |
| AssetDocument | doc link | UUID | ✓ | full | SD | △ | ✓ | L | assetId; documentId | (assetId,documentId,role) | (documentId) | |
| AssetValueHistory | value stream | UUID | ✓ | app | APPEND | △ | ✗ | L | assetId | — | (assetId,valuedAt) | Decimal+currency |

## Device / OT + Agent (owner: Devices)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Device | device root | UUID | ✓ | full | SD | ✓ | ✓ | L | typeId; modelId; statusId; assetId optional | (tenantId,code) | (tenantId,status),(assetId),(lastSeenAt) | ≠ Agent (spec §16) |
| DeviceType | type vocabulary | UUID | ✓ | full | PROTECT | △ | ✓ | L | — | (tenantId,code) | — | |
| DeviceModel | models | UUID | ✓ | full | PROTECT | △ | ✓ | L | manufacturerId | (tenantId,manufacturerId,code) | — | |
| DeviceManufacturer | makers | UUID | ✓ | full | SD | — | ✓ | L | — | (tenantId,code) | — | |
| DeviceStatus | status vocabulary | UUID | ✓ | full | PROTECT | △ | ✓ | L | — | (tenantId,code) | — | |
| DeviceCredential | credential refs | UUID | ✓ | full | SD | ✓ | ✓ | M | deviceId | (deviceId,credentialType) | — | secretRef only (§49) |
| DeviceRegistration | registration facts | UUID | ✓ | full | SD | ✓ | ✓ | L | deviceId | (deviceId) | — | approvedBy |
| DeviceHeartbeat | heartbeat stream | UUID | ✓ | app | APPEND | — | ✗ | S/C | deviceId | — | (deviceId,occurredAt) | retention configurable; partition candidate (06 §5) |
| DeviceTelemetry | telemetry stream | UUID | ✓ | app | APPEND | — | ✗ | C | deviceId | — | (deviceId,metric,occurredAt) | high-volume; partitioning/purge (06 §5, 10 §3) |
| DeviceConfiguration | versioned config | UUID | ✓ | full | SD | ✓ | ✓ | L | deviceId | (deviceId,version) | — | versions immutable |
| DeviceEvent | event stream | UUID | ✓ | app | APPEND | △ | ✗ | C | deviceId | — | (deviceId,eventType,occurredAt) | severity enum |
| Agent | software agent | UUID | ✓ | full | SD | ✓ | ✓ | M | ownerType/Id | (tenantId,code) | (tenantId,lastSeenAt) | never merged with Device (spec §16) |

## Maintenance (owner: Maintenance)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MaintenancePlan | plan | UUID | ✓ | full | SD | ✓ | ✓ | L | targetType(asset/device) targetId | (tenantId,code) | (targetType,targetId),(status) | cadence enum |
| MaintenanceSchedule | occurrences | UUID | ✓ | full | SD | △ | ✓ | M | planId | (planId,dueAt) | (dueAt,status) | |
| MaintenanceWorkOrder | work order | UUID | ✓ | full | SD | ✓ | ✓ | L | planId optional; targetType/Id; technicianId | (tenantId,code) | (status,dueAt),(technicianId) | completion requires outcome (07 §3) |
| MaintenanceTask | WO tasks | UUID | ✓ | full | SD | △ | ✓ | M | workOrderId; technicianId | (workOrderId,title) | (technicianId,status) | |
| MaintenanceEvent | WO events | UUID | ✓ | app | APPEND | △ | ✗ | L | workOrderId; actorId | — | (workOrderId,occurredAt) | |
| MaintenanceTechnician | technician registry | UUID | ✓ | full | SD | △ | ✓ | M | employeeId | (employeeId) | — | |
| MaintenancePart | parts used | UUID | ✓ | full | SD | △ | ✓ | M | workOrderId | (workOrderId,partRef) | — | Decimal cost |
| MaintenanceCost | costs | UUID | ✓ | full | SD | ✓ | ✓ | L | workOrderId | (workOrderId,costType,occurredAt) | — | Decimal+currency |
| MaintenanceHistory | history | UUID | ✓ | app | APPEND | ✓ | ✗ | L | targetType/Id; actorId | — | (targetType,targetId,occurredAt) | |

## Document (owner: Documents)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Document | document root | UUID | ✓ | full | SD | ✓ | ✓ | L | typeId; categoryId; folderId; ownerId | (tenantId,code) | (tenantId,status),(folderId) | storage via StoragePort (§40) |
| DocumentVersion | immutable version | UUID | ✓ | full | SD | ✓ | ✓ | L | documentId; uploadedBy | (documentId,versionNumber) | (documentId,uploadedAt) | never overwrite (spec §18); checksum |
| DocumentType | type vocabulary | UUID | ✓ | full | PROTECT | △ | ✓ | L | — | (tenantId,code) | — | |
| DocumentCategory | categories | UUID | ✓ | full | PROTECT | △ | ✓ | L | parentId | (tenantId,code) | — | tree |
| DocumentFolder | folder tree | UUID | ✓ | full | SD | △ | ✓ | L | parentId | (tenantId,parentId,name) | — | acyclic (07 §3) |
| DocumentPermission | ACL | UUID | ✓ | full | SD | ✓ | ✓ | L | documentId; subjectType/Id | (documentId,subjectType,subjectId,permissionLevel) | (subjectType,subjectId) | |
| DocumentShare | shares | UUID | ✓ | full | SD | ✓ | ✓ | M | documentId; sharedBy | (documentId,sharedWithType,sharedWithId) | (expiresAt) | |
| DocumentMetadata | metadata | UUID | ✓ | full | SD | — | ✓ | L | documentId | (documentId,key) | — | JSON allowed (§41) |
| DocumentAttachment | attachments | UUID | ✓ | full | SD | △ | ✓ | L | documentId; attachmentId | (documentId,attachmentId) | — | |
| DocumentWorkflow | workflow link | UUID | ✓ | full | SD | ✓ | ✓ | L | documentId; workflowInstanceId | (documentId,workflowInstanceId) | (workflowInstanceId) | trigger contract (Phase 03) |

## Workflow (owner: Workflow)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Workflow | named engine entity | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | — | generic (spec §19) |
| WorkflowVersion | versions | UUID | ✓ | full | SD | ✓ | ✓ | L | workflowId | (workflowId,versionNumber) | — | status draft/published/retired |
| WorkflowDefinition | definition graph | UUID | ✓ | full | SD | ✓ | ✓ | L | workflowVersionId | (workflowVersionId) | — | graph JSON (§41) |
| WorkflowNode | nodes | UUID | ✓ | full | SD | △ | ✓ | L | workflowDefinitionId | (workflowDefinitionId,nodeKey) | — | nodeType enum |
| WorkflowTransition | edges | UUID | ✓ | full | SD | △ | ✓ | L | workflowDefinitionId; from/to nodeKey | (workflowDefinitionId,fromNodeKey,toNodeKey) | — | condition JSON |
| WorkflowInstance | running instance | UUID | ✓ | full | SD | ✓ | ✓ | L | workflowDefinitionId; targetType/Id | — | (targetType,targetId),(status) | version col; only defined transitions (07 §3) |
| WorkflowInstanceState | state snapshot | UUID | ✓ | full | SD | △ | ✓ | M | instanceId | (instanceId) | — | current node |
| WorkflowTask | human tasks | UUID | ✓ | full | SD | ✓ | ✓ | M | instanceId; assigneeId | (instanceId,nodeKey) | (assigneeId,status,dueAt) | |
| WorkflowAction | actions | UUID | ✓ | app | APPEND | ✓ | ✗ | L | instanceId; actorId | — | (instanceId,occurredAt) | |
| WorkflowApproval | approvals | UUID | ✓ | full | SD | ✓ | ✓ | L | workflowTaskId; approverId; delegatedFromId | (workflowTaskId,approverId) | (approverId) | decision enum; delegation audited |
| WorkflowHistory | transition history | UUID | ✓ | app | APPEND | ✓ | ✗ | L | instanceId; actorId | — | (instanceId,occurredAt) | |

## Communication (owner: Communication)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Conversation | chat aggregate | UUID | ✓ | full | SD | ✓ | ✓ | M/L | type; createdBy | — | (tenantId,type,lastMessageAt) | member/role rules by type (07 §3) |
| ConversationMember | membership data | UUID | ✓ | full | SD | ✓ | ✓ | M | conversationId; userId | (conversationId,userId) | (userId) | §30 intermediate entity |
| ConversationType | type vocabulary | UUID | — | full | PROTECT | — | ✓ | L | — | code | — | |
| Message | message | UUID | ✓ | full | SD | △ | ✓ | M/L | conversationId; senderId; replyToId; threadId | — | (conversationId,createdAt) cursor pagination | editedAt/deletedAt policy; generatedByAi flag (governance) |
| MessageAttachment | attachments | UUID | ✓ | full | SD | △ | ✓ | M | messageId; attachmentId | (messageId,attachmentId) | — | |
| MessageReaction | reactions | UUID | ✓ | full | SD | — | ✓ | S/M | messageId; userId | (messageId,userId,emoji) | — | |
| MessageReadReceipt | read state | UUID | ✓ | full | SD | — | ✓ | S/M | messageId; userId | (messageId,userId) | (userId,readAt) | |
| Channel | channel profile | UUID | ✓ | full | SD | ✓ | ✓ | L | conversationId | (conversationId) | (visibility) | announcement/public/private |
| ChannelMember | channel membership | UUID | ✓ | full | SD | ✓ | ✓ | M | channelId; userId | (channelId,userId) | (userId) | |
| VoiceCall | 1:1 call | UUID | ✓ | full | SD | △ | ✓ | M | conversationId; initiatorId | — | (tenantId,startedAt) | |
| VoiceCallParticipant | call participants | UUID | ✓ | full | SD | △ | ✓ | M | callId; userId | (callId,userId) | (userId) | |
| GroupCall | group voice | UUID | ✓ | full | SD | △ | ✓ | M | conversationId; hostId | — | (tenantId,startedAt) | SFU scale path (Phase 02) |
| VideoMeeting | meeting | UUID | ✓ | full | SD | ✓ | ✓ | L | conversationId; hostId | — | (tenantId,scheduledAt) | recurring capable |
| MeetingParticipant | participants | UUID | ✓ | full | SD | △ | ✓ | M | meetingId; userId | (meetingId,userId) | (userId) | |
| MeetingSession | sessions | UUID | ✓ | full | SD | △ | ✓ | M | meetingId | (meetingId,sessionKey) | — | reconnect/recurring (Phase 11 concept) |
| ScreenShareSession | share sessions | UUID | ✓ | full | SD | △ | ✓ | S | meetingSessionId; sharerId | — | — | |
| MeetingRecording | recordings | UUID | ✓ | full | SD | ✓ | ✓ | L | meetingSessionId | — | (tenantId,createdAt) | consent flag; storageRef; retention policy |
| Presence | presence | UUID | ✓ | full | SD | — | ✗ | S | userId; deviceId | (userId,deviceId) | (lastSeenAt) | cache-first (Redis); SQL is durable fallback |
| PresenceStatus | status vocabulary | UUID | — | full | PROTECT | — | ✓ | L | — | code | — | online/away/busy/invisible/offline |

## Notification (owner: Notifications)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Notification | notification root | UUID | ✓ | full | SD | △ | ✓ | S/M | templateId; sourceEventId | — | (tenantId,createdAt),(tenantId,type) | **no isRead on root** — read state on recipient (Phase 12 rule) |
| NotificationTemplate | versioned templates | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code,version) | — | |
| NotificationPreference | user preferences | UUID | ✓ | full | SD | — | ✓ | M | userId | (userId,notificationType,channel) | (userId) | quietHours |
| NotificationChannel | channel vocabulary | UUID | — | full | PROTECT | — | ✓ | L | — | code | — | inApp/email/sms/push/realtime |
| NotificationDelivery | delivery attempts | UUID | ✓ | app | APPEND | △ | ✗ | S/M | notificationId; recipientId; channel | — | (recipientId,attemptedAt),(status) | idempotent delivery |
| NotificationRecipient | recipient+read state | UUID | ✓ | full | SD | — | ✓ | S/M | notificationId; userId | (notificationId,userId) | (userId,readAt) | readAt lives here |

## Audit (owner: Audit)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AuditEvent | append-only audit fact | UUID | ✓ | app | APPEND | ✓(is record) | ✗ | L | actorId (SET_NULL semantics) | (eventId) | (tenantId,entityType,entityId,timestamp),(correlationId),(actorId,timestamp) | before/after JSON; no updates ever (spec §22); detail `09AuditModel.md` |

## Reporting (owner: Reporting/Analytics)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ReportDefinition | report spec | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | — | |
| ReportParameter | parameter defs | UUID | ✓ | full | SD | △ | ✓ | L | reportDefinitionId | (reportDefinitionId,key) | — | |
| ReportExecution | runs | UUID | ✓ | full | SD | △ | ✓ | M | reportDefinitionId; requestedBy | — | (tenantId,startedAt),(status) | |
| ReportSchedule | schedules | UUID | ✓ | full | SD | △ | ✓ | M | reportDefinitionId | (reportDefinitionId,cron) | (nextRunAt) | |
| ReportOutput | outputs | UUID | ✓ | full | SD | △ | ✓ | M | executionId | — | (executionId) | storageRef |
| ReportAccess | access grants | UUID | ✓ | full | SD | ✓ | ✓ | L | reportDefinitionId; subjectType/Id | (reportDefinitionId,subjectType,subjectId) | — | |

## Analytics (owner: Reporting/Analytics)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MetricDefinition | metric spec | UUID | ✓ | full | SD | △ | ✓ | L | — | (tenantId,code) | — | |
| MetricValue | metric points | UUID | ✓ | app | APPEND | — | ✗ | C | metricId | — | (metricId,period) | rebuildable projections |
| KpiDefinition | KPI spec | UUID | ✓ | full | SD | △ | ✓ | L | — | (tenantId,code) | — | |
| KpiValue | KPI points | UUID | ✓ | app | APPEND | — | ✗ | C | kpiId | — | (kpiId,period) | period d/w/m/q/y (spec §24) |
| Dashboard | dashboards | UUID | ✓ | full | SD | △ | ✓ | M | ownerId | (tenantId,code) | (ownerId) | |
| DashboardWidget | widgets | UUID | ✓ | full | CASCADE* | △ | ✓ | M | dashboardId | (dashboardId,position) | — | *meaningless without dashboard |
| AnalyticsSnapshot | projections | UUID | ✓ | app | APPEND | — | ✗ | C | scopeType/Id | — | (scopeType,scopeId,period) | §45 documented denormalization |

## AI (owner: AI)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AiProvider | provider registry | UUID | — | full | SD | ✓ | ✓ | L | — | code | — | adapter config JSON (§41) |
| AiModel | model registry | UUID | — | full | SD | ✓ | ✓ | L | providerId | (providerId,code) | — | |
| AiModelVersion | versions | UUID | — | full | SD | ✓ | ✓ | L | modelId | (modelId,version) | — | |
| AiAgent | software AI agent | UUID | ✓ | full | SD | ✓ | ✓ | M | modelVersionId | (tenantId,code) | (tenantId,isActive) | instructions versioned |
| AiAgentExecution | agent runs | UUID | ✓ | app | APPEND | △ | ✗ | M | agentId | — | (agentId,startedAt) | tokens/cost |
| AiRequest | inference request | UUID | ✓ | full | SD | ✓ | ✓ | M | promptVersionId; requestedBy | — | (tenantId,createdAt),(capability) | authorization recorded pre-inference (ADR-013) |
| AiResponse | response+classification | UUID | ✓ | full | SD | ✓ | ✓ | M | requestId | (requestId) | (resultClassification) | classification enum mandatory |
| AiConversation | chat session | UUID | ✓ | full | SD | △ | ✓ | S/M | userId | — | (userId,updatedAt) | |
| AiMessage | chat turns | UUID | ✓ | app | APPEND | △ | ✗ | S/M | conversationId | — | (conversationId,createdAt) | |
| AiKnowledgeSource | RAG source | UUID | ✓ | full | SD | △ | ✓ | L | — | (tenantId,code) | — | |
| AiKnowledgeDocument | ingested doc | UUID | ✓ | full | SD | △ | ✓ | L | sourceId; documentRef | (sourceId,documentRef) | (status) | permission-filtered retrieval (ADR-013) |
| AiEmbedding | vectors | UUID | ✓ | app | APPEND | — | ✗ | C | knowledgeDocumentId | — | (knowledgeDocumentId) | vector store ref; SQL keeps registry |
| AiRecommendation | recommendations | UUID | ✓ | full | SD | ✓ | ✓ | M | targetType/Id | — | (targetType,targetId,status) | classification; review workflow |
| AiPrediction | predictions | UUID | ✓ | full | SD | ✓ | ✓ | M | targetType/Id | — | (targetType,targetId,horizon) | confidence Decimal |
| AiInsight | insights | UUID | ✓ | full | SD | △ | ✓ | M | scopeType/Id | — | (scopeType,scopeId,generatedAt) | |

## Integration (owner: Integration)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Integration | registered integration | UUID | ✓ | full | SD | ✓ | ✓ | L | typeId | (tenantId,code) | (typeId) | |
| IntegrationType | type vocabulary | UUID | — | full | PROTECT | — | ✓ | L | — | code | — | rest/webhook/mqtt/opcua/wincc/sap… |
| IntegrationCredential | secret refs | UUID | ✓ | full | SD | ✓ | ✓ | M | integrationId | (integrationId,credentialType) | — | secretRef never inline (§49) |
| IntegrationEndpoint | endpoints | UUID | ✓ | full | SD | △ | ✓ | L | integrationId | (integrationId,direction) | — | |
| IntegrationConnection | connection state | UUID | ✓ | full | SD | △ | ✓ | M | integrationId | (integrationId) | (status) | |
| IntegrationMapping | payload mapping | UUID | ✓ | full | SD | ✓ | ✓ | L | integrationId | (integrationId,direction) | — | mapping JSON (§41) |
| IntegrationJob | sync job | UUID | ✓ | full | SD | ✓ | ✓ | L | integrationId | (integrationId,name) | (status) | |
| IntegrationExecution | job runs | UUID | ✓ | app | APPEND | △ | ✗ | M | jobId | — | (jobId,startedAt),(status) | |
| IntegrationEvent | in/out records | UUID | ✓ | full | SD | ✓ | ✓ | M | integrationId | (integrationId,idempotencyKey) | (direction,status) | idempotencyKey unique (spec §30/§18) |
| IntegrationError | errors | UUID | ✓ | app | APPEND | △ | ✗ | M | integrationId; executionId | — | (integrationId,occurredAt) | dead-letter review |

## WinCC — INDUSTRY EXTENSION (owner: Industry Pack — NOT Core, spec §28)

| Entity | Purpose | PK | T | B | Del | Aud | SD | Ret | FKs → | Unique | Extra indexes | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WinCcServer | server registry | UUID | ✓ | full | SD | ✓ | ✓ | L | — | (tenantId,code) | — | pack schema (ADR-014) |
| WinCcConnection | connections | UUID | ✓ | full | SD | △ | ✓ | M | serverId | (serverId) | (status) | |
| WinCcTag | tag registry | UUID | ✓ | full | SD | △ | ✓ | L | serverId | (tenantId,serverId,tagPath) | — | |
| WinCcTagValue | time-series | UUID | ✓ | app | APPEND | — | ✗ | C | tagId | — | (tagId,occurredAt) | high-volume, partition/purge |
| WinCcAlarm | alarms | UUID | ✓ | app | APPEND | △ | ✗ | C | serverId | — | (serverId,occurredAt) | |
| WinCcEvent | events | UUID | ✓ | app | APPEND | △ | ✗ | C | serverId | — | (serverId,occurredAt) | |
| WinCcSyncJob | sync jobs | UUID | ✓ | full | SD | ✓ | ✓ | M | serverId | (serverId) | (lastRunAt) | |

---

**Totals:** Platform 14 · Identity 10 · Organization 10 · Workforce 12 ·
Performance 4 · Project 10 · Task 12 · Asset 10 · Device 12 · Maintenance 9 ·
Document 10 · Workflow 11 · Communication 19 · Notification 6 · Audit 1 ·
Reporting 6 · Analytics 7 · AI 15 · Integration 10 = **188 Core** +
WinCC 7 = **195**.
