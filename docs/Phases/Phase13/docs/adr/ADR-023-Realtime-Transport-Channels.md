# ADR-023 — Real-Time Transport: Django Channels + Daphne + Redis (Phase 08)

- Status: Accepted (Phase 08, Communication Platform)
- Date: 2026-08-30
- Deciders: Platform architecture
- Related: Phase8.md §7/§8/§10–§12/§29/§30/§31; ADR-019 (session tokens), ADR-021 (shared kernel exception)

## Context

Phase 08 introduces live communication (messages, typing, presence, WebRTC
signaling, read receipts, live meeting events). The platform until now was
purely request/response (DRF over WSGI). Requirements that constrain the
choice:

1. **§8** — WebSocket consumers must be *thin*: authentication, tenant
   resolution, transport validation, delegation to application services,
   response. No business logic in the transport layer.
2. **§7/§31** — presence and typing are ephemeral with TTL heartbeats;
   SQL is only for audit/history, never the source of truth for "online".
3. **§29/§38** — integration events must survive crashes (Outbox pattern)
   and be delivered *after* commit.
4. **§10–§12** — the backend relays versioned signaling envelopes
   (`communication.signal.v1`) but NEVER touches media (WebRTC / SFU is an
   infrastructure adapter).
5. **§30** — REST remains the surface for management/history/search;
   WS only carries live traffic. Django must serve both in one process in
   development.

## Decision

1. **Django Channels 4.3** as the WS framework, with **daphne 4.2** at the
   top of `INSTALLED_APPS` so `runserver` serves the ASGI application
   directly (REST and WS in one dev process). `config/asgi.py` becomes a
   `ProtocolTypeRouter` (http → Django ASGI, websocket → origin validator →
   `URLRouter` → `CommunicationConsumer`).
2. **Channel layer**: `InMemoryChannelLayer` for development/tests;
   `channels-redis 4.3` in production (`REDIS_URL`), pinned in
   `requirements/base.txt`.
3. **Presence** lives in an ephemeral store with TTL (`RedisPresenceRepository`
   with a process-local fallback) — never in SQL (§7).
4. **Thin consumer** (`presentation/ws/communicationConsumer.py`): every
   incoming frame maps 1:1 to an application service
   (`RealtimeRelayService`, use cases). The consumer binds the request
   context (§17 — identity from the verified session token, never the
   payload), never opens the ORM for business decisions.
5. **Signaling v1** is a validated, versioned envelope relayed through
   `RelaySignalUseCase`; SDP/ICE payloads are opaque. `MEDIA_STATE_CHANGE`
   (screen share §14) only updates leg state + audit.
6. **Outbox (§29)**: integration events (`Communication<Name>V1`, §25) are
   written in the same transaction and dispatched only after commit by
   `OutboxDispatcher`; failed deliveries keep their row PENDING and are
   retried (§38 scenario 10).
7. **Cross-context access** goes through Identity's public application
   facade (`apps.identity.application.services.principalDirectory`) per
   RULE E/F (ADR-021).

## Consequences

- `runserver` now speaks WebSocket; plain-WSGI deployments must switch to
  an ASGI server (daphne/uvicorn) — already the documented runbook path.
- The realtime broadcaster is event-loop aware (`bindLoop`) so synchronous
  use cases running in worker threads can publish to the loop-bound
  channel layer safely.
- Metrics (§39) are process-local counters exposed at
  `GET /api/v1/communication/metrics`; a Prometheus exporter can scrape
  the same snapshot without code changes.
- Alternatives rejected: raw ASGI (no layer/group abstraction, more
  hand-rolled security), Centrifugo/Ably (external broker before the
  platform needs it; §22 requires replaceable infra, and the port design
  keeps that door open), polling (violates §7/§30 latency expectations).
