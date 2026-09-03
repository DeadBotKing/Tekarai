# Tekarai — Observability Architecture

**Status:** Authoritative (Phase 02 — Architecture & ADRs)
**Related ADRs:** ADR-016 (decisive), ADR-008
**Live today:** health endpoints (Phase 01) + structured logging config.

---

## 1. Pillars (Phase 02 §23)

| Pillar | Baseline decision | Full delivery |
|---|---|---|
| Logging | structured console now; JSON in production (ADR-016) | phased |
| Metrics | application-layer counters/timers at ports | metrics phase |
| Tracing | correlation/request IDs on every important operation | with API phase |
| Health checks | `/healthz/`, `/readyz/` (app + database) since Phase 01 | extends per phase |
| Error monitoring | stable error envelopes; no stack traces to clients | operations phase |

## 2. Correlation Identifiers

- Every important request/business operation carries a **request ID /
  correlation ID** that flows: HTTP request → use case → events → audit
  records → outbound integrations.
- Correlation IDs are part of event contracts (Event Architecture §3) and
  audit records — enabling incident reconstruction.

## 3. Logging Rules

1. Log events are structured (level, timestamp, logger, message, context
   fields, correlationId).
2. Secrets, tokens and passwords are never logged (Development Rules §12).
3. Domain layer logs business facts via domain events rather than ad-hoc
   strings; infrastructure logs technical detail.
4. Production format: JSON (`logFormat=json`, reserved in `.env.example`).

## 4. Health & Readiness

- Current components: application, database (engine label + latency,
   credential-free).
- Future components per phase: cache (Redis), queue/broker, storage,
   external services (spec §17).

## 5. Audit Architecture (Phase 02 §22)

- Principle: **Everything is Auditable** — but audit is not logging
  (ADR-016 §3).
- Audit records capture, as far as applicable: **Who · What · When · Where ·
  Why · Before · After**, plus correlation ID.
- Records are append-oriented and not casually editable; security-sensitive
  and important business operations are recorded by their use cases.
- `createdAt/updatedAt` alone is explicitly **not** audit (spec §22).

## 6. Metrics & Tracing Placement

- Metrics/tracing are infrastructure concerns reached through ports — no
  vendor SDK inside domains (RULE D).
- Use cases emit timing/outcome data at their boundaries; adapters emit
  protocol-level telemetry.

## 7. Failure Visibility

- Infrastructure errors surface as stable error envelopes with correlation
  IDs; operational detail goes to logs/metrics, never to clients.
- Alerting/monitoring wiring is an operations-phase deliverable
  (System Architecture §10).
