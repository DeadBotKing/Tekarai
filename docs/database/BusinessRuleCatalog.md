# BusinessRuleCatalog.md — Phase 05 business rules

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §15–§62, §58 format
**Format (§58):** ID · Name · Rule · Severity · Enforcement.
**Traceability (§62):** every rule lists Entities · Use cases · Services ·
API · Test bindings. Bindings marked `Phase 06+` are assigned when
implementation phases open; the rule itself is binding from approval of this
catalog. Requirement → Rule → Implementation → Test.
**Priorities (§60):** CRITICAL · HIGH · MEDIUM · LOW — tenant isolation,
authentication, authorization and audit rules are CRITICAL.
**Categories (§59):** TEN tenant · SEC security · PER permission · AUD audit ·
DAT data · BR business · WF workflow · AI ai · COM communication ·
INT integration · PERF performance.

---

## TEN — Tenant rules (§9–§11)

### BR-TEN-001 · Tenant Isolation
- **Rule:** A user may only access data belonging to a tenant they are an
  active member of; every repository/selector call must carry tenant context
  — `getProject(projectId, tenantId)`, never `getProject(projectId)` (§10).
- **Severity:** CRITICAL
- **Enforcement:** Application + Repository + Database integrity
- **Trace:** all tenant-owned entities · all use cases · all selectors ·
  API middleware · isolation test suite (per aggregate, DoD item). Error:
  `TENANT_ACCESS_DENIED`.

### BR-TEN-002 · Tenant Mode Declaration
- **Rule:** Every entity declares GLOBAL, TENANT_SCOPED or HYBRID (§9);
  TENANT_SCOPED rows always carry tenantId; HYBRID rows declare which part
  is global.
- **Severity:** HIGH · **Enforcement:** EntityCatalog review + schema review
- **Trace:** `EntityCatalog.md` · Phase 06 model review.

### BR-TEN-003 · Cross-Tenant FK Forbidden
- **Rule:** A foreign key between two tenant-owned tables must reference the
  same tenant; platform→tenant references only from global catalogues.
- **Severity:** CRITICAL · **Enforcement:** Repository validation + review
- **Trace:** `05RelationshipCatalog.md` (Phase 04) · Phase 06+ model tests.

### BR-TEN-004 · Tenant Code Globality
- **Rule:** `Tenant.code` is globally unique; `Tenant.name` is unique per
  scope only (resolution of Phase 04 §7).
- **Severity:** HIGH · **Enforcement:** Database UNIQUE
- **Trace:** Tenant · createTenant · TenantService · error
  `DUPLICATE_BUSINESS_CODE`.

### BR-TEN-005 · Scoped Business Uniqueness
- **Rule:** Business identifiers are unique per tenant:
  `UNIQUE(tenantId, employeeNumber)` / `(tenantId, code)` — never bare
  `UNIQUE(code)` except platform-global catalogues (§11).
- **Severity:** HIGH · **Enforcement:** Database UNIQUE
- **Trace:** all coded entities · create/update use cases · error
  `DUPLICATE_BUSINESS_CODE`.

## SEC — Security rules (§41, §28, §39)

### BR-SEC-001 · Authentication ≠ Authorization ≠ Tenant authorization
- **Rule:** The three questions — Who are you? What may you do? Which
  tenant's data? — are answered by separate mechanisms; no API relies on
  authentication alone (§41).
- **Severity:** CRITICAL
- **Enforcement:** Application layer (authorization) + API middleware
- **Trace:** every protected endpoint (Phase 06+ API tests) · error
  `PERMISSION_DENIED`.

### BR-SEC-002 · Server-Side Authorization
- **Rule:** Authorization is enforced server-side at the application
  boundary with object-level checks; client-supplied tenant/permission hints
  are never trusted (§44 six layers: authn → tenant → permission → role →
  scope → object-level).
- **Severity:** CRITICAL · **Enforcement:** Application
- **Trace:** all use cases · permission test matrix (Identity phase).

### BR-SEC-003 · No Secrets In Storage
- **Rule:** Credentials (integration, device, MFA) are stored as secret-manager
  references; plain-text secrets anywhere are forbidden (§39).
- **Severity:** CRITICAL · **Enforcement:** Review + scanner + repository
- **Trace:** IntegrationCredential · DeviceCredential · AuthenticationMethod.

