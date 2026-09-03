# ADR-012 — Multi-Tenant Architecture

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "Multi-Tenant Architecture"

## Context

Tekarai is a sellable, industry-neutral platform: many customer organizations
must share one deployment without ever seeing each other's data. Tenant
isolation is a core architectural boundary (Master Specification §22, Phase 02
§20–21), and it must exist before any business data is implemented.

## Decision

1. **Tenancy model (Phase 02 baseline):** single database, shared schema,
   row-level tenancy — every tenant-owned aggregate carries an explicit
   `tenantId` reference, enforced through application services and
   tenant-scoped repositories. Separate-schema / separate-database deployment
   remains a future scale option and requires a new ADR.
2. **Tenant context, not a global variable:** every request that executes
   tenant-scoped work carries an explicit **Tenant Context** (tenant, user,
   organization context, roles, permissions). It is established from the
   authenticated principal after authentication — never from a client-supplied
   tenant ID alone — and is passed deliberately through the use case.
3. **Isolation is enforced server-side at every layer:**
   - API: authorization derives the tenant from identity/session.
   - Application: use cases require tenant context before execution.
   - Persistence: repositories scope every query by tenant.
   - Cross-tenant operations are prohibited by default; explicit, audited,
     platform-level administrative capabilities are the only exception.
4. **Tenant-aware uniqueness:** business identifiers are unique per tenant
   (`UNIQUE(tenantId, code)`), never globally (Phase 4/5 specs detail this).
5. Tenancy data (Tenant, membership) is owned by the Tenancy/Organization
   contexts (refined in Phase 3); no other context may write tenant records.

## Alternatives

- **Schema-per-tenant / database-per-tenant** — deferred: strongest isolation
  but heavy migration and operational cost at platform start.
- **Client-supplied tenant header as the isolation mechanism** — rejected:
  trivially spoofable; the spec explicitly forbids trusting client tenant IDs.
- **Global mutable tenant variable** — rejected: Phase 02 §21 explicitly
  forbids it; breaks testability and concurrency reasoning.

## Consequences

- Positive: one deployment serves many customers; isolation rules are
  testable from day one (architecture tests + later isolation test suites).
- Negative: every repository and use case must carry tenant scope — a
  permanent discipline, enforced by review and tests.
- Positive: upgrade path to stronger isolation later without changing domain
  code (repositories encapsulate the scoping).
