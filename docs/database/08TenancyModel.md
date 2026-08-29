# 08 — Tenancy Model

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §6–7 · **ADR-012**

---

## 1. Model

Single database, shared schema, row-level tenancy (ADR-012). Every
tenant-owned table carries `tenantId` (UUID FK → Tenant). Platform-level
tables (Permission, ConversationType, NotificationChannel, IntegrationType,
AiProvider registry, Feature) are global by design and marked `T = —` in
`04EntityCatalog.md`.

## 2. Tenant Entity (spec §7)

| Field | Rule |
|---|---|
| id | UUID PK |
| name | required; unique policy: scoped (see below) |
| code | **globally unique** (platform identifier used in routing/integration) |
| description | optional |
| status | active · suspended · closed (controlled vocabulary) |
| base fields | createdAt/updatedAt/createdBy/updatedBy/deletedAt/deletedBy/isActive |

`name` uniqueness: **unique per scope** (tenant display names need not be
globally unique); `code` is the platform-global identifier — matches spec §7
("name بسته به سیاست Platform می‌تواند Global Unique یا Unique per Scope
باشد" — resolved here and recorded for Phase 05).

## 3. Isolation Layers (spec §6)

| Layer | Enforcement |
|---|---|
| Application | use cases require tenant context derived from identity (never client-supplied alone) |
| Repository | every tenant-scoped query filters `tenantId` (default manager excludes other tenants) |
| Database | every tenant-owned table has `tenantId` FK + tenant-aware uniques + `(tenantId, …)` indexes; cross-tenant FKs structurally discouraged (same-tenant FK rule below) |
| Authorization | cross-tenant operations denied by default; explicit platform-admin capabilities audited (ADR-012) |

## 4. Structural Rules

1. **FK tenant rule:** any FK between two tenant-owned tables must reference
   the same tenant (domain + repository check; filtered-unique/FK guards at
   implementation where supported — engine note, 07 §5).
2. **Unique rule:** business identifiers unique per tenant:
   `UNIQUE(tenantId, code)` (07 §1).
3. **Index rule:** leading `tenantId` composites (06 §1–2).
4. **Platform → tenant references** allowed (global catalogues consumed by
   tenant rows); tenant → platform references never leak tenant data upward.
5. **Polymorphic ownership** (Attachment, TagAssignment, CustomFieldValue,
   Address, ContactInformation, WorkflowInstance targets, MaintenancePlan
   targets) must validate owner tenant = row tenant in the application
   layer (structural FK not expressible for polymorphic targets — documented
   exception, reviewed per use case).

## 5. Tenant Data Map (spec §6)

Tenant-owned domain groups: Users · Employees/Organization · Projects/Tasks ·
Documents · Devices/Assets/Maintenance · Notifications · Communications ·
Reports/Analytics · AI data · Integration configuration — exactly the
`T = ✓` rows of `04EntityCatalog.md`.

## 6. Test Strategy (from implementation phases)

- Repository isolation test per context (tenant A write → tenant B read
  must miss).
- Tenant-aware uniqueness tests (same code in two tenants succeeds; same
  code twice in one tenant fails).
- API tests: client-supplied tenant IDs cannot switch scope.
- These are DoD items for every tenant-owned aggregate (Phase 03/ADR-012).
