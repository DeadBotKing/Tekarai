# ADR-001 — Product Architecture

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

Tekarai (rebranded from Meryx) is a general-purpose, multi-tenant Enterprise
Operations Platform. The original reference environment was a pharmaceutical
manufacturing operation (Ronak), but the product must remain industry-neutral.
The platform must serve identity, organization, workforce, projects, tasks,
assets, devices, maintenance, documents, workflow, communication,
notifications, analytics, AI, integration, audit and configuration for web,
mobile, desktop, machine/agent clients and external systems — and remain
maintainable for 5–10+ years.

## Decision

1. Tekarai is a **product platform**, not a customer application. Industry
   behaviour is delivered only through Industry Packs, extensions, plugins,
   connectors and configuration — never inside the Core.
2. The architectural style is **Modular Monolith + DDD + Clean Architecture +
   SOLID + Event-Driven**, with API First, Security First, AI Native, Cloud
   Ready, Offline Ready and Configuration over Customization.
3. Microservices are an optimization for a later, proven need — not the
   starting architecture.
4. Project-specific technical identifiers use **camelCase** (`createdAt`,
   `tenantId`, `dbHost`, `jwtSigningKey`). Framework identifiers remain exactly
   as the framework defines them (`SECRET_KEY`, `INSTALLED_APPS`,
   `select_related`, `SET_NULL`, `is_staff`). Documentation files use
   `PascalCase.md` or `UPPERCASE` standardized names.
5. This ADR supersedes the historical `docs/Phase 1/ADR-001.md` from the lost
   build (see `docs/Phase 1/HISTORICAL-NOTE.md`).

## Alternatives

- **Customer-specific application for the pharmaceutical site** — rejected:
  kills reusability and sales potential; the reference customer becomes a trap.
- **Microservices from day one** — rejected: unproven domain boundaries, high
  operational cost, contradicts the rebuild-from-zero starting condition.
- **Single-layer rapid Django application (fat models/views)** — rejected:
  unmaintainable at the intended scope; business rules would leak into the
  framework layer.

## Consequences

- Positive: one architecture for every industry; long maintenance horizon;
  clear extension seams for industry packs.
- Positive: naming is deterministic and machine-checkable (enforced by
  `tests/architecture/test_namingConventions.py`).
- Negative: more structure and ceremony than a simple app — accepted cost for
  an enterprise platform.
- Every future phase must respect this ADR or explicitly supersede it with a
  new ADR.
