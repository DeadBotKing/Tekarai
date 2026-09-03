# ADR-014 — Extension / Plugin Strategy

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "Extension / Plugin Strategy"

## Context

Tekarai must stay industry-neutral while serving industry-specific needs
(pharmaceutical manufacturing is the reference customer, not the product
boundary). Customer-specific forks of the Core would destroy the product.

## Decision

1. All industry/customer-specific behaviour lives **outside the Core**, as one
   of: **Industry Pack · Plugin · Integration Connector · AI Provider ·
   Storage Provider · Notification Provider**.
2. The Core exposes **stable extension points**: application contracts,
   integration events, provider ports (storage, notification, AI, call),
   workflow definitions and configuration. Extension points are versioned
   like public APIs.
3. Extensions may consume Core contracts and add behaviour; they must not
   modify Core internals, Core-owned tables, or bypass tenant isolation and
   authorization.
4. **Configuration over customization**: when configuration can express the
   variation, no code extension is written.
5. An Industry Pack may bring its own Django apps/modules following the same
   layer rules as Core contexts (ADR-007) and is installed explicitly per
   tenant/deployment.

## Alternatives

- **Fork per customer** — rejected: unmaintainable, kills the product.
- **Hard-coded industry flags inside Core** — rejected: the spec explicitly
  forbids industry logic in Core.
- **Unrestricted plugin access to Core internals** — rejected: plugins become
  rewrite hazards; only stable contracts are exposed.

## Consequences

- Positive: sellable Core, per-industry packs, upgrades without forks.
- Negative: Core contracts must stay disciplined and versioned — breaking a
  contract breaks third-party packs.
- `docs/architecture/ExtensionArchitecture.md` defines extension types and
  rules in detail.
