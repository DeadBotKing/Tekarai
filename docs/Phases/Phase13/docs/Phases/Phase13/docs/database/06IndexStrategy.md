# 06 — Index Strategy

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §33–34
Every index has a query-pattern justification (spec §33). No blind indexing.

---

## 1. Standard Index Set (implied — not repeated in `04EntityCatalog.md`)

Applied to **every tenant-owned base entity** (SQL Server nonclustered):

| Index | Justification (query pattern) |
|---|---|
| `(tenantId)` | tenant-scoped repository reads (ADR-012: every query filters tenant) |
| `(tenantId, isActive)` | active-row listings per tenant |
| `(tenantId, createdAt)` | newest-first listings, temporal windows, pagination |
| FK columns | referential lookups (Django FK index) |

Primary key: UUID nonclustered PK; consider a default `rowversion`/identity
clustering key only at implementation if SQL Server guidance requires it —
engine-specific, must be documented (spec §2; implementation-phase ADR).

Soft-delete aware queries use `(tenantId, deletedAt)` where listings must
include/exclude deleted rows on hot paths (e.g. admin recycle-bin views).

## 2. Standard Composite Patterns (spec §33–34)

| Pattern | Use |
|---|---|
| `(tenantId, status)` | status-filtered worklists |
| `(tenantId, createdAt DESC)` | activity feeds |
| `(tenantId, code)` / unique | business identifier lookup (see 07) |
| `(tenantId, entityType, entityId, timestamp)` | audit lookups by target |
| `(conversationId, createdAt DESC)` | message cursor pagination |
| `(deviceId/metric, occurredAt)` | telemetry time windows |

## 3. Per-Domain Justified Indexes (beyond standard)

| Domain | Index | Query pattern |
|---|---|---|
| Identity | `(userId, expiresAt)` | session expiry sweep |
| Identity | `(tenantId, eventType, occurredAt)` | security event review |
| Workforce | `(organizationUnitId, startDate)` | who was in unit X on date Y (temporal §36) |
| Performance | `(tenantId, status)` on EvaluationCycle | open-cycle lookup |
| Projects | `(projectId, status)` | project task/status board |
| Tasks | `(projectId, status)`, `(tenantId, deadline)` | boards + due-soon worklists |
| Tasks | `(taskId, changedAt)` | history timeline |
| Documents | `(tenantId, status)`, `(documentId, versionNumber)` (unique) | status lists; version fetch |
| Workflow | `(targetType, targetId)` | instances for a business object |
| Workflow | `(assigneeId, status, dueAt)` | my-approvals queue |
| Communication | `(conversationId, createdAt DESC)` | cursor message history (offset pagination forbidden for large threads) |
| Notification | `(userId, readAt)` | unread badge |
| Audit | `(tenantId, entityType, entityId, timestamp)`, `(correlationId)`, `(actorId, timestamp)` | investigation, trace reconstruction |
| Analytics | `(metricId, period)`, `(kpiId, period)` | period series |
| AI | `(tenantId, resultClassification)` | governance review queues |
| Integration | `(integrationId, idempotencyKey)` (unique) | duplicate delivery protection |
| Devices | `(deviceId, metric, occurredAt)` | telemetry windows |

## 4. What Must NOT Be Indexed

- Free-text bodies (use search infrastructure when the phase requires it —
  Phase 02 StorageArchitecture; SQL full-text is an engine-specific option
  to document).
- JSON payload columns (filtering happens after structured keys).
- Any column without a stated query pattern — adding one requires a new row
  in §3 (review gate).

## 5. High-Volume Tables (telemetry, heartbeats, audit, tag values)

- Append-only + time-window access → leading time index (above).
- Partitioning/switching and retention purge arrive at implementation
  (SQL Server partitioning is engine-specific — documented decision
  required, spec §2); retention classes: `10DataRetentionPolicy.md`.
- Writes avoid index bloat: no per-event secondary indexes beyond the
  documented set.

## 6. Review Gate

New index ⇒ pull request adds: query pattern, expected selectivity, and
measurement plan (query plan before/after). Indexes without entries in this
document are treated as architecture violations (RULE N).
