# Phase 08 Report — Communication Platform

- Status: **COMPLETE** — rebuilt & audited file-by-file against the spec; full gate green (386 tests, 0 failures).
- Date: 2026-08-30 (rebuild audit)
- Spec: `docs/Phases/Phase8.md` (§3–§41) · Manifest: `docs/Phases/Phase8Manifest.md`
- ADR: ADR-023 (Channels/Daphne/Redis, signaling v1, outbox)

## 0. Rebuild audit (second pass)

A full second pass re-verified every layer against the spec text and fixed
three real gaps found by the audit:

1. `GenerateMeetingSummaryQuery` was referenced by the REST view but missing
   from the queries module (the summary endpoint would have failed) — added.
2. §9 catalogue event `MessageRead` was never emitted as an integration
   event — now emitted by the bulk read-receipt use case
   (`CommunicationMessageReadV1`).
3. §39 gauges `activeCalls`/`activeMeetings` were static zeros — now tracked
   live (call start/reject/end, meeting start/end), plus
   `AITranscriptionCompleted` (§9) emitted when a meeting transcript is
   completed.

Live verification on a real daphne server: REST 200/401 semantics, metrics
endpoint, and a real WebSocket client (subscribe → typing → message.send →
presence) all passed. Audit also confirmed: all 15 §26 tables, §27 indexes,
20/20 §35 services, 41 commands, 13 queries, 50 use cases (all wired in the
container), 58 Python files AST-clean with zero placeholders.


## 1. What was built

A complete Communication bounded context under `backend/apps/communication/`
following the house DDD/Clean architecture (domain → application →
infrastructure → presentation, kernel-templated use cases, EDA, API-first,
security-first, multi-tenant, audit-first).

### Domain (framework-free; guarded by architecture tests)

- `valueObjects/communicationTypes.py` — every vocabulary of §3–§16:
  conversation types, 5 participant roles (OWNER/ADMIN/MODERATOR/MEMBER/GUEST),
  10 message types, read states (SENT/DELIVERED/READ monotonic), presence ×6,
  channel visibility, call states, meeting states + RSVP states, recording
  states, letter states, transition tables, protocol versions
  (`communication.signal.v1`, `communication.rt.v1`), `DEFAULT_EDIT_WINDOW_MINUTES = 15`.
- Entities: `conversation` (deterministic `directKey` §5, channels with code §4,
  archive), `participant` (leave/remove/changeRole — ownership transfer refused §6,
  preferences, read watermark), `message` (BODY_MAX 8000; soft delete §34 with
  body withheld at the DTO boundary; edit §33; attachments metadata-only §3.4;
  reactions §3.5; monotonic read states; pins), `meeting` (5-state machine §13,
  RSVP + re-join), `call` (§10; RINGING→end = CANCELLED; mediaState §14),
  `recording` (§15, storage ref = Documents subsystem), `officialLetter`
  (dedicated aggregate §16, reference `^\d{4}-\d{6}$`, approval workflow).
- Services: `communicationRules` — `directKeyOf`, mention extraction
  (emails excluded), `canEditMessage`/`canDeleteMessage` (§33/§34), thread
  validation (§3.8), `SignalingProtocol` validate/envelope (§11).
- Repositories: Protocols for all stores + ports `PresenceRepository` (TTL §7),
  `OutboxRepository` (§29), `RealtimeBroadcaster` (§8), `MediaRouter` (SFU §12),
  `MeetingAiAssistant` (§21). No ORM/Redis/Channels import (§37, tests enforce).

### Application (§35 service inventory — 53 factories)

- 39 commands / 13 queries / DTO layer with mappers.
- `CommunicationUseCase` base: kernel template + outbox integration events
  (`Communication<Name>V1` §25/§29 — same-transaction enqueue, post-commit
  dispatch, row stays PENDING on failure §38) + realtime broadcast helpers.
- Use cases: conversations (direct idempotent via `directKey`, group, channel
  with `PHASE8-UQ_Channel_code`, update/archive, participants, preferences,
  join-PUBLIC-only §4, listings), messages (send idempotent via
  `clientRequestId` §24, mentions resolved through the Identity facade, edit/
  delete policy §33/§34, reactions, bulk read receipts §32, pins, history with
  cursor + thread filter, member-scoped search §22), meetings (§13 lifecycle,
  idempotent create, RSVP, join/leave, end cascades active recordings),
  recordings (§15 permission-gated, publish via storage ref), calls (§10–§12
  start xor conversation/meeting, accept/reject/end, idempotent), signaling
  relay (§11 membership + state checked, sender stamped §17, MEDIA_STATE_CHANGE
  audited §14), presence (§7 TTL store + bulk get), AI summary (§21 ports only),
  letters (§16 create + submit/approve/sign/dispatch/receive with per-action
  permissions), typing relay service (§31 ephemeral — zero SQL).

### Infrastructure (§26–§29, §36)

