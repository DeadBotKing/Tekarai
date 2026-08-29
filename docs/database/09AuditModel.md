# 09 — Audit Model

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §4–5, §22, §35

---

## 1. AuditEvent (spec §22 — the single append-only audit entity)

| Field | Meaning |
|---|---|
| id | UUID PK |
| tenantId | tenant boundary |
| actorId | who performed the action (user/service account/connector; SET_NULL if actor purged — spec §35) |
| action | controlled vocabulary (created / updated / deleted / restored / approved / rejected / assigned / login / permissionGranted …) |
| entityType | target entity type |
| entityId | target entity id |
| timestamp | UTC instant |
| ipAddress | client address where permitted |
| userAgent | client metadata where permitted |
| beforeState | JSON snapshot before change (null on create) |
| afterState | JSON snapshot after change (null on delete) |
| metadata | change context (which fields, reason code) |
| correlationId | flows from request → use case → events (ADR-016) |
| createdAt | row insert time |

Rules: **append-oriented; no updates, no casual deletes** (spec §22);
retention long-term (`10DataRetentionPolicy.md`); writes happen inside the
use-case transaction that performed the business change (spec §46).

## 2. Base-Entity Audit Columns (spec §4, §35)

`createdBy / updatedBy / deletedBy → User` with **SET_NULL** delete
behavior — deleting a user must never destroy audit information. These
columns are the cheap "who last touched this" layer; the full
Who/What/When/Where/Why/Before/After record is AuditEvent. `createdAt/
updatedAt alone is NOT audit` (spec §22; Phase 02 §22).

## 3. What Must Be Audited (per catalog `Aud = ✓`)

- All create/update/soft-delete of business roots and security-relevant
  children (spec §12: "تمام تغییرات مهم HR باید Audit شوند" generalizes).
- Security operations: login, failed login, permission/role grants and
  revocations, policy changes, session revocation, API key lifecycle
  (Identity phase refines the matrix).
- Evaluation score changes — every edit audited (spec §12, Phase 03 §6).
- Workflow transitions/approvals/delegations.
- Document permission changes and shares.
- AI requests/responses and classification decisions (ADR-013).
- Integration inbound/outbound records (idempotency + audit, ADR-015).

## 4. Audit ≠ Logging (ADR-016)

AuditEvent = durable business-grade record (this document). Logging =
operational telemetry (ObservabilityArchitecture.md). Neither substitutes
the other.

## 5. Soft Delete Interaction (spec §5)

Soft-deleted rows remain queryable for audit/compliance/recovery/
reporting/investigation. `deletedAt/deletedBy` record the deletion fact;
the AuditEvent records the reason and before/after context.

## 6. Query Patterns (drives 06 indexes)

- By target: `(tenantId, entityType, entityId, timestamp)`.
- By actor: `(actorId, timestamp)`.
- By trace: `(correlationId)`.
- Append-only writes; no secondary mutable state.