### BR-SEC-004 · Password/Token Handling
- **Rule:** Only hashes of passwords/token values are stored; hashes never
  logged; sessions revocable and expiry-swept.
- **Severity:** CRITICAL · **Enforcement:** Identity services + DB
- **Trace:** User · Session (Identity phase).

## PER — Permission rules (§42–§44)

### BR-PER-001 · Action-Based Permissions
- **Rule:** Permissions are action-based codes — `project.view`,
  `project.create`, `project.update`, `project.delete`, `project.approve`
  (§42); free-text permissions forbidden.
- **Severity:** HIGH · **Enforcement:** Permission catalogue (seed data)
- **Trace:** Permission · RolePermission · UserPermission.

### BR-PER-002 · Role Scope
- **Rule:** Roles carry scope (GLOBAL · TENANT · ORGANIZATION · DEPARTMENT ·
  PROJECT); e.g. a Project-Manager role need not grant tenant-wide project
  access (§43).
- **Severity:** HIGH · **Enforcement:** Authorization evaluation
- **Trace:** UserRole.scopeType · access-control service (Identity phase).

### BR-PER-003 · Direct User Permissions
- **Rule:** Users get permissions via roles; direct user permissions exist
  for exceptions with explicit effect allow/deny (§42).
- **Severity:** MEDIUM · **Enforcement:** Authorization evaluation
- **Trace:** UserPermission.

### BR-PER-004 · Multi-Layer Access Decision
- **Rule:** Access = permission ∧ role ∧ scope ∧ object-level policy;
  `project.update` alone does not authorize updating every project (§44).
- **Severity:** CRITICAL · **Enforcement:** Application
- **Trace:** authorization service · API tests.

## AUD — Audit rules (§32–§33)

### BR-AUD-001 · Mandatory Audit Actions
- **Rule:** At minimum these actions are audited: CREATE · UPDATE · DELETE ·
  LOGIN · LOGOUT · PERMISSION_CHANGE · ROLE_CHANGE · EXPORT · DOWNLOAD ·
  APPROVAL · REJECTION (§32); every AuditEvent carries actor + timestamp.
- **Severity:** CRITICAL · **Enforcement:** Application (use-case writes)
- **Trace:** AuditEvent · all use cases.

### BR-AUD-002 · Audit Immutability
- **Rule:** Audit records cannot be updated or deleted by regular users —
  append-oriented only (§33).
- **Severity:** CRITICAL · **Enforcement:** Database (no UPDATE/DELETE grant)
  + review
- **Trace:** AuditEvent · operations runbook.

### BR-AUD-003 · Audit Before/After
- **Rule:** Sensitive changes record beforeState/afterState snapshots plus
  correlationId, enabling reconstruction (Who/What/When/Where/Why).
- **Severity:** HIGH · **Enforcement:** Application
- **Trace:** AuditEvent fields.

### BR-AUD-004 · Evaluation Score Change Audit
- **Rule:** Every EvaluationScore change (score/weight) is audited with
  actor + previous value; scores are editable only with audit (§ Phase 3/5).
- **Severity:** HIGH · **Enforcement:** Application + AUD-001
- **Trace:** EvaluationScore · updateEvaluationScore.

### BR-AUD-005 · Audit Columns Survive User Deletion
- **Rule:** createdBy/updatedBy/deletedBy use SET_NULL; deleting a user
  never destroys audit (Phase 04 §35).
- **Severity:** HIGH · **Enforcement:** Database FK policy
- **Trace:** base-entity columns.

## DAT — Data rules (§5–§8, §12–§14, §47–§55)

### BR-DAT-001 · camelCase Field Naming
- **Rule:** Database fields use camelCase (`createdAt`, `tenantId`);
  `created_at`, `TenantId`, `EmployeeID` are forbidden (§3).
- **Severity:** MEDIUM · **Enforcement:** schema review + Phase 06 model
  conventions
- **Trace:** FieldCatalog.

### BR-DAT-002 · Date Ordering
- **Rule:** Where a range exists, start ≤ end (cycles, employments,
  assignments, phases); CHECK constraints enforce simple cases (§55).
- **Severity:** MEDIUM · **Enforcement:** Domain + Database CHECK
- **Trace:** EvaluationCycle · Employment · ProjectPhase · dateRange VO.

