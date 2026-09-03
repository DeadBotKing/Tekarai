# ADR-018 — Offline Ready Strategy

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "Offline Ready Strategy"

## Context

Field/industrial clients (maintenance technicians, factory floors) may lose
connectivity. Phase 02 §30 does not require an offline-first system now — it
requires the architecture to permit offline-capable clients later.

## Decision

1. **UUID identifiers everywhere** (already mandated) — clients can create
   records offline without a central sequence.
2. **Explicit resource versioning / optimistic concurrency fields** on
   mutable records (e.g. version stamps) so offline edits can detect
   conflicts — designed with the ERD phase (Phase 4/5), not invented ad hoc
   later.
3. **Command idempotency keys** are part of the API contract style, enabling
   safe retry/replay after reconnect.
4. **Queued local mutations:** clients queue offline changes and replay them
   as idempotent commands; conflict resolution rules are domain-specific and
   defined by the owning context when that phase lands.
5. Clients (web/mobile/desktop) own their local cache/queue — the backend
   never assumes a live connection per operation.
6. The concrete offline protocol per client type is designed in the GUI and
   client phases; Phase 02 fixes only the enabling decisions above.

## Alternatives

- **Full offline-first sync engine in Phase 02** — rejected: the spec
  explicitly scopes this out until later phases.
- **Last-write-wins with no version fields** — rejected: silent data loss.

## Consequences

- Positive: offline support becomes a client/protocol concern instead of an
  architecture rewrite.
- Negative: every mutation endpoint must think about idempotency and version
  semantics from the start — a lasting API discipline.
