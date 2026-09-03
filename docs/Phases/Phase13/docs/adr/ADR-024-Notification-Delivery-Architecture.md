# ADR-024 — Notification Delivery Architecture

- Status: Accepted (Phase 09)
- Date: 2026-08-30
- Context: `docs/Phases/Phase9.md` (Notification Platform), ADR-002 (modular
  monolith), ADR-008 (event-driven), ADR-023 (Channels realtime + outbox)

## Decision

1. **Single-recipient aggregate.** The Notification aggregate always targets
   exactly one recipient (`recipientId`). Group specs (ROLE / group / channel /
   org unit / tenant / external) are resolved to individual user ids by
   `ResolveRecipientsService` BEFORE fan-out. Delivery, read and
   acknowledgement state therefore never need per-recipient sub-rows, and
   `NotificationDelivery` stays a clean per-channel record (§3/§25/§26).

2. **Worker behind a queue port, no broker dependency.** External delivery is
   asynchronous through the `NotificationJobQueue` port. The default
   `InlineNotificationQueue` executes the §32 worker pipeline immediately
   after the creating transaction commits; `runNotificationWorker` is an
   independent tick (dispatch → retry → schedules → digests → expiry) that
   also recovers anything the inline pass missed. Swapping in Celery/RQ later
   means implementing one port — the application services never change (§31).
   This deliberately defers a broker dependency until a phase requires
   horizontal scale.

3. **Outbox consumption over direct coupling.** Other contexts never call the
   notification engine. They publish integration events (Phase-08 outbox →
   dispatcher); the notification consumer subscribes by event name through a
   configuration route table (`NOTIFICATION_EVENT_ROUTES`, overridable in
   settings). Adding a source event is a config row, not code (§7/§30).
   To make that possible on the modular monolith, `InProcessEventDispatcher`
   now keeps ONE class-level handler registry shared by all instances —
   composition roots instantiate it per use case, while subscribers register
   once at boot.

4. **Channel → provider → adapter layering with failover.** Services see
   `NotificationChannelPort` (IN_APP/PUSH/EMAIL/SMS/DESKTOP/BROWSER). Each
   channel owns a `ProviderPool` (§48) whose chain is configurable via
   `NOTIFICATION_EMAIL_PROVIDERS` / `…SMS…` / `…PUSH…`. Default adapters are
   log-backed so the platform is fully functional — and testable — with zero
   external services; production swaps SMTP/FCM/APNs/Graph by settings only
   (§12/§13/§48).

5. **Retry semantics live in the delivery row.** `markFailed` classifies
   PERMANENTLY_FAILED (§24 permanent error codes, exhausted attempts) vs
   RETRY_SCHEDULED (exponential backoff 30s → 2m → 10m … capped 600s). The
   aggregate outcome counts only hard failures — a channel sitting in
   RETRY_SCHEDULED is "in flight", so one channel's outage can never fail the
   whole notification (§47 partial-delivery isolation).

6. **In-app is persisted truth; WebSocket is optimization.** The notification
   row IS the in-app inbox item (§14). `/ws/notifications/` pushes
   `notification.event` frames to the recipient's group after commit (§41);
   reconnecting clients recover through the REST list/read endpoints (§42).

## Alternatives

- **Per-recipient rows inside one group notification (multi-recipient
  aggregate):** rejected — read/ack state would need a side table and every
  query would fan out; §26's read ≠ acknowledged semantics get murky.
- **Adopt Celery now as the worker:** rejected — the spec (§31) requires the
  broker to stay replaceable, not chosen early; the queue port + inline
  default give identical guarantees at the current scale with zero new
  infrastructure (see ADR-002 modular-monolith guidance).
- **Notifications subscribing directly to the communication ORM:** rejected —
  violates RULE E/F; the participant/profile directory application contracts
  keep contexts replaceable.
- **Immediate synchronous provider calls inside the request:** rejected —
  violates §16/§31 (external delivery must be asynchronous) and loses §24
  retry semantics.

## Consequences

- Notification context owns 12 tables exactly as §36 lists them (templates +
  immutable template versions; policies + per-policy channel rows).
- Cross-context reads (recipients, contacts, language) go through the OTHER
  context's application contracts (`identity.profileDirectory`,
  `communication.participantDirectory`) — RULE E stays green.
- Group structures whose bounded contexts are not opened yet resolve to an
  empty recipient list (logged) — the engine is ready; the data arrives with
  those phases.
- `notification.send` / `notification.manage` action codes were added to the
  permission catalogue; `bootstrapPlatform` extends existing roles, so a
  re-run grants them to platform/tenant admins automatically.