### BR-DAT-003 · Task Deadline Validity
- **Rule:** `task.deadlineAt ≥ task.startDate`; subtask windows inside parent
  window.
- **Severity:** MEDIUM · **Enforcement:** Domain validation
- **Trace:** Task · createTask/updateTask · error `VALIDATION_FAILED`.

### BR-DAT-004 · Criteria Weights Sum
- **Rule:** Σ EvaluationCriteria.weight = 100% per cycle; weights are
  percentages 0–100 (§55 "complex rule stays in domain": sum checked in
  domain, per-row range in CHECK).
- **Severity:** HIGH · **Enforcement:** Domain service (cycle approval)
- **Trace:** EvaluationCriteria · performanceScoreCalculationService.

### BR-DAT-005 · Score Bounds
- **Rule:** EvaluationScore.score within its criteria's [0, maxScore];
  reviewer weight 0–100.
- **Severity:** HIGH · **Enforcement:** Domain + CHECK (0 ≤ score)
- **Trace:** EvaluationScore.

### BR-DAT-006 · Meaningful Defaults Only
- **Rule:** Defaults only where domain-logical (isActive=true, flag=false);
  a status default requires a domain rule (§7).
- **Severity:** LOW · **Enforcement:** FieldCatalog review
- **Trace:** FieldCatalog Default column.

### BR-DAT-007 · NULL Semantics
- **Rule:** Every nullable field documents what NULL means (§6);
  `deletedAt NULL = not deleted`; `description NULL = not yet provided`.
- **Severity:** MEDIUM · **Enforcement:** FieldCatalog review
- **Trace:** FieldCatalog Nullable column.

### BR-DAT-008 · Acyclic Graphs
- **Rule:** OrganizationUnit hierarchy, task/project dependency graphs,
  folder trees and parent chains must be acyclic; self-reference forbidden
  (A→B→C→A rejected) (§17, §21).
- **Severity:** HIGH · **Enforcement:** Domain validation (graph check)
- **Trace:** OrganizationUnit · TaskDependency · ProjectDependency ·
  DocumentFolder · error `CYCLIC_REFERENCE`.

### BR-DAT-009 · Money Precision
- **Rule:** Money = decimal(19,4) + ISO-4217 currency; float forbidden
  (§52); amounts ≥ 0 where business requires (CHECK §55).
- **Severity:** HIGH · **Enforcement:** Schema + Domain
- **Trace:** ProjectBudget · MaintenanceCost/Part · AssetValueHistory.

### BR-DAT-010 · UTC Storage
- **Rule:** All timestamps stored UTC; user/tenant timezone applied at
  presentation only (§51).
- **Severity:** HIGH · **Enforcement:** Infrastructure (Django USE_TZ)
- **Trace:** all datetime fields.

### BR-DAT-011 · Documented JSON Only
- **Rule:** JSON columns only for metadata / provider config / extension
  data / dynamic configuration; every JSON column's purpose is documented in
  FieldCatalog (§4, Phase 04 §41); core business data stays structured.
- **Severity:** MEDIUM · **Enforcement:** FieldCatalog review
- **Trace:** every `json` field row.

### BR-DAT-012 · Controlled Vocabulary Status
- **Rule:** Status/type fields are enums or reference entities; values
  outside the allowed set are rejected (§8, §13).
- **Severity:** HIGH · **Enforcement:** Domain + DB (FK to vocab)
- **Trace:** StateMachineCatalog · 07ConstraintCatalog §2 · error
  `INVALID_STATE_TRANSITION` / `VALIDATION_FAILED`.

### BR-DAT-013 · Optimistic Concurrency
- **Rule:** Sensitive entities (versioned in FieldCatalog) use a version
  column; a stale write is rejected — a user may not silently overwrite
  another's change (§50).
- **Severity:** HIGH · **Enforcement:** Application + row filter
- **Trace:** versioned entities · error `CONCURRENCY_CONFLICT`.

### BR-DAT-014 · Four Validation Layers
- **Rule:** Validation runs at API, Application, Domain and Database layers;
  no layer fully replaces another (§53–§55); simple scalar rules may be
  CHECKs, complex rules stay in domain/application.
- **Severity:** HIGH · **Enforcement:** Architecture review + tests
- **Trace:** all use cases (Phase 06+).

