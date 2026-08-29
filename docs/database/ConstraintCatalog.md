# ConstraintCatalog.md — Phase 05 constraints

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §11–§12,
§55, §67; deepens Phase 04 `07ConstraintCatalog.md` (ERD level) to
field/rule level.
**Laws:** UNIQUE is tenant-scoped unless the entity is GLOBAL (§11); CHECK
only for simple scalar rules (§55) — complex rules stay in domain (§54);
technical PK is uuid surrogate, business code is separate (§12); FK delete
policies follow the Phase 04 Delete Behavior Register (CASCADE only for the
4 approved cases + soft delete default).

---

## 1 · Naming conventions

| Kind | Pattern | Example |
|---|---|---|
| Primary key | `PK_<Table>` | `PK_Project` |
| Foreign key | `FK_<Table>_<Ref>` | `FK_Task_Project` |
| Unique (tenant-scoped) | `UQ_<Table>_<columns>` | `UQ_Employee_tenant_code` |
| Unique (global) | `UQG_<Table>_<columns>` | `UQG_Tenant_code` |
| Filtered unique | `UQF_<Table>_<rule>` | `UQF_ProjectMember_active` |
| Check | `CK_<Table>_<rule>` | `CK_ProjectBudget_amount_nonneg` |

## 2 · Primary keys (§12)

- Every table: `id uuid DEFAULT gen_random_uuid()` surrogate PK.
- Business codes (`code`, `employeeNumber`, …) are **never** the PK; they are
  UNIQUE per scope (§11/§12) — see §4.
- Link tables (UserRole, RolePermission, ConversationMember, …) also use
  surrogate uuid + scoped unique composite (no裸 composite PKs) — keeps FK
  targets stable and audit columns attachable.

## 3 · Foreign keys and delete behaviors (§57 dict; Phase 04 register)

Default policy: **RESTRICT + soft delete** (deletedAt). The complete
register lives in Phase 04 `05RelationshipCatalog.md`; the authoritative
summary:

| Policy | Meaning | Cases |
|---|---|---|
| CASCADE | Hard children removal with parent | (1) Tenant → tenant-owned data (tenant purge, controlled op only) · (2) Conversation → Messages (conversation purge) · (3) Document → DocumentVersion (document purge) · (4) WorkflowDefinition → WorkflowVersion (definition purge) |
| SET_NULL | History survives, link cleared | audit columns (createdBy/updatedBy/deletedBy → User) · Task.projectId (standalone tasks, BR-TSK-001) · all *_Id references into User |
| RESTRICT | Delete blocked while children exist | all remaining relations (default) |
| SOFT DELETE | deletedAt set; row retained | all base entities (§71 retention) |

**Tenant-column rule:** every FK between two TENANT_SCOPED tables implicitly
requires equal tenantId (BR-TEN-003); enforced by composite FK
`(tenantId, parentId) → (tenantId, id)` where the engine supports it, else by
repository validation + review tests.

## 4 · Unique constraints (tenant-scoped by default — §11)

| Constraint | Table · Columns | Scope | Rule |
|---|---|---|---|
| `UQG_Tenant_code` | Tenant(code) | GLOBAL | BR-TEN-004 |
| `UQ_Tenant_name` | Tenant(name) | GLOBAL (platform registry) | BR-TEN-004 note |
| `UQ_User_email` | User(tenantId, email) | TENANT | identity per tenant |
| `UQ_User_username` | User(tenantId, username) | TENANT | login handle |
| `UQ_Employee_code` | Employee(tenantId, employeeNumber) | TENANT | BR-TEN-005 |
| `UQ_OrganizationUnit_path` | OrganizationUnit(tenantId, code) | TENANT | stable unit code |
| `UQ_Project_code` | Project(tenantId, code) | TENANT | BR-TEN-005 |
| `UQF_ProjectMember_active` | ProjectMember(tenantId, projectId, userId) WHERE leftAt IS NULL | TENANT | BR-PRJ-002 one active membership |
| `UQ_Task_code` | Task(tenantId, projectId, code) | TENANT | per-project task code (NULL project → repository check) |
| `UQ_Document_code` | Document(tenantId, code) | TENANT | BR-TEN-005 |
| `UQF_DocumentVersion_no` | DocumentVersion(tenantId, documentId, versionNumber) | TENANT | BR-DOC-001/002 |
| `UQ_Asset_code` | Asset(tenantId, code) | TENANT | BR-TEN-005 |
| `UQ_Device_serial` | Device(tenantId, serialNumber) | TENANT | device identity |
| `UQ_MaintenanceWorkOrder_code` | MaintenanceWorkOrder(tenantId, code) | TENANT | BR-TEN-005 |
| `UQ_WorkflowDefinition_key` | WorkflowDefinition(tenantId, definitionKey) | TENANT | engine key |
| `UQF_WorkflowVersion_no` | WorkflowVersion(tenantId, workflowId, versionNumber) | TENANT | BR-WF2-003 |
| `UQ_NotificationRecipient_once` | NotificationRecipient(tenantId, notificationId, userId) | TENANT | no double-addressee |
| `UQ_Role_code` | Role(tenantId, code) | TENANT | tenant roles |
| `UQG_SystemRole_code` | SystemRole(code) — if platform roles materialize | GLOBAL | platform catalogue |
| `UQ_SystemSetting_key` | SystemSetting(scope, key) | GLOBAL | §SystemSetting row |
| `UQ_LookupType_key` | LookupType(tenantId, key) | TENANT | lookup family |
| `UQ_LookupValue_code` | LookupValue(tenantId, typeId, code) | TENANT | vocab per family |
| `UQ_EvaluationCycle_name` | EvaluationCycle(tenantId, name) | TENANT | cycle naming |
| `UQ_EmployeeSkill_once` | EmployeeSkill(tenantId, employeeId, skillId) | TENANT | no dup skill row |
| `UQ_EmployeeCertification_ref` | EmployeeCertification(tenantId, employeeId, certificationId, certificateRef) | TENANT | cert instance |
| `UQ_Conversation_slug` | Conversation(tenantId, slug) | TENANT | link slug |
| `UQF_ConversationMember_active` | ConversationMember(tenantId, conversationId, userId) WHERE leftAt IS NULL | TENANT | rejoin = new row |
| `UQ_Attachment_checksum_dedup` | Attachment(tenantId, checksum) — dedup candidate, policy-gated | TENANT | BR-INT-004 |
| `UQ_IntegrationEvent_idem` | IntegrationEvent(integrationId, idempotencyKey) | TENANT | BR-INT-003 |
| `UQ_AiRequest_trace` | AiRequest(tenantId, requestId) | TENANT | provider trace id |
| `UQ_UserPermission_once` | UserPermission(tenantId, userId, permissionId, scopeType) | TENANT | no dup grant |
| `UQ_RolePermission_once` | RolePermission(tenantId, roleId, permissionId) | TENANT | no dup grant |
| `UQ_UserRole_once` | UserRole(tenantId, userId, roleId, scopeType) | TENANT | no dup grant |
| `UQ_Webhook_endpoint` | Webhook(tenantId, endpointId) | TENANT | one registration per endpoint |

