# Notification API (v1)

Base path: `/api/v1/notifications` · Auth: `Authorization: Bearer <accessToken>`
(JWT, same as the rest of the platform). All responses use the standard
envelope `{"data": …, "meta": …}`; errors use the shared error envelope with
stable codes.

The database is the source of truth; the WebSocket channel is a real-time
optimization only (`/ws/notifications/`). After a reconnect, clients
reconcile via REST (`GET ./` + `POST read-bulk`).

## Own notifications (authenticated)

| Method | Path | Description |
|---|---|---|
| GET | `/` | List own notifications. Query: `unread`, `category`, `priority`, `before` (cursor id), `limit` (≤200), `archived`. Meta: `unreadCount`, `hasNext`. |
| GET | `/unread-count` | Badge count. |
| POST | `/read-bulk` | Bulk mark-read (`{"notificationIds": […]}`) — §42 recovery. |
| GET | `/{notificationId}` | Detail incl. per-channel `deliveries` (§25). |
| POST | `/{notificationId}/read` | Mark read (§26 read ≠ acknowledged). |
| DELETE | `/{notificationId}/read` | Mark unread — 409 after acknowledgement. |
| POST | `/{notificationId}/acknowledge` | Acknowledge — 403 when not required, implied read. |
| POST | `/{notificationId}/archive` | Soft delete (reappears with `?archived=true`). |

Example:

```http
GET /api/v1/notifications/?unread=true&limit=20
POST /api/v1/notifications/0192…/acknowledge
```

```json
{"data": {"id": "0192…", "status": "DELIVERED", "category": "MEETING",
          "priority": "HIGH", "readAt": null, "acknowledgedAt": null,
          "channels": ["IN_APP", "PUSH"],
          "deliveries": [{"channel": "PUSH", "status": "DELIVERED",
                          "attemptCount": 1}]},
 "meta": {"unreadCount": 3, "hasNext": false}}
```

## Preferences (§10)

| Method | Path | Description |
|---|---|---|
| GET | `/preferences` | Own rows + valid `levels` and `channels`. |
| PUT | `/preferences` | Replace own set. Most specific wins: TYPE > CATEGORY > GLOBAL. |

```json
{"preferences": [
  {"level": "GLOBAL",   "channel": "EMAIL", "enabled": false},
  {"level": "CATEGORY", "channel": "SMS", "category": "SECURITY", "enabled": true},
  {"level": "TYPE",     "channel": "PUSH", "notificationType": "meeting.invitation", "enabled": true}
]}
```

Tenant org rules (§11) override preferences: FORCED channels are always added,
DENIED channels are always removed; the in-app SECURITY channel can never be
denied.

## Devices (§15)

| Method | Path | Description |
|---|---|---|
| GET | `/devices` | List registrations (`?active=true`). Push tokens are never returned (§33). |
| POST | `/devices` | Register/rotate `{platform, deviceIdentifier, pushToken, provider}` — idempotent per identifier. |
| DELETE | `/devices/{deviceId}` | Revoke — the device stops receiving push immediately. |

## Administration — requires `notification.send`

| Method | Path | Description |
|---|---|---|
| POST | `/admin/send` | Create notifications (`recipientType` USER/ROLE/TENANT/…, `eventId` for dedup §29). |
| GET/POST | `/admin/schedules` | List / create (IMMEDIATE, SCHEDULED, RECURRING, DELAYED, DIGEST — §22). |
| DELETE | `/admin/schedules/{id}` | Cancel a schedule. |
| POST | `/{notificationId}/cancel` | Cancel before delivery. |

## Administration — requires `notification.manage`

| Method | Path | Description |
|---|---|---|
| GET/POST | `/admin/templates` | List (add `?templateKey&language&channel` for the active version chain) / save next version (§18/§19). |
| DELETE | `/admin/templates/{id}` | Deactivate. |
| GET/POST | `/admin/policies` | List / upsert policy (`matchType` TYPE/CATEGORY, channels, retries, cooldown, digest, escalation, bypass — §8). |
| DELETE | `/admin/policies/{id}` | Delete. |
| GET | `/admin/channels` | Channel catalog + provider per channel (§12/§48). |
| GET/POST | `/admin/tenant-rules` | Tenant FORCED/DENIED rules (§11; security guard applies). |
| DELETE | `/admin/tenant-rules/{id}` | Delete rule. |
| GET | `/admin/metrics` | §44 snapshot: notificationsCreated/Delivered/Failed, deliveryLatencyMs, readRate, acknowledgementRate, channelUsage, retryRate, providerFailureRate, notificationVolume. |

## WebSocket (§41)

`GET /ws/notifications/?token=<accessToken>` (or `Authorization: Bearer`).

Frames server→client:

```json
{"type": "notification.ready", "event": {"userId": "…", "heartbeatSeconds": 30}}
{"type": "notification.event", "event": {"name": "notificationDelivered",
 "notificationId": "…", "status": "DELIVERED", "category": "MEETING", "priority": "HIGH"}}
{"type": "reconcile.hint", "event": {"unreadCount": 3, "source": "rest:/api/v1/notifications"}}
```

Client→server: `{"type": "heartbeat"}` → `heartbeat.ok`;
`{"type": "reconcile"}` → `reconcile.hint`. Unauthenticated connect closes
with 4401.
