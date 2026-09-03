# ADR-021 — Shared Kernel dependency exception (RULE E/F amendment)

**Status:** Accepted (Phase 06) · **Context:** Phase 02 RULE F says
cross-module imports must target the other module's application layer only;
RULE E said infrastructure never imports other contexts. Phase 06 introduces
the Shared Kernel (`apps/sharedKernel`) — cross-cutting primitives every
context needs at every layer (errors, ports, envelope, middleware).

## Decision

1. **`apps.sharedKernel.*` is public to all layers of every context.** It is
   the platform's explicit contract, not a business context; its own
   `domain`/`application` stay framework-free (existing RULE A–D tests apply
   to it like any context).
2. **Composition roots may cross context boundaries via application facades
   only**: `infrastructure/container.py` of one context may import another
   context's `application` service (e.g. Identity's container uses Tenancy's
   `TenantDirectory`). Domain, infrastructure and presentation of other
   contexts remain private (RULE E unchanged otherwise).

## Consequences

- Cross-context wiring stays one-hop and reviewable; `testArchitecturalRules`
  encodes both amendments explicitly.
- The kernel must never grow business logic; its scope is checked by
  `testNoBusinessDomains` vocabulary scan (no unopened-context vocabulary).
- Alternatives rejected: settings-dot-path indirection everywhere (hides the
  dependency graph), duplicating primitives per context (drift).
