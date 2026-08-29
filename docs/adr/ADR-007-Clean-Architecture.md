# ADR-007 — Clean Architecture

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

The domain must survive framework churn and be testable without HTTP, Redis,
SQL Server drivers or vendor SDKs. Django is an implementation framework, not
the architecture.

## Decision

1. Four layers with dependencies pointing inward:
   `Presentation → Application → Domain ← Infrastructure`.
2. **Domain imports nothing from the framework world** — no Django, DRF, HTTP,
   Redis, Channels, WebRTC or vendor SDKs.
3. Infrastructure implements interfaces (ports) defined by inner layers
   (dependency inversion).
4. Standard context layout (from Phase 02/03 on):
   `apps/<context>/{domain, application, infrastructure, presentation}`.
5. Phase 01 realizes the pattern at the configuration level only
   (`config/environment.py` is plain Python, unit-testable without a request
   cycle); no business layers exist yet.

## Alternatives

- **Django MTV as the architecture** — rejected: business rules end up in
  models/views; framework lock-in.
- **Hexagonal with full CQRS event sourcing on day one** — rejected as the
  starting point: complexity before the domain is proven; read models and
  events are introduced per-phase as required.

## Consequences

- Positive: domain stays pure and fast to test; framework parts are
  replaceable.
- Negative: more files and mapping between layers — accepted enterprise cost.
- Enforced mechanically from Phase 01 by `test_dependencyRules.py`
  (domain files must not import framework modules).
