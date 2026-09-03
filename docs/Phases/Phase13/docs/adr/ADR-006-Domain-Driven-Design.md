# ADR-006 — Domain Driven Design

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

The platform covers ~20 bounded contexts with rich business rules
(evaluations, approvals, maintenance, workflow). A data-centric design would
scatter rules across views and models and collapse under change.

## Decision

1. The solution space is organized as **bounded contexts** (Identity, Tenancy,
   Organization, Workforce, Performance, Project, Task, Asset, Device,
   Maintenance, Document, Workflow, Communication, Notification, Audit,
   Reporting, AI, Integration, Configuration, Platform Core).
2. Each context owns its entities, value objects, aggregates, domain events,
   domain services and repository contracts.
3. Context classification (Core / Supporting / Generic) and the context map are
   designed in Phase 03 — Phase 01 deliberately implements none of them.
4. Cross-context interaction uses application contracts and domain events
   only; direct cross-context model access is forbidden.

## Alternatives

- **Table-driven CRUD design** — rejected: no place for invariants; rules leak
  into UI and reports.
- **One generic "objects" model with type flags** — rejected: destroys
  ownership and tenant-scoped integrity.

## Consequences

- Positive: rules live one place — testable, auditable, replaceable.
- Negative: requires discipline and phase-ordered implementation
  (Platform Core → Identity → Organization → ...).
- Phase 01 installs guard-rail tests (`test_dependencyRules.py`,
  `test_noBusinessDomains.py`) so structure cannot rot silently.
