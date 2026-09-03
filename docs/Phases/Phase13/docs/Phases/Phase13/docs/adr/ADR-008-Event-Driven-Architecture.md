# ADR-008 — Event Driven Architecture

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

Cross-context workflows (task assigned → notification → analytics projection)
must not be built as synchronous chains of direct calls. The specification
distinguishes facts from requests.

## Decision

1. **Domain events represent facts** ("TaskAssigned happened"); **commands
   request actions**; **queries never mutate state**.
2. Integration events cross context/process boundaries with versioned names
   (e.g. `communication.signal.v1` style introduced by the Communication
   phases).
3. Handlers must be idempotent where duplicate delivery is possible; retries
   and dead-lettering are infrastructure concerns.
4. The concrete transport (in-process bus, outbox, broker) is selected in the
   phases that need it — Phase 01 builds no event infrastructure.

## Alternatives

- **Direct synchronous calls between contexts** — rejected: coupling,
  cascading failures, no audit projection path.
- **CRUD polling between modules** — rejected: latency and load; no fact
  semantics.

## Consequences

- Positive: loose coupling, natural audit/analytics projections, room to
  introduce the outbox pattern when reliability requires it.
- Negative: eventual consistency must be designed for; debugging needs
  correlation identifiers (audit phase defines them).
