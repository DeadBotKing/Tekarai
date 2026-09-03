# ADR-002 — Modular Monolith

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

Tekarai spans ~20 bounded contexts. The team is rebuilding from zero with a
small, possibly AI-assisted development workflow. Early distribution
(microservices) would multiply infrastructure, testing and deployment cost
while domain boundaries are still being proven.

## Decision

1. The first and current deployment style is a **single deployable modular
   monolith** with strict internal module boundaries (one bounded context per
   Django app/module, layers inside each).
2. Cross-context communication happens through application contracts and
   events — never by reaching into another context's models or tables.
3. Service extraction is allowed only when a documented scale or isolation
   requirement justifies it, and must be recorded as a new ADR.

## Alternatives

- **Microservices** — rejected for now (see ADR-001).
- **Serverless functions around shared tables** — rejected: destroys domain
  ownership and transactional integrity.

## Consequences

- Positive: single quality gate, single deployment, fast local development,
  trivial cross-context transactions where justified.
- Positive: domain boundaries remain testable via architecture tests
  (Phase 01 §13 guard rails installed in `tests/architecture/`).
- Negative: discipline is required so the monolith does not decay into a
  tangle — enforced by dependency rules and reviews.
