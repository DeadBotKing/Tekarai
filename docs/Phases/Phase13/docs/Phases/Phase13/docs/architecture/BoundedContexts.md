# Tekarai — Bounded Contexts

**Status:** Authoritative (Phase 03 — Domain Architecture)
**Specification:** `docs/Phases/Phase3.md` §4 (Contexts 01–20)
**Aggregates per context:** `AggregateCatalog.md` · **events:** `DomainEvents.md`
**Classification:** `DomainMap.md` §2

---

## 1. Context ↔ Module Map (spec §13)

| # | Bounded Context | Module (`apps/`) | Class |
|---|---|---|---|
| 01 | Identity | `identity` | Generic |
| 02 | Tenancy | `tenancy` | Generic |
| 03 | Organization | `organization` | Core |
| 04 | Workforce / HR | `workforce` | Core |
| 05 | Performance | `performance` | Core |
| 06 | Project | `projects` | Core |
| 07 | Task / Work Management | `tasks` | Core |
| 08 | Asset | `assets` | Supporting |
| 09 | Device / OT | `devices` | Supporting |
| 10 | Maintenance | `maintenance` | Supporting |
| 11 | Document | `documents` | Supporting |
| 12 | Workflow | `workflow` | Core |
| 13 | Communication | `communication` | Supporting |
| 14 | Notification | `notifications` | Generic |
| 15 | Audit | `audit` | Generic |
| 16 | Reporting / Analytics | `analytics` | Supporting |
| 17 | AI / Intelligence | `ai` | Core |
| 18 | Integration | `integrations` | Generic |
| 19 | Configuration | `configuration` | Generic |
| 20 | Platform Core | `platform` | Generic (foundation) |

> Phase 02 mapped Tenancy inside the coarse "Organization" module row; Phase
> 03 refines it into its own context (spec §4 Context 02). This is the
> designed refinement announced by Phase 02, not a contradiction.

---

## 2. Context Details

### CONTEXT 01 — IDENTITY (module `identity`)
**Responsible for:** User · Authentication · Credentials · Sessions · Roles ·
Permissions · Access Policies · Security Identity.
**Owns:** who the principal is and how they authenticate/authorize.
**Must NOT own:** Employee (that is Workforce). `Identity.User ≠
Workforce.Employee` — a user may exist without employment.
**Boundary notes:** authorization evaluates user/role/permission/policy/
resource/tenant/org-scope (never `is_superuser` alone). Service accounts and
API keys are identity principals.

### CONTEXT 02 — TENANCY (module `tenancy`)
**Responsible for:** Tenant · Tenant Configuration · Tenant Lifecycle ·
Tenant Isolation · Tenant Membership.
**Owns:** tenants, tenant lifecycle/state, tenant-level configuration scope,
user↔tenant memberships (with status per membership).
**Must NOT own:** organization structure below tenant (Organization context)
or identity credentials (Identity).
**Boundary notes:** tenant is the top isolation boundary (ADR-012); all
tenant-aware aggregates reference the tenant id.

