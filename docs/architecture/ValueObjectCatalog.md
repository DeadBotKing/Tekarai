# Tekarai — Value Object Catalog

**Status:** Authoritative (Phase 03 — Domain Architecture)
**Specification:** `docs/Phases/Phase3.md` §8

---

## 1. Rules (spec §8)

A value object:
- has **no independent identity** (unlike entities, spec §7);
- is **immutable** — every transformation returns a new instance;
- is **validated** at construction — an invalid VO can never exist;
- is **side-effect free**;
- is compared by value, not by id.

Entities use UUID identity (spec §7); VOs never do.

## 2. Shared Value Objects (owned by Platform Core, spec §4 Context 20)

| Value Object | Invariants | Used by |
|---|---|---|
| emailAddress | RFC-style format, normalized lowercase | Identity, Workforce, Communication |
| phoneNumber | E.164-style normalization | Identity, Workforce, Notifications |
| money | Decimal amount (never float) + currency code; non-negative where required | Projects (budget), Contracts |
| address | normalized postal fields | Organization, Workforce |
| dateRange | start ≤ end, timezone-aware (UTC storage) | Performance cycles, Leave, Projects |
| percentage | 0–100 (or 0–1 normalized per contract) | Performance weights, Analytics |
| score | Decimal within criteria bounds | Performance |
| coordinates | valid lat/long pair | Assets, Devices, Organization locations |
| fileSize | non-negative, unit bytes | Documents, Communication attachments |
| duration | non-negative time span | Meetings, Calls, Maintenance tasks |

These are exactly the ten VOs the spec names (§8) — owned centrally so no
context redefines money/score semantics.

## 3. Per-Context Value Objects

| Context | Value Objects |
|---|---|
| Identity | credentialSecret (hashed representation), permissionCode, roleCode, tokenScope |
| Tenancy | tenantScope, membershipStatus (state) |
| Organization | orgUnitType, legalId, hierarchyPath |
| Workforce | employmentType, skillLevel, leaveType, attendanceWindow |
| Performance | evaluatorWeight, evaluationCriteria, performanceRating |
| Projects | projectStatus (state), milestoneProgress, budgetSnapshot |
| Tasks | taskStatus (state), taskPriority (state), checklistItem, dependencyType |
| Assets | assetStatus (state), assetCategoryRef |
| Devices | deviceHealthStatus (state), connectionState (state), telemetryMetric |
| Maintenance | workOrderStatus (state), maintenanceCadence |
| Documents | documentStatus (state), versionLabel, classificationLevel, storageObjectRef |
| Workflow | workflowState, transitionRule, approvalDecision |
| Communication | conversationType, messageContentType, presenceStatus, recordingPolicy |
| Notifications | notificationChannel (state), deliveryStatus (state), digestWindow |
| Audit | auditDiff (before/after pair), clientMetadata |
| Analytics | metricName, aggregationWindow |
| AI | modelVersion, promptVersion, resultClassification (advisory/draft/automated/authoritative) |
| Integration | connectorEndpoint, idempotencyKey, payloadMapping |
| Configuration | configScope (system/tenant), flagState |
| Platform Core | typed identifiers (tenantId, userId, correlationId, aggregateId), versionStamp, clockInstant |

## 4. Usage Rules

1. VOs cross layers freely (they are pure data + rules) but never leave the
   process as private implementations — API/integration payloads define their
   own DTO representations (Phase 02 rule: event schema never couples to
   internal implementations).
2. Money math is Decimal only (Master Specification; float forbidden).
3. Timestamps are stored UTC and rendered per user timezone (ADR-017).
4. State VOs (statuses) define their allowed transitions; the transition
   rules are aggregate invariants (`AggregateCatalog.md`).
