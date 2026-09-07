# Notification Platform API (Phase 15)

Base path: `/api/v1/notifications`

All successful responses use `{ "success": true, "data": ..., "meta": ... }`. Authenticated routes derive tenant/user from the bearer session; tenant IDs in request bodies are not trusted.

## Recipient APIs

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Inbox list with existing Phase 9 filters/pagination |
| GET | `/search` | Full-text title/body search plus `type`, `status`, `readState`, `channel`, `dateFrom`, `dateTo`, `beforeId`, `limit` |
| GET | `/unread-count` | Recipient unread count |
| POST | `/{id}/read` | Mark recipient row read |
| POST | `/{id}/unread` | Mark unread |
| POST | `/{id}/archive` | Archive |
| POST | `/{id}/dismiss` | Dismiss |
| POST | `/{id}/acknowledge` | Acknowledge where required |
| GET/PUT | `/preferences` | Read/update preference hierarchy |
| GET/POST | `/devices` | List/register push device |
| POST | `/devices/{id}/revoke` | Revoke device immediately |
| GET/POST | `/push-subscriptions` | List/register encrypted Web Push subscription |

Search is recipient-scoped and spans legacy Phase 9 and canonical Phase 12/15 rows. The result never exposes recipient addresses, device tokens, Web Push endpoints/keys, credentials, or provider payloads.

## Canonical/broadcast APIs

| Method | Path | Permission |
|---|---|---|
| GET | `/broadcasts` | authenticated recipient query |
| POST | `/broadcasts` | `notification.send` |
| GET | `/broadcasts/{id}` | recipient or authorized admin |
| POST | `/broadcasts/{id}/read-state` | authenticated recipient |
| GET | `/deliveries` | `notification.manage` |
| POST | `/deliveries/{id}/retry` | `notification.manage` |
| GET/POST | `/rules` | `notification.manage` |
| POST | `/events` | `notification.send` |

Broadcast fan-out is capped at 10,000 recipients. Use idempotency keys for retried producer requests.

## Provider and operations APIs

| Method | Path | Authentication |
|---|---|---|
| POST | `/provider-webhooks/{tenantId}/{provider}` | timestamped HMAC signature |
| GET/POST | `/admin/providers` | `notification.manage` |
| POST | `/admin/cleanup-runs` | `notification.manage` |
| GET | `/admin/metrics` | notification admin permission |

### Callback example

```json
{
  "eventId": "evt_123",
  "providerMessageId": "msg_456",
  "status": "DELIVERED",
  "occurredAt": "2026-09-06T12:00:00Z",
  "errorCode": "",
  "errorMessage": ""
}
```

Signature input is the exact raw request body. See `docs/operations/notificationPlatform.md` for header and HMAC details.

## Error behavior

- `401`: missing/invalid authentication
- `403`: missing `notification.send`/`notification.manage` or cross-tenant access
- `409`: idempotency event ID reused with a different payload
- `422`: malformed input, invalid state transition, signature/timestamp rejection, invalid provider reference
- `429`: endpoint policy exceeded

Provider callback duplicates with the same event ID and payload are successful idempotent acknowledgements, not errors.
