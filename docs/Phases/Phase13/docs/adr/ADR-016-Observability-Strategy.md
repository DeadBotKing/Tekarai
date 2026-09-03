# ADR-016 — Observability Strategy

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "Observability Strategy"

## Context

An enterprise platform must be diagnosable in production: requests must be
traceable end-to-end, business operations auditable, and failures visible
before customers report them (Phase 02 §22–23: Logging, Metrics, Tracing,
Health Checks, Error Monitoring; "Everything is Auditable").

## Decision

1. **Observability is designed in, not bolted on:** every architectural layer
   treats logging/metrics/tracing as a cross-cutting concern with structured,
   machine-parseable output.
2. **Correlation IDs are mandatory:** every important request/business
   operation carries a request/correlation identifier that flows through
   logs, events and audit records, enabling reconstruction of what happened.
3. **Audit ≠ logging:** audit records (Who/What/When/Where/Why/Before/After)
   are business-grade, append-oriented records owned by the Audit context;
   logs are operational telemetry. Neither substitutes the other.
4. **Health checks are part of the contract:** liveness/readiness endpoints
   exist from Phase 01 (`/healthz/`, `/readyz/`) and extend with cache,
   queue, storage and external service components as those phases land.
5. Metrics/tracing backends are **pluggable infrastructure** (no vendor
   hard-coded in Core); error monitoring is wired at the deployment phase.
6. Structured JSON logging is the production format; console format remains
   available for development (configuration via ADR-009).

## Alternatives

- **printf-style unstructured logs** — rejected: unusable at enterprise scale.
- **Audit as "just rows with createdAt/updatedAt"** — rejected: explicitly
  forbidden (Phase 02 §22).
- **Vendor-specific monitoring SDKs inside domains** — rejected: violates
  domain purity (ADR-007).

## Consequences

- Positive: incidents become diagnosable; audit satisfies governance.
- Negative: every use case/event must propagate correlation identifiers —
  enforced by review and, where possible, tests.
- `docs/architecture/ObservabilityArchitecture.md` holds the binding detail.
