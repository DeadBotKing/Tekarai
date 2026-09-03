# ADR-017 — Cloud Ready Strategy

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "Cloud Ready Strategy"

## Context

The first deployment target is on-premise Windows + SQL Server + Waitress
(ADR-003/004), but the product must deploy to cloud environments without an
architecture rewrite.

## Decision

1. **No architectural dependency on on-premise-only facilities:** the backend
   never assumes local disks (storage port, Phase 02 §25), local time (UTC
   storage), machine-local state (no in-process state that blocks horizontal
   scaling) or a single node (stateless request handling).
2. **Configuration is fully externalized** (ADR-009): environment variables
   drive every environment difference — the same artifact runs on-premise or
   in a container.
3. **Stateless application tier:** anything that must survive a process
   restart lives in SQL Server (or the future cache/queue infrastructure),
   never in process memory.
4. **Media never flows through Django** (WebRTC/SFU in the Communication
   phase; object storage via the storage port) — keeping instances small and
   scalable.
5. Container/orchestration packaging (Docker, health-probe wiring, rollout
   and rollback) is delivered in the Deployment phase — the architecture
   keeps those hooks ready (health endpoints, externalized config,
   statelessness).

## Alternatives

- **Cloud-only design (serverless first)** — rejected: the approved baseline
  is on-premise SQL Server + Windows.
- **Assume single-instance forever (in-memory state, local files)** —
  rejected: blocks both scaling and cloud migration.

## Consequences

- Positive: same code and contracts on-premise and in cloud; horizontal
  scaling stays possible.
- Negative: some conveniences (local file assumptions, sticky state) are
  permanently forbidden.