## BR — Business rules (§15–§26)

### BR-USR-001 · User ≠ Employee
- **Rule:** User (identity) and Employee (employment) are independent; an
  employee may lack a user account; link is optional 1:1 (§15).
- **Severity:** HIGH · **Enforcement:** Domain model
- **Trace:** User · Employee.

### BR-WF-001 · Employee Capability Set
- **Rule:** An Employee can hold organization placement, position, manager,
  assignments (temporal), employment history, skills, certifications and
  evaluations (§16).
- **Severity:** MEDIUM · **Enforcement:** Domain design
- **Trace:** Workforce aggregates.

### BR-WF-002 · No Self-Management
- **Rule:** EmployeeManager.managerId ≠ employeeId.
- **Severity:** MEDIUM · **Enforcement:** Domain + CHECK
- **Trace:** EmployeeManager.

### BR-WF-003 · Assignment History Preserved
- **Rule:** Changing department/assignment never deletes prior assignment
  rows; history is closed with endDate (§16, Phase 04 §36).
- **Severity:** HIGH · **Enforcement:** Domain (temporal close, not delete)
- **Trace:** EmployeeAssignment.

### BR-ORG-001 · Acyclic Organization Hierarchy
- **Rule:** An OrganizationUnit must not be its own ancestor (§17) —
  see BR-DAT-008 (listed there); hierarchy changes recorded temporally.
- **Severity:** HIGH · **Enforcement:** Domain graph check
- **Trace:** OrganizationUnit · OrganizationHierarchy.

### BR-PRJ-001 · Project Owner Rule
- **Rule:** Projects require an owner except in explicitly allowed statuses
  (DRAFT); after COMPLETION, changes require special permission (§18).
- **Severity:** HIGH · **Enforcement:** Domain + StateMachine:Project
- **Trace:** Project · error `PROJECT_ALREADY_COMPLETED`.

### BR-PRJ-002 · One Active Membership
- **Rule:** One ACTIVE membership record per person per project — the
  logical constraint `ONE ACTIVE MEMBERSHIP PER PERSON PER PROJECT` (§19);
  re-joining creates a new row after leftAt.
- **Severity:** HIGH · **Enforcement:** Domain + filtered unique index
- **Trace:** ProjectMember · error `DUPLICATE_ACTIVE_MEMBERSHIP`.

### BR-TSK-001 · Project-Optional Tasks
- **Rule:** A task may belong to a project or stand alone; tasks remain
  usable independently of project internals (§20).
- **Severity:** MEDIUM · **Enforcement:** Domain (nullable projectId)
- **Trace:** Task.

### BR-TSK-002 · Task Dependency Integrity
- **Rule:** A task cannot depend on itself; dependency cycles are rejected
  (§21).
- **Severity:** HIGH · **Enforcement:** Domain graph check
- **Trace:** TaskDependency · error `CYCLIC_REFERENCE`.

### BR-TSK-003 · Comment Revisions
- **Rule:** Editing a comment appends a revision; original content is not
  silently lost (§27 pattern generalized to tasks).
- **Severity:** LOW · **Enforcement:** Application
- **Trace:** TaskComment.

### BR-DOC-001 · Immutable Versions
- **Rule:** Document versions are never overwritten; important changes
  create a new version; deleted versions never destroy history (§22–§23).
- **Severity:** CRITICAL · **Enforcement:** Domain + no-update policy
- **Trace:** DocumentVersion · error `DOCUMENT_VERSION_IMMUTABLE`.

### BR-DOC-002 · Current Version Pointer
- **Rule:** `Document.currentVersionNumber` always identifies the latest
  version; it is updated atomically with version creation (§23).
- **Severity:** HIGH · **Enforcement:** Domain transaction
- **Trace:** Document · DocumentVersion.

### BR-AST-001 · Asset History Preserved
- **Rule:** Asset assignment/ownership changes keep history; changing owner
  never deletes the previous owner row (§24).
- **Severity:** HIGH · **Enforcement:** Temporal rows
- **Trace:** AssetAssignment · AssetOwnership.

### BR-DEV-001 · Offline By Policy
- **Rule:** Device online/offline is determined by policy
  (lastSeenAt + offlineAfterSeconds), never a bare `isOnline` flag (§25).
- **Severity:** MEDIUM · **Enforcement:** Domain service
- **Trace:** Device · DeviceHeartbeat.