### CONTEXT 03 — ORGANIZATION (module `organization`)
**Responsible for:** Organization · Legal Entity · Business Unit ·
Department · Division · Team · Organizational Hierarchy · Positions.
**Owns:** the organizational structure inside a tenant and organizational
positions.
**Must NOT own:** personal/employment data of employees (spec: "Organization
نباید مسئول اطلاعات شخصی Employee باشد") — Workforce owns person records;
positions are *owned* here, position *assignments* belong to Workforce.

### CONTEXT 04 — WORKFORCE / HR (module `workforce`)
**Responsible for:** Employee · Employment · Contract · Job · Position
Assignment · Attendance · Leave · Skills · Employee Lifecycle.
**Owns:** the person/employment record and its lifecycle.
**Must NOT own:** authentication identity (references `userId`, never
stores credentials).
**Relationship:** `User = Identity`, `Employee = Workforce person/employment
record` — related by id, never merged.

### CONTEXT 05 — PERFORMANCE (module `performance`)
**Responsible for:** Performance Cycle · KPI · Evaluation · Evaluation
Criteria · Reviewer · Reviewer Weight · Score · Performance Result ·
Performance History.
**Rules (spec §4/05):** multiple managers may evaluate one employee; each
evaluator may carry a weight; scores are editable; **every score change is
audited**.
**Must NOT own:** employee master data (Workforce) or analytical projections
(Reporting).

### CONTEXT 06 — PROJECT (module `projects`)
**Responsible for:** Project · Project Member · Project Phase · Milestone ·
Budget · Status · Risk.
**Must NOT own:** task implementation (Task is an independent context);
projects are referenced by tasks via contract (spec §4/06).

### CONTEXT 07 — TASK / WORK MANAGEMENT (module `tasks`)
**Responsible for:** Task · Subtask · Assignment · Priority · Status ·
Deadline · Dependency · Checklist · Task Comment · Task Activity.
**Boundary:** a task may belong to a project, but the Task domain stays
independent (spec §4/07) — project is a reference id, never internal access.

### CONTEXT 08 — ASSET (module `assets`)
**Responsible for:** Asset · Asset Type · Asset Category · Ownership ·
Assignment · Lifecycle · Asset Status.
**Owns:** the enterprise asset lifecycle.

### CONTEXT 09 — DEVICE / OT (module `devices`)
**Responsible for:** Device · Device Type · Device Registration · Device
Health · Telemetry · Device Connection · Industrial Connector.
**Boundary:** industrial protocols (WinCC, OPC-UA) never enter this context's
core — connector implementations live in the Integration context / Industry
Packs (spec §4/09, §23).

### CONTEXT 10 — MAINTENANCE (module `maintenance`)
**Responsible for:** Maintenance Plan · Preventive · Corrective · Work
Order · Schedule · History.
**Integrates with:** Asset and Device contexts (via contracts/events) —
never by writing their tables.

### CONTEXT 11 — DOCUMENT (module `documents`)
**Responsible for:** Document · Document Version · Folder · Metadata ·
Document Permission · Document Lifecycle · Document Relation.
**Boundary:** binary content goes through the storage port
(`StorageArchitecture.md`); metadata/lifecycle/permissions are owned here.

### CONTEXT 12 — WORKFLOW (module `workflow`)
**Responsible for:** Workflow Definition · Version · Instance · Step ·
Approval · Approval Assignment · Transition.
**Boundary:** workflow stays **generic** — never hard-coded to one business
domain (spec §4/12); triggering domains integrate via contracts/events
(Phase 03 resolution, `DomainArchitecture.md` §12).

### CONTEXT 13 — COMMUNICATION (module `communication`)
**Responsible for:** Direct Chat · Group Chat · Channel · Message ·
Conversation · Participant · Presence · Call · Meeting — and voice calls,
group voice, video meetings, screen sharing, recording are managed in this
context (spec §4/13).
**Boundary:** media transport never flows through Django (ADR/Phase 02);
canonical resolution of the Communication spec quadruple happens before this
context is implemented (docs/ANALYSIS.md).

### CONTEXT 14 — NOTIFICATION (module `notifications`)
**Responsible for:** Notification · Template · Delivery · Channel · User
Preference · Notification History.
**Style:** event-driven — `taskAssigned → event bus → notification handler`
(spec §4/14); delivery channels are providers behind ports
(`ExtensionArchitecture.md`).

### CONTEXT 15 — AUDIT (module `audit`)
**Responsible for:** Audit Event · Actor · Action · Entity · Previous State ·
New State · Timestamp · Correlation ID · IP/Client Metadata.
**Rules:** **append-only**; never mixed with business CRUD (spec §4/15);
audit ≠ logging (ADR-016).

### CONTEXT 16 — REPORTING / ANALYTICS (module `analytics`)
**Responsible for:** Reports · Report Definitions · Dashboards · Metrics ·
KPIs (analytical) · Aggregations · Analytical Views.
**Boundary:** never owns transactional data — it receives data from domains
via events/projections (spec §4/16). Performance *evaluation* data is owned
by Context 05; analytical views over it live here.

### CONTEXT 17 — AI / INTELLIGENCE (module `ai`)
**Responsible for:** AI Model Registry · Provider · Job · Prediction ·
Recommendation · Analysis · Prompt · AI Knowledge · Knowledge Graph ·
AI Feedback.
**Boundary:** AI is a **consumer** of domain information and never owns
business truth (spec §4/17, §19; ADR-013); authoritative changes flow back
only through application commands after review.

### CONTEXT 18 — INTEGRATION (module `integrations`)
**Responsible for:** Integration · Connector · External System · API
Credential · Webhook · Sync Job · Integration Event · Mapping.
**Boundary:** ALL external traffic passes this boundary — WinCC, ERP, MES,
Email, SMS, External HR, External AI, External Storage (spec §4/18,
ADR-015).

### CONTEXT 19 — CONFIGURATION (module `configuration`)
**Responsible for:** System Configuration · Tenant Configuration · Feature
Flags · Policies · Runtime Settings.
**Purpose:** prevent hard-coding (spec §4/19); complements environment-based
settings (ADR-009) with runtime, tenant-scoped configuration.

### CONTEXT 20 — PLATFORM CORE (module `platform`)
**Responsible for:** Domain primitives · Base abstractions · Domain Event
infrastructure · Result · Error · Identifier · Clock · Correlation · Tenant
Context · Security Context.
**Must NOT own:** any business domain logic (spec §4/20). It is the shared
kernel all other contexts may depend on — and nothing else depends upward.

---

## 3. Ownership Guardrails (per spec §4 "must not" statements)

| Guardrail | Statement |
|---|---|
| Identity ⇏ Employee | Identity never owns employment; Workforce never owns credentials |
| Organization ⇏ personal data | Structure & positions only |
| Project ⇏ Task internals | Reference by contract; Tasks stay independent |
| Core ⇏ industry protocols | WinCC/OPC-UA live in Integration / Industry Packs |
| Workflow = generic | No domain-specific hard-coding |
| Analytics ⇏ transactional data | Projections/read models only |
| AI ⇏ business truth | Consumer; changes flow back via application commands |
| Audit = append-only | Never edited, never mixed with CRUD |
| Platform Core ⇏ business logic | Primitives and abstractions only |