Filtered (`UQF`) entries require partial-index support (PostgreSQL native;
SQL Server filtered index; MySQL 8 — repository-level enforcement +
integration test, engine notes §7).

## 5 · CHECK constraints (simple scalar only — §55)

| Check | Table · Expression | Rule |
|---|---|---|
| `CK_ProjectBudget_amount_nonneg` | ProjectBudget.amount ≥ 0 | BR-DAT-009 |
| `CK_MaintenanceCost_amount_nonneg` | MaintenanceCost.amount ≥ 0 | BR-DAT-009 |
| `CK_MaintenancePart_qty_nonneg` | MaintenancePart.quantity ≥ 0 | BR-DAT-009 |
| `CK_EvaluationScore_nonneg` | EvaluationScore.score ≥ 0 | BR-DAT-005 |
| `CK_EvaluationCriteria_weight_range` | EvaluationCriteria.weight BETWEEN 0 AND 100 | BR-DAT-004 |
| `CK_EvaluationCycle_dates` | EvaluationCycle.startDate ≤ endDate | BR-DAT-002 |
| `CK_Employment_dates` | Employment.startDate ≤ endDate (NULL end allowed) | BR-DAT-002 |
| `CK_EmployeeAssignment_dates` | EmployeeAssignment.startDate ≤ endDate | BR-DAT-002 |
| `CK_Task_dates` | Task.deadlineAt IS NULL OR Task.startDate IS NULL OR deadlineAt ≥ startDate | BR-DAT-003 |
| `CK_Tenant_slug_fmt` | Tenant.code ~ '^[a-z0-9-]{2,64}$' | code grammar |
| `CK_Json_metadata_is_object` | JsonField checks NOT enforced by CHECK — JSON contract validated at application layer (§53) | BR-DAT-011 |

**Explicitly NOT CHECKs** (complex → domain layer, §54):
Σ criteria weights = 100 (BR-DAT-004); graph acyclicity (BR-DAT-008);
state-machine transition legality (BR-DAT-012); multi-row invariants
(BR-PRJ-002 active membership); cross-entity temporal containment
(subtask-in-parent).

## 6 · Controlled vocabularies (§8, §13)

Two implementation forms, chosen per entity:

1. **Enum columns** for closed, code-owned sets — all `enum(...)` types in
   `FieldCatalog.md` (e.g. tenantStatus, projectStatus, callStatus,
   integrationExecutionStatus). Values live in StateMachineCatalog /
   FieldCatalog; adding a value = design decision + migration + catalog
   update.
2. **Vocabulary entities** for tenant-extensible sets — the 20+ vocab tables
   (TaskStatus, TaskPriority, DocumentType, AssetCategory, SkillCategory,
   Certification, Location, …) with `code` unique per tenant+family and
   sortOrder; FK from business tables guarantees closure (BR-DAT-012).

Free-text status/type fields are forbidden (§13) —
`VAL_ENUM_VALUE_FORBIDDEN`.

## 7 · Engine notes (from Phase 04 §6, unchanged)

| Feature | PostgreSQL | SQL Server | MySQL 8 |
|---|---|---|---|
| Partial/filtered unique | native WHERE | filtered index | ✗ → repository + test |
| CHECK | native | native | 8.0.16+ native |
| JSON contract | validated in app layer (BR-DAT-011) | same | same |
| FK ON DELETE SET NULL | native | native | native |
| Case-insensitive unique (email/username) | citext/LOWER() index | CI collation | CI collation |

## 8 · Governance

- Adding/changing a constraint = entry here + FieldCatalog row updated +
  migration file (Phase 06+) + test asserting the violation error code.
- Every constraint names its rule ID (traceability §62).