### BR-DEV-002 · Auditable Registration
- **Rule:** Device registration and approval are audited events (§25).
- **Severity:** MEDIUM · **Enforcement:** AUD-001
- **Trace:** DeviceRegistration.

### BR-MNT-001 · Completion Requires Outcome
- **Rule:** A completed work order requires an outcome note; completed work
  orders change only with special permission (§26).
- **Severity:** HIGH · **Enforcement:** Domain + StateMachine:Maintenance
- **Trace:** MaintenanceWorkOrder · error `WORK_ORDER_COMPLETED`.

## COM — Communication rules (§27–§30)

### BR-COM-001 · Conversation Creator
- **Rule:** Every conversation has at least one owner/creator (§27).
- **Severity:** HIGH · **Enforcement:** Domain
- **Trace:** Conversation.

### BR-COM-002 · Private Membership Guard
- **Rule:** A user cannot join a private conversation/channel without
  permission (invite or member role) (§27).
- **Severity:** HIGH · **Enforcement:** Application authorization
- **Trace:** ConversationMember · ChannelMember · error
  `CONVERSATION_ACCESS_DENIED`.

### BR-COM-003 · Message Edit/Delete Policy
- **Rule:** Messages are immutable after send or editable under an edit
  policy; edits are audited; delete is soft (tombstone) per policy (§27).
- **Severity:** HIGH · **Enforcement:** Domain
- **Trace:** Message.

### BR-COM-004 · Call Metadata Only
- **Rule:** Voice/group calls never store audio streams in the database —
  metadata only; media transport is WebRTC (§28).
- **Severity:** CRITICAL · **Enforcement:** Architecture boundary
- **Trace:** VoiceCall · GroupCall · VoiceCallParticipant.

### BR-COM-005 · Recording Storage
- **Rule:** Meeting recordings reference object storage; binary video never
  stored in the database (§29).
- **Severity:** HIGH · **Enforcement:** StoragePort
- **Trace:** MeetingRecording.

### BR-COM-006 · Recording Consent
- **Rule:** A recording requires captured consent flag before publish.
- **Severity:** HIGH · **Enforcement:** Domain
- **Trace:** MeetingRecording.consentCaptured · error
  `RECORDING_CONSENT_REQUIRED`.

### BR-COM-007 · Presence Truth Split
- **Rule:** Realtime presence truth = Redis/Channels; database persists
  last-known state only — DB is never the sole source for live presence
  (§30). Presence vocabulary: online · away · busy · doNotDisturb · offline
  (canonical §30 set; `invisible` is a Phase-11 extension decision — TBD).
- **Severity:** MEDIUM · **Enforcement:** Architecture
- **Trace:** Presence.

### BR-COM-008 · Notification Read State Placement
- **Rule:** Read state lives on NotificationRecipient (and delivery READ
  status); an `isRead`/`readAt` column on Notification root is FORBIDDEN
  (multi-recipient rule).
- **Severity:** HIGH · **Enforcement:** Schema review
- **Trace:** Notification · NotificationRecipient · NotificationDelivery.

## NOT (notification) — (§31, §36)

### BR-NOT-001 · Event-Driven Creation
- **Rule:** Notifications are never created inside domain cores; a domain
  event (e.g. taskCompleted) triggers the notification handler (§36).
- **Severity:** HIGH · **Enforcement:** Architecture boundary
- **Trace:** Notification · event handlers.

### BR-NOT-002 · Retryable Delivery
- **Rule:** Delivery failure is retryable with status pending · sent ·
  delivered · failed · read; failures never erase the notification (§31).
- **Severity:** HIGH · **Enforcement:** Delivery service
- **Trace:** NotificationDelivery.

## WF — Workflow rules (§34–§35)

### BR-WF2-001 · Generic Engine
- **Rule:** Workflow engine stays generic — no domain-specific hard-coding;
  document/project/purchase/leave/maintenance approvals all use the same
  engine (§34).
- **Severity:** CRITICAL · **Enforcement:** Architecture review
- **Trace:** Workflow aggregates.

### BR-WF2-002 · Instance/Definition Independence
- **Rule:** A workflow instance keeps state independent of its definition;
  editing/retiring a definition never mutates running instances (§34).
