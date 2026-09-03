# Tekarai — Aggregate Catalog

**Status:** Authoritative (Phase 03 — Domain Architecture)
**Specification:** `docs/Phases/Phase3.md` §6 (aggregate rules), §4 (concept
lists per context)
**Design-only:** no models/migrations exist in this phase (spec §26).

---

## 1. Aggregate Rules (spec §6)

Every aggregate has: a **root** · an explicit **boundary** · its own
**invariants** · children never mutated directly from outside · a defined
**transaction boundary** (one aggregate per transaction; spec §16).

## 2. Worked Example — PerformanceEvaluation (spec §6)

```
PerformanceEvaluation            ← Aggregate Root
├── EvaluationReviewer           (child: reviewer + weight)
├── EvaluationScore              (child: criterion + score + history)
└── EvaluationResult             (child: computed outcome)
```

Invariants (from spec §4 Context 05):
- multiple reviewers allowed, each with a weight;
- scores are editable, and **every change is audited**;
- result computed only via the weighted calculation rules
  (`performanceScoreCalculationService` domain service, spec §17);
- `EvaluationScore` is never modified outside the root.

## 3. Catalog by Context

> Roots in **bold**; children indented. "T" marks tenant-owned aggregates.
> Invariants listed are the main ones — the implementing phase finalizes
> field-level rules (Phase 5 database dictionary).

### 01 Identity
- **user** (T): credentials, authentication factors, account status/lifecycle.
  Inv: unique credential per type; status transitions valid; no employment data.
- **session** (T): token/session lifetime, revocation. Inv: revoked/expired
  sessions never authorize.
- **role** (T): permission assignments. Inv: permission codes valid; no
  duplicate permission in role.
- **accessPolicy** (T): policy rules attached to roles/users.

### 02 Tenancy
- **tenant**: lifecycle (active/suspended/closed), tenant configuration.
  Inv: closed tenants accept no business writes.
- **tenantMembership** (T): user↔tenant with status/role scope.
  Inv: one active membership per (user, tenant); suspended membership blocks
  tenant activity.

### 03 Organization
- **organization** (T): legal entity metadata, root of hierarchy.
- **orgUnit** (T): business unit/division/department/team node; parent
  reference. Inv: hierarchy acyclic; unit type valid.
- **position** (T): organizational position definition. Inv: unique code per
  tenant; assignments live in Workforce.

### 04 Workforce
- **employee** (T): person profile, skills, lifecycle.
  Inv: lifecycle transitions valid; optional userId reference unique.
- **employment** (T): employment record, contract, position assignment,
  reporting relationship. Inv: one active employment per employee at a time.
- **leaveRequest** (T): leave type/period/status. Inv: period valid; no
  overlap with another approved leave of the same employee.
- **attendanceRecord** (T): check-in/out facts. Inv: out ≥ in.

### 05 Performance
- **performanceCycle** (T): cycle period, criteria, participating KPIs.
  Inv: period not overlapping an open cycle of same scope.
- **performanceEvaluation** (T): reviewers, scores, result (§2).
- **kpi** (T): KPI definition, target, unit. Inv: unique code per tenant.

### 06 Projects
- **project** (T): phases, milestones, budget, status, risks.
  Inv: status lifecycle valid; budget non-negative (Money VO); dates ordered.
- **projectMembership** (T): member + project role.
  Inv: unique (project, member).

### 07 Tasks
- **task** (T): subtasks, assignments, priority, status, deadline,
  dependencies, checklist. Inv: status lifecycle valid; dependency graph
  acyclic; assignee is a resolved principal; deadline ≥ start.
- **taskComment** (T): append-oriented comment stream referencing taskId.
- **taskActivity** (T): append-only activity/history stream referencing
  taskId.

### 08 Assets
- **asset** (T): category/type refs, ownership, assignment, lifecycle status.
  Inv: lifecycle transitions valid; assignment references resolved principal/org.
- **assetType** (T): type/category taxonomy. Inv: unique code per tenant.

### 09 Devices
- **device** (T): registration, health, connection state; asset reference.
  Inv: registration unique per tenant; connection state machine valid.
- **telemetryReading** (T): append-only readings (never inside **device** —
  volume). Inv: metric valid; reading immutable.

### 10 Maintenance
- **maintenancePlan** (T): preventive plan, schedules, target asset/device.
  Inv: schedule dates ordered; target reference valid.
- **workOrder** (T): corrective/preventive order, assignment, outcome,
  events. Inv: status lifecycle valid; completion requires outcome.

### 11 Documents
- **document** (T): versions, metadata, classification, permissions,
  relations, lifecycle. Inv: version monotonically increases; lifecycle
  transitions valid; permission changes audited.
- **folder** (T): folder tree. Inv: hierarchy acyclic.

### 12 Workflow
- **workflowDefinition** (T): versions, steps, transitions.
  Inv: transitions reference defined steps; definitions versioned.
- **workflowInstance** (T): current step, approvals, assignments,
  transitions history, escalation. Inv: only defined transitions allowed;
  approvals recorded before advance; delegation audited.

### 13 Communication
- **conversation** (T): type (direct/group/channel), members, settings.
  Inv: members resolve; type-specific member rules.
- **message** (T): content, attachments, edit history; conversation ref.
  Inv: edits append history; deletion per policy (retention).
- **meeting** (T): participants, sessions, recording/transcript refs.
  Inv: sessions belong to the meeting; recording flags per policy.
- **call** (T): call participants and state.
- **presenceRecord**: per-user/per-device ephemeral state (cache-backed;
  Redis is not the source of truth).

### 14 Notifications
- **notification** (T): payload, recipients resolution, status.
  Inv: recipients resolved from event; delivery attempts recorded.
- **notificationPreference** (T): per-user channel/policy preferences.
- **notificationTemplate** (T): versioned templates.

### 15 Audit
- **auditEvent** (T): actor, action, entity, previousState, newState,
  timestamp, correlationId, client metadata. Inv: **append-only**; immutable
  after write; no business CRUD mixing.

### 16 Reporting / Analytics
- **reportDefinition** (T): report spec/parameters.
- **dashboard** (T): widget layout/ownership.
- **projection** (T): read-model snapshot built from events.
  Inv: rebuildable from events; never written by business transactions.

### 17 AI
- **aiJob** (T): request, context ref, result, classification
  (advisory/draft/automated/authoritative), model/prompt versions.
  Inv: classification mandatory; authoritative path requires review.
- **promptDefinition** (T): versioned prompt.
- **modelConfiguration** (T): provider/model routing + limits.
- **aiFeedback** (T): feedback on results.

### 18 Integration
- **connectorConfiguration** (T): connector type, endpoint, credential
  reference, mapping. Inv: secrets referenced, never embedded.
- **integrationEventRecord** (T): inbound/outbound record with idempotency
  key. Inv: duplicate delivery creates no duplicate business state.
- **syncJob** (T): synchronization run/state.

### 19 Configuration
- **configurationEntry** (T): scoped (system/tenant) runtime setting.
  Inv: scope + key unique; changes audited.
- **featureFlag** (T): flag state per scope.

### 20 Platform Core
- No business aggregates. Provides: identifier, result/error, clock,
  correlation, tenant context, security context, domain event base,
  aggregate/entity base contracts, repository contracts.

## 4. Transaction Boundaries (spec §16)

- One aggregate per database transaction; cross-aggregate consistency via
  events (eventual consistency) where business rules allow.
- Examples: completing a task (one **task** transaction + `taskCompleted`
  event); approving a document (one **document** transaction + workflow
  event; the workflow instance advances in its own transaction).
