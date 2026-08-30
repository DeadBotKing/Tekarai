# Phase 09 Report — Notification Platform

- Status: **COMPLETE** — built file-by-file against the spec; full gate green
  (**457 tests, 0 failures** — 386 pre-existing + 71 new).
- Date: 2026-08-30
- Spec: `docs/Phases/Phase9.md` (§1–§50) · Manifest: `docs/Phases/Phase9Manifest.md`
- ADR: ADR-024 (single-recipient aggregate, queue port, outbox consumer,
  provider failover, retry semantics)
- API doc: `docs/api/NOTIFICATION_API.md` · Runbook: `docs/operations/Phase9Runbook.md`

## 1. What was built

A complete Notification bounded context under `backend/apps/notifications/`
(69 files, ~9.4k lines) following the house DDD/Clean architecture
(domain → application → infrastructure → presentation; kernel-templated use
cases; event-driven; multi-tenant; audit-first).

### Domain (framework-free; guarded by architecture tests)

- `valueObjects/notificationTypes.py` — every vocabulary of §3–§29:
  7 notification statuses (+ terminal/dispatchable sets), 14 categories,
  5 priorities with rank + the §5 bypass rule (CRITICAL bypass ONLY for
  SECURITY/SYSTEM and only when the policy explicitly allows it),
  6 channels + PUSH_LIKE set, 8 delivery statuses + PERMANENT_ERROR_CODES,
  9 recipient types, 3 preference levels, digest/schedule enums, the §20
  language chain constants, §24 retry/backoff constants (30s → ×4 → cap 600s),
  §28 rate/cooldown defaults and the §29 hashed idempotency key
  (`sha256(tenant|eventType|eventId|recipient|type)`).
- `entities/notification.py` — single-recipient aggregate (ADR-024):
  `startProcessing`, `applyDeliveryOutcome` (DELIVERED / PARTIALLY_DELIVERED /
  FAILED), idempotent `cancel`/`expire` (§23 — expired is never delivered),
  `markRead` / `markUnread` (ack-guard, §26) / `acknowledge` (implies read),
  `archive` soft delete, correlationId/causationId (§46).
- `entities/notificationDelivery.py` — per-channel row (§25) whose
  `markFailed` classifies PERMANENTLY_FAILED vs RETRY_SCHEDULED with
  exponential backoff; `retryIsDue`, `isPendingRetry`, `skip` (a disabled
  channel is not a failure).
- `entities/notificationPreference.py` + `NotificationPreferenceRule` —
  per-level validated preferences (§10) and tenant FORCED/DENIED rules (§11).
- `entities/notificationTemplate.py` — safe `{token}` rendering (§18 — pure
  substitution, no code execution), `placeholders()`, `nextVersion()` (§19).
- `entities/notificationPolicy.py` — config-driven policy (§8) with
  type-beats-category matching, escalation stages (§27), bypass flag;
  `NotificationPolicyChannel` (§36).
- `entities/notificationDevice.py` — many devices per user (§15), idempotent
  revoke.
- `entities/notificationDigest.py` — digest aggregate (§21) + schedule
  aggregate (§22: IMMEDIATE/SCHEDULED/RECURRING/DELAYED/DIGEST with due/run
  arithmetic).
- `services/notificationRules.py` — §10/§11 channel arithmetic
  (tenant deny → user prefs → tenant force; critical bypass guard),
  §20 language resolution, §24 retry classification, §28 cooldown/window.

### Application (§38 — 15 services + read/admin use cases)

`CreateNotificationService` (§7/§9 fan-out, §29 dedup, §28 anti-storm with
digest aggregation, §23 expiry), `ResolveRecipientsService` (§9 incl.
EXTERNAL with synthetic identities), `ResolveNotificationPolicyService`
(§8/§11 incl. the "tenant may never weaken security" guard),
`ResolveNotificationPreferencesService`, `RenderNotificationService`
(§18/§20 with exact → tenant → platform template fallback),
`DispatchNotificationService` — the §32 eleven-step worker core with §47
per-channel isolation, §27 escalation scheduling and §44/§45 metrics/logs,
`RetryNotificationDeliveryService` (§24), `CreateDigestService` +
`SendDigestService` (§21), `ScheduleNotificationService` +
`RunDueSchedulesService` (§22), `CancelNotificationService`,
`MarkNotificationReadService` (+ unread/bulk/ack/archive/list/get/unread),
`RegisterNotificationDeviceService` / `RevokeNotificationDeviceService` (§15),
plus admin services for templates/policies/tenant rules and
`ExpireNotificationsService` (§23 sweeper). Ports: `NotificationJobQueue`
(§31 — broker replaceable), `NotificationChannelRegistry`,
`AiNotificationComposer` (§43 interface only).

