# ADR-015 — Integration Strategy

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "Integration Strategy"

## Context

Tekarai must exchange data with ERP (SAP), HR systems, SCADA/WinCC, OPC-UA,
MQTT devices, email/SMS/push providers, AI providers, cloud services,
payment and identity providers (Phase 02 §27). External systems must never
leak into the domain.

## Decision

1. **Ports & adapters only:** every external system is reached through an
   adapter that implements a port defined by the application layer:
   `External System → Integration Adapter → Application Contract → Domain`.
2. Vendor protocols (WinCC, OPC-UA, SAP SDKs) live exclusively in
   Infrastructure / Integration Hub adapters — never in domain or application
   layers, never in Core contexts.
3. **Inbound payloads are untrusted:** external data is validated and mapped
   to integration events/commands at the boundary; it never becomes a domain
   object directly.
4. Inbound integrations (webhooks, MQTT, OPC-UA subscriptions) must be
   **idempotent and audited**; retries and dead-lettering are infrastructure
   concerns.
5. Outbound integrations subscribe to **versioned integration events**
   (ADR-008) through the Integration Hub.
6. Concrete connector build-out happens in the Integration phases; Phase 02
   fixes only the boundary and contract rules.

## Alternatives

- **Direct SDK calls where convenient (e.g. in views)** — rejected: vendor
  lock-in and untestable coupling.
- **Shared database integration with external systems** — rejected: schema
  coupling, no audit trail, breaks ownership.
- **One mega "integration module" mixing protocol and business logic** —
  rejected: adapters must stay per-protocol and thin.

## Consequences

- Positive: new systems connect without touching domains; protocol changes
  are localized.
- Negative: every connector needs a defined contract before implementation
  (spec-mandated discipline).
- `docs/architecture/IntegrationArchitecture.md` holds the binding detail.
