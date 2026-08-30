# Phase 08 — Communication Platform API (v1)

Base path: `/api/v1/communication` — all endpoints require a Bearer access
token (Phase 07 identity). Live transport is the WebSocket gateway at
`/ws/communication/` (§30); REST below covers management, history,
scheduling and admin.

## Conversations

| Method | Path | Notes |
|---|---|---|
| GET | `/conversations?includeArchived=` | conversations of the caller (+ public channels) |
| POST | `/conversations` | `kind=direct\|group\|channel`; channel needs `code` + `visibility`; `conversation.create` |
| GET | `/conversations/{id}` | detail (channel metadata for channels) |
| PATCH | `/conversations/{id}` | name/description/topic/visibility |
| POST | `/conversations/{id}/archive` | moderators (`conversation.moderate`) |
| POST | `/conversations/{id}/join` | self-join PUBLIC channels only (§4) |
| GET/POST | `/conversations/{id}/participants` | list / add (`role` MEMBER default) |
| PATCH/DELETE | `/conversations/{id}/participants/{userId}` | change role / remove |
| POST | `/conversations/{id}/leave` | owner must transfer first (§6) |
| PATCH | `/conversations/{id}/preferences` | isMuted / notificationLevel |

## Messages

| Method | Path | Notes |
|---|---|---|
| GET | `/conversations/{id}/messages?beforeId=&threadRootId=&limit=` | cursor history (§30) |
| POST | `/conversations/{id}/messages` | body ≤ 8000; `clientRequestId` idempotent (§24); mentions `@user` resolved server-side |
| PATCH | `/messages/{id}` | edit — sender within 15-min window or moderator (§33) |
| DELETE | `/messages/{id}` | soft delete (§34) |
| POST/DELETE | `/messages/{id}/reactions` | unique (message,user,reaction) (§3.5) |
| POST | `/conversations/{id}/read` | bulk read receipt `uptoMessageId` (§32) |
| GET/POST/DELETE | `/conversations/{id}/pins[/{messageId}]` | moderators |
| GET | `/messages/search?q=` | member-scoped search (§22) |

## Meetings & recordings

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/meetings` | schedule (idempotent via `clientRequestId`) |
| GET | `/meetings/{id}` | detail + participants |
| POST | `/meetings/{id}/{start\|end\|cancel\|join\|leave}` | lifecycle (§13) |
| POST | `/meetings/{id}/rsvp` | `{"accepted": bool}` |
| POST | `/meetings/{id}/summary` | AI summary through ports (§21) |
| GET/POST | `/meetings/{id}/recordings` | list / start (`recording.manage`, LIVE only §15) |
| POST | `/recordings/{id}/{stop\|publish}` | publish takes `storageRef` (Documents subsystem) |

## Calls & signaling (§10–§14)

| Method | Path | Notes |
|---|---|---|
| POST | `/calls` | start session — `conversationId` xor `meetingId`; idempotent |
| GET | `/calls/{id}` | participant-visible detail |
| POST | `/calls/{id}/{accept\|reject\|end\|signal}` | REST fallback; live path is WS |

Signaling envelope (`communication.signal.v1`):

```json
{"version": "communication.signal.v1", "kind": "OFFER",
 "callId": "<uuid>", "payload": {"sdp": "..."}}
```

Kinds: `OFFER`, `ANSWER`, `ICE_CANDIDATE`, `CALL_INVITE`, `ACCEPT`,
`REJECT`, `END`, `MEDIA_STATE_CHANGE`.

## Presence, letters, metrics

| Method | Path | Notes |
|---|---|---|
| PUT | `/presence` | `{"status": "ONLINE\|AWAY\|BUSY\|DO_NOT_DISTURB\|IN_MEETING\|OFFLINE"}` (§7, TTL store) |
| GET | `/presence?userIds=a,b` | bulk lookup |
| GET/POST | `/letters` | dedicated §16 model; reference `YYYY-NNNNNN`; `letter.create` |
| POST | `/letters/{id}/{submit\|approve\|sign\|dispatch\|receive}` | approval workflow |
| GET | `/metrics` | §39 counters/gauges |

## WebSocket gateway — `/ws/communication/`

Auth: `Authorization: Bearer <token>` header or `?token=` query param.
Frames are `{"type": ..., "payload": {...}}`:

- `subscribe` / `unsubscribe` — membership-checked group join
- `typing` — ephemeral relay (§31)
- `presence` — heartbeat/status
- `read` — bulk read receipt
- `message.send` — same use case as REST (idempotent)
- `signal` — versioned signaling relay

Server frames: `subscribed`, `typing.started|stopped`, `presence.updated`,
`message.created|edited|deleted`, `message.reactionAdded|Removed`,
`message.read`, `message.pinned|unpinned`, `participant.*`, `meeting.*`,
`call.*`, `signal`, `notification.mention`, plus `error` envelopes with
kernel error codes.