### Infrastructure (§12/§13/§30/§31/§39/§41/§44)

- 12 tables exactly as §36 lists them (`notifications*`, templates +
  immutable template versions, policies + policy channels) with the §37
  index set (unread recipientId+readAt+createdAt; retry status+nextAttemptAt;
  unique tenantId+idempotencyKey). Migration `0001_phase9_notifications`.
- All §39 repositories implemented over the ORM; row↔entity mapping only.
- Channel adapters (§12) each owning a `ProviderPool` (§48 failover chains,
  configurable via `NOTIFICATION_*_PROVIDERS`); log-backed defaults keep the
  platform fully functional without external services; a real SMTP adapter
  ships for email.
- §30 consumer: subscribes to Phase-08 outbox events through a configuration
  route table (`NOTIFICATION_EVENT_ROUTES`) — meeting/call/message/letter/
  recording/AI events become notifications with zero coupling.
- `InlineNotificationQueue` (§31) + `runNotificationWorker` management
  command (dispatch → retry → schedules → digests → expiry, `--once` or loop).
- Realtime broadcaster (§41) with the Phase-08 loop-hopping technique;
  metrics registry (§44 exact names); cross-context directories through
  `identity.profileDirectory` / `communication.participantDirectory`
  application contracts (RULE E/F compliant).

### Presentation (§40/§41)

- 29 REST endpoints under `/api/v1/notifications/` (own notifications,
  preferences, devices; admin send/schedules/templates/policies/channels/
  tenant-rules/metrics), all registered in the OpenAPI catalogue.
- `/ws/notifications/` thin consumer: JWT auth (4401 when missing),
  `notification.event` pushes, heartbeat, reconcile hint (§42).

## 2. Platform integration

- `apps.notifications` added to INSTALLED_APPS + MIGRATION_MODULES; routes
  mounted in `config/urls.py`; WS routing merged in `config/asgi.py`.
- Permission catalogue: `notification.send`, `notification.manage`
  (platformAdmin + tenantAdmin presets — `bootstrapPlatform` extends existing
  roles, so a re-run grants them automatically).
- `InProcessEventDispatcher` (shared kernel): one class-level handler
  registry shared by all instances (EVOLUTION NOTE in code) — required for
  boot-time subscriptions to reach per-use-case dispatchers (§30).
- Architecture tests: notifications context added to the Phase-01/03 opening
  registers; "Notification" vocabulary allowed inside the context only;
  `notification_event`/`add_arguments` framework hooks exempted.
- `seedNotifications` command: 20 templates (10 keys × fa-IR/en-US) + 7
  default policies; idempotent, re-saving an edited template creates the
  next version (§19).

## 3. Verification

- **457/457 tests green** (71 new: 32 domain unit, 19 application/worker,
  15 API contract, 5 WebSocket).
- §49 critical scenarios all covered by tests: duplicate event, duplicate
  notification, duplicate delivery (re-dispatch), provider failure, timeout
  class errors, retry + backoff recovery, partial delivery isolation,
  tenant isolation, preference override, critical bypass guard, expired
  notification, cancelled notification, device revoked (push stops
  immediately), offline user (WS reconnect → REST recovery), digest
  generation + send.
- §50 DoD: all 36 items delivered (bounded context, aggregate, delivery
  model, preferences, policies, templates + versioning, multi-language,
  in-app + WebSocket, email/push/SMS adapters, provider abstraction,
  device registration, scheduling, retry + exponential backoff,
  deduplication, idempotency, rate limiting, digests, escalation, expiration,
  acknowledgement, outbox integration, async worker, audit, AI interface,
  analytics events, tenant isolation, security/API/worker/integration tests,
  documentation).
- Seed + worker tick verified end-to-end on a real database.

## 4. Deferred by design (documented, not gaps)

- Real FCM/APNs/Graph SDKs: behind `ProviderPool` config (§13/§48) — no code
  change needed to enable.
- Team / org-unit / project-work recipient types resolve empty until those
  bounded contexts open (§9 — engine ready, data later).
- Broker-backed queue (Celery/RQ): one port implementation away (ADR-024).
- Organization-level language policy feeds the tenant default (§20) as
  configuration until the organization phase opens.
