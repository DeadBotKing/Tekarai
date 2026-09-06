# Phase 14 — Enterprise Communication Platform completion report

**Status:** Complete  
**Release:** 0.14.0  
**Specification:** `docs/Phases/Phase14.md`  
**Bounded context:** `backend/apps/communication`

## Delivery strategy

Phase 14 is a consolidation and completion phase. Tekarai already delivered the communication foundation in Phase 8, rich meetings/WebRTC/transcription in Phase 10, and enterprise governance in Phase 11. Phase 14 therefore preserves those production-tested vertical slices and closes the remaining requirements without duplicating or replacing the bounded context.

## Specification gap matrix

| Phase 14 area | Delivery source | Completion evidence |
|---|---|---|
| Conversations, direct/group chat, channels | Phases 8/10 | `Conversation`, participants, channel profile/membership, REST and WebSocket APIs |
| Membership and roles | Phases 8/10/11 | owner/admin/moderator/member/guest controls, join/leave/preferences/capabilities |
| Message lifecycle | Phases 8/10/11 | send, reply, thread root, revisions, soft delete, reactions, pins, mentions |
| Delivery/read state | Phases 8/11 | read state and distinct recipient delivery state |
| Forwarding | **Phase 14** | original-message UUID, forwarding actor/time, bounded historical snapshot, idempotent command |
| Attachments | Phases 8 + **Phase 14 hardening** | separate metadata aggregate; MIME, extension, size, checksum and malware verdict validation; server-issued tenant key |
| Presence and typing | Phases 8/10 | Redis/in-memory ephemeral presence, TTL/privacy and WebSocket typing events |
| WebSocket security | Phases 8/10/11 | authenticated tenant context, group authorization, versioned signaling |
| Calls/WebRTC | Phases 8/10 | call lifecycle, participants, signaling relay, replaceable media-router port |
| Meetings and permissions | Phases 8/10/11 | participants, capabilities, room/session, host/co-host governance |
| Screen sharing | Phase 11 | capability checks, state, signaling and audit |
| Recording | Phases 8/10 + **Phase 14 schema completion** | policy-driven lifecycle plus storage key, file size and checksum metadata |
| Transcription | Phase 10 | request/complete pipeline and timed speaker segments |
| AI summaries/action items | Phases 10/11 | summaries, confidence, human review and dispatch boundary |
| Unified search | **Phase 14** | message, conversation, channel, attachment, meeting and transcript scopes; membership and tenant filtering before retrieval |
| Audit/outbox/notifications | Phases 8/11 + Phase 14 events | immutable audit integration, transactional outbox, notification consumers |
| Retention/legal hold | Phase 11 + **Phase 14 execution** | preview/execute service, run ledger, CLI/API, dependent cleanup, conversation/user/meeting/recording/transcript hold exclusions |
| Moderation | Phase 11 | report/review workflow and communication policy |
| Official communication | Phases 8/11 | separate letters and official-message governance; not conflated with chat |
| Offline/idempotency | Phase 8 + **Phase 14 completion** | client-generated UUID, command request IDs, bounded batch replay, immutable receipt and changed-payload conflict |
| Rate limits/security | Phases 8/10/11 + Phase 14 hardening | REST/WS throttles, object authorization, validation, tenant isolation, storage-key protection |
| Performance | Phases 8 + **Phase 14 optimization** | cursor-style `beforeId`, bounded pages, bulk mentions/reactions/attachments, constant query-count regression test |

## New Phase 14 architecture

### Domain

- `Message` carries optional forwarding metadata while the original identity remains authoritative.
- `AttachmentPolicy` performs framework-free security validation and server key generation.
- `syncRequestHash` canonicalizes a bounded operation batch for exact replay detection.
- Closed vocabularies protect search scopes, scan states, classifications and sync operation types.
- Recording metadata now includes `storageKey`, `fileSizeBytes` and SHA-256 `checksum`.

### Application

- `ForwardMessageUseCase`
- `AttachmentPreflightUseCase`
- `UnifiedSearchUseCase`
- `OfflineSyncUseCase`
- `RunRetentionUseCase`

Every identity and tenant is obtained from request context; payload identity is never trusted. Forwarding requires active membership in source and target conversations. Search authorization is applied before querying content. Retention requires the existing communication moderator permission.

### Infrastructure

Migration `communication.0005_phase14_completion` adds:

- forwarding reference/snapshot columns;
- attachment security metadata;
- recording storage integrity metadata;
- immutable offline sync receipts;
- immutable retention run summaries;
- reconciliation of the previously detected channel profile schema drift.

`UnifiedCommunicationSearchDjango` applies tenant and membership filters to every scope. `CommunicationRetentionStoreDjango` executes a transaction, deletes dependent message/transcript metadata first, and excludes active legal holds. `OfflineSyncReceiptStoreDjango` enforces `(tenant, user, clientBatchId)` uniqueness under races.

### REST API

All routes are under `/api/v1/communication/` and require authentication:

| Method | Route | Purpose |
|---|---|---|
| `POST` | `attachments/preflight` | validate metadata and issue a tenant-bound server storage key |
| `POST` | `messages/{messageId}/forward` | idempotent reference-preserving forward |
| `GET` | `search?q=...&scope=...` | permission-aware unified search |
| `POST` | `sync` | bounded offline operation replay with conflict results |
| `POST` | `retention/runs` | preview or execute governed retention |

`POST conversations/{id}/messages` and WebSocket `message.send` additionally accept `clientMessageId` and secured attachment metadata.

### Operations

Preview retention (safe default):

```bash
python manage.py runCommunicationRetention \
  --tenant-id <tenant-uuid> --actor-id <authorized-user-uuid> --days 2555
```

Execute only after reviewing preview counts:

```bash
python manage.py runCommunicationRetention \
  --tenant-id <tenant-uuid> --actor-id <authorized-user-uuid> --days 2555 --execute
```

## Security decisions

1. An attachment must have an allow-listed MIME type and matching extension.
2. Size must be positive and within the configured maximum.
3. Checksum must be a valid SHA-256 hex digest.
4. A clean malware-scan verdict is mandatory by default.
5. Clients cannot choose arbitrary paths; persisted keys must use `communication/{tenantId}/...`.
6. Deleted messages cannot be forwarded.
7. Forward snapshots are bounded to prevent unbounded amplification.
8. Offline batches are capped at 100 unique operations.
9. Reusing a batch ID with changed content returns a conflict.
10. Search never performs cross-tenant or pre-authorization retrieval.
11. Physical retention deletes only soft-deleted expired messages and respects every applicable active hold.

## Tests and release gates

The Phase 14 suites cover forwarding membership/idempotency, client-generated IDs, file security, security metadata persistence, cross-tenant search exclusion, offline exact replay/conflicts, retention preview/execution/legal holds, constant query count, REST happy paths, input rejection and authentication.

Communication regression covers all Phase 8, 10, 11 and 14 unit/application/API/WebSocket suites. Final repository-wide results and known baseline exceptions are recorded in `PHASE14_DELIVERY.md`.