- **Severity:** HIGH · **Enforcement:** Domain
- **Trace:** WorkflowInstance · WorkflowDefinition.

### BR-WF2-003 · Versioned Definitions
- **Rule:** Workflow definitions are versioned; versions are never
  overwritten (§34).
- **Severity:** HIGH · **Enforcement:** Unique (workflowId, versionNumber)
- **Trace:** WorkflowVersion.

### BR-WF2-004 · Approval Completeness
- **Rule:** Every approval records actor, timestamp, decision, comment;
  REJECTED requires a reason unless a business rule explicitly waives it
  (§35).
- **Severity:** HIGH · **Enforcement:** Domain
- **Trace:** WorkflowApproval · error `REJECTION_REASON_REQUIRED`.

## AI — AI rules (§37–§38)

### BR-AI-001 · Output Classification
- **Rule:** AI output is never stored as system fact; every result carries
  classification advisory · draft · automated · authoritative; authoritative
  application requires explicit business rules + authorization (§37).
- **Severity:** CRITICAL · **Enforcement:** Application + schema
- **Trace:** AiResponse.resultClassification · AiRecommendation.

### BR-AI-002 · Traceable Decisions
- **Rule:** Important AI decisions record model, model version, provider,
  prompt/context reference, input reference, output, confidence, timestamp
  (§37/§38 — explainability).
- **Severity:** HIGH · **Enforcement:** Schema + service
- **Trace:** AiRequest · AiResponse.

### BR-AI-003 · No Direct Mutation
- **Rule:** AI never writes business tables directly; changes flow back via
  application commands after review (Phase 03 §19).
- **Severity:** CRITICAL · **Enforcement:** Architecture boundary
- **Trace:** AI context · recommendation review use cases.

## INT — Integration rules (§39–§40)

### BR-INT-001 · Credential Safety
- **Rule:** Integration credentials are never stored in plain text — secret
  references only (§39); see BR-SEC-003 (listed there for storage-wide
  scope).
- **Severity:** CRITICAL · **Enforcement:** Secret manager
- **Trace:** IntegrationCredential.

### BR-INT-002 · Traceable Executions
- **Rule:** Integration executions support started · success · failed ·
  retrying; errors are traceable to execution + payload (§39).
- **Severity:** HIGH · **Enforcement:** Append-only streams
- **Trace:** IntegrationExecution · IntegrationError.

### BR-INT-003 · Idempotent Inbound
- **Rule:** Duplicate delivery of an external event must not create
  duplicate business state — idempotencyKey unique per integration.
- **Severity:** CRITICAL · **Enforcement:** Database UNIQUE + handler
- **Trace:** IntegrationEvent · error `DUPLICATE_INTEGRATION_EVENT`.

### BR-INT-004 · File Metadata Contract
- **Rule:** File records keep name, size, mimeType, checksum, storage
  provider, storage key; binary lives in object storage; checksum detects
  change/duplicate (§40).
- **Severity:** MEDIUM · **Enforcement:** Attachment schema
- **Trace:** Attachment · DocumentVersion · MeetingRecording.

## PERF — Performance rules

### BR-PERF-001 · No Unjustified Index
- **Rule:** An index without a documented use case (IndexCatalog entry) is
  an architecture violation (Phase 04 §33; §56).
- **Severity:** MEDIUM · **Enforcement:** IndexCatalog review
- **Trace:** `IndexCatalog.md`.

### BR-PERF-002 · Cursor Pagination For Streams
- **Rule:** Large append-only streams (messages, telemetry, audit) use
  cursor pagination on leading (entity, occurredAt/createdAt) indexes —
  offset pagination is forbidden for them.
- **Severity:** MEDIUM · **Enforcement:** Selector review
- **Trace:** Message · DeviceTelemetry · AuditEvent queries.

---

## Rule inventory summary

| Category | Count | Critical |
|---|---|---|
| TEN | 5 | 2 |
| SEC | 4 | 4 |
| PER | 4 | 1 |
| AUD | 5 | 2 |
| DAT | 14 | 0 (all HIGH≤) |
| BR (business) | 16 | 1 |
| COM | 8 | 1 |
| NOT | 2 | 0 |
| WF | 4 | 1 |
| AI | 3 | 2 |
| INT | 4 | 1 |
| PERF | 2 | 0 |
| **Total** | **71** | **15** |
