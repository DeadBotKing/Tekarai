# ADR-005 — API First

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

Tekarai must serve web, mobile, desktop, machine/agent clients and external
integrations from one backend. Contracts must remain stable and versionable
for years.

## Decision

1. Every capability is exposed through a **versioned REST API**
   (`/api/v1/<domain>/<resource>/`) with consistent response and error
   envelopes. WebSockets join with the Communication phase.
2. The API is a contract, not an implementation detail: clients depend only on
   documented, versioned endpoints.
3. Serializers map transport data to application DTOs; business rules never
   live in views or serializers (Development Rules §4).
4. Phase 01 lays only the framework foundation (DRF installed); the first
   business endpoints arrive with their phases.

## Alternatives

- **GraphQL-first** — rejected: harder to cache, audit and version
  mechanically for enterprise clients at this stage.
- **RPC-style endpoints** — rejected: not resource-oriented, poor long-term
  contract stability.

## Consequences

- Positive: any client type consumes the same contracts; versioning isolates
  change.
- Negative: contract discipline is mandatory — breaking changes require a new
  API version.