- 17 models/tables: `communicationConversations`, `communicationChannels`,
  `communicationChannelMemberships`, `communicationConversationParticipants`,
  `communicationMessages`, `communicationMessageAttachments`,
  `communicationMessageReactions`, `communicationMessageMentions`,
  `communicationMessageReadStates`, `communicationMeetings`,
  `communicationMeetingParticipants`, `communicationCalls`,
  `communicationCallParticipants`, `communicationRecordings`, `communicationPins`,
  `communicationOfficialLetters`, `communicationOutbox` — UUID PKs,
  createdAt/updatedAt, tenant scoping, soft delete where required, §27 indexes,
  conditional unique constraints (direct-key, message/meeting/call idempotency §24,
  active-participant, reaction uniqueness, letter reference).
- Migration `0001_phase8_communication` under `infrastructure/migrations` (house
  convention, `MIGRATION_MODULES`).
- `Django*Repository` implementations for every port; `UserDirectoryOverIdentity`
  and WS authentication via Identity's **application facade** (`principalDirectory`,
  RULE E/F).
- Realtime: `ChannelsRealtimeBroadcaster` (loop-aware, thread-safe),
  `RedisPresenceRepository` (+ in-memory fallback), `NoopMediaRouter` (SFU-ready §12),
  `OutboxDispatcher` (§29).
- Metrics registry §39 with the exact spec names; exposed at
  `GET /api/v1/communication/metrics`.
- Composition root: `infrastructure/container.py` (53 factories).

### Presentation (§8/§30)

- REST: 26 routes under `/api/v1/communication/` (management, history, search,
  scheduling, admin) — thin views, DRF serializers for transport validation only,
  OpenAPI registration, kernel envelope/error codes.
- WebSocket: `/ws/communication/` thin consumer — authenticate (session token §17),
  resolve tenant, bind request context, validate frame, delegate to application
  services, respond. Handlers: subscribe/unsubscribe (membership-checked),
  typing (§31), presence (§7), read (§32), message.send, signal (§11).
- ASGI: `ProtocolTypeRouter` + `AllowedHostsOriginValidator` + `AuthMiddlewareStack`;
  `daphne` first in INSTALLED_APPS so `runserver` serves both HTTP and WS.

## 2. Security & tenancy (§17–§19)

Identity comes exclusively from the verified session (WS) / request context
(REST) — `actorOf()`; client-supplied `tenantId`/`senderId` are never trusted.
Every repository read is tenant-scoped; cross-tenant access surfaces as
`SYS_RECORD_NOT_FOUND` (no existence leak). Permission-gated commands:
`conversation.create`, `conversation.moderate`, `meeting.manage`,
`recording.manage`, `letter.*`. All mutations audited; message bodies/tokens
never logged (§39).

## 3. Verification

- **Unit (29)**: aggregates, state machines, edit/delete policy, thread rules,
  signaling protocol, mention regex, letter workflow.
- **Application (33, ORM-backed)**: the ten §38 critical scenarios —
  unauthorized conversation access, cross-tenant isolation, duplicate message
  (idempotent retry), duplicate participant, invalid meeting state,
  unauthorized recording, call authorization (+ failed-signaling metric),
  edit authorization (window + moderator elevation), delete authorization
  (soft delete semantics), event delivery failure (outbox PENDING → drain) —
  plus channels, presence, search scoping, archive, letters, pins, read receipts.
- **REST integration (8)**: contract over real HTTP with Phase 7 login
  (envelope, 401/403/409 semantics, metrics endpoint).
- **WebSocket integration (5)**: real ASGI application via Channels
  communicator — unauthenticated rejected, subscribe allowed/denied by
  membership, typing relay, read receipts, live send, signaling round-trip,
  unknown-action error envelope.
- **Architecture (164)**: context-opening register updated for `communication`;
  RULE E/F cross-context imports via application facades only; naming
  conventions; migration placement. Total suite: **386 tests OK**.
- Runtime smoke over the real stack (daphne): REST 401s unauthenticated,
  WS handshake reaches the consumer (403 without valid token = expected close).

## 4. Deviations / decisions

- `recipientUnit` (instead of "Department") avoids Organization-context
  vocabulary before that phase opens (architecture guard).
- Soft-deleted message bodies stay in storage (retention/legal §34) but are
  withheld from transport DTOs.
- Direct-message duplicate detection uses a deterministic sorted `directKey`
  with a conditional unique constraint — races can't create double DMs.
- Development channel layer is in-memory; production settings wire
  `channels-redis` via `REDIS_URL` (ADR-023).

## 5. DoD checklist (§41)

Direct/Group/Channels ✓ · presence ✓ · WS ✓ · Redis-ready layer ✓ · domain +
integration events ✓ · outbox ✓ · WebRTC signaling v1 ✓ · 1:1 calls ✓ ·
group-call/SFU port ✓ · screen-share state/audit ✓ · meetings (incl. group) ✓ ·
recording architecture ✓ · notification & AI interfaces (events + ports) ✓ ·
audit ✓ · tenancy ✓ · permissions ✓ · idempotency ✓ · security/integration/WS
tests ✓ · docs + ADR ✓.
