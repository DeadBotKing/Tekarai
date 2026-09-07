# Notification Platform Operations Runbook

## Components

- Django API persists canonical notification/recipient/delivery state.
- Transactional outbox records domain events.
- `CeleryNotificationQueue` publishes identifiers only after database commit.
- Celery workers dispatch due deliveries; beat invokes worker, schedule, digest, escalation, expiry, and cleanup ticks.
- Redis is transport infrastructure, never the notification source of truth.
- Django Channels/WebSocket pushes are best-effort inbox hints; clients reconcile through REST.

## Deployment order

1. Back up the database and verify a stable production `SECRET_KEY`.
2. Deploy code without starting new workers.
3. Run `python manage.py migrate`.
4. Start/restart Celery workers consuming `notifications`.
5. Start/restart Celery beat (exactly one active scheduler).
6. Start/restart API and ASGI instances.
7. Verify health, a canary in-app notification, one configured external channel, and callback receipt processing.

Never rotate `SECRET_KEY` directly: it derives the at-rest token envelope key. Re-encrypt secrets under a replacement key/KMS envelope before changing it.

## Worker commands

```bash
celery -A config worker -l INFO -Q notifications --concurrency=4
celery -A config beat -l INFO
python manage.py runNotificationWorker --once --limit 200
```

Tasks are replay-safe: durable delivery status and attempt records decide whether work is still due. Acknowledgement occurs after execution (`acks_late`), worker loss rejects and requeues, and prefetch is intentionally low.

## Provider callbacks

Endpoint:

```text
POST /api/v1/notifications/provider-webhooks/{tenantId}/{provider}
```

Headers:

- `X-Notification-Timestamp`: Unix epoch seconds
- `X-Notification-Signature`: lowercase HMAC-SHA256 hex of `timestamp + "." + rawBody`

Body fields: `eventId`, `providerMessageId`, `status`, and optional `occurredAt`, `errorCode`, `errorMessage`.

Configure secrets through `NOTIFICATION_WEBHOOK_SECRETS`. Reject or investigate invalid signatures, timestamps outside tolerance, duplicate event IDs with a changed payload hash, unknown message IDs, and callback spikes. Repeated identical events are acknowledged idempotently. State transitions are monotonic, so late `SENT` callbacks cannot downgrade `DELIVERED`.

## Provider configuration

Admin endpoint: `/api/v1/notifications/admin/providers` with `notification.manage`.

Credential material must live in a secret manager. Accepted reference schemes are `vault://`, `env://`, `aws-sm://`, `gcp-sm://`, and `azure-kv://`. API keys/passwords placed in JSON configuration are redacted before persistence. Never log callback bodies, message bodies, addresses, device tokens, auth secrets, or credentials.

Provider implementations are selected by dotted paths in:

- `NOTIFICATION_EMAIL_PROVIDERS`
- `NOTIFICATION_SMS_PROVIDERS`
- `NOTIFICATION_PUSH_PROVIDERS`

The pool attempts providers in order and records the selected provider and external message ID on the delivery.

## Retry and dead letter

Transient failures use exponential backoff and a bounded attempt count. Permanent exhaustion enters `DEAD_LETTER`; it is never silently deleted. Operators should:

1. inspect delivery attempts and provider error codes;
2. fix provider/configuration/address issues;
3. use the authorized retry endpoint;
4. verify progression to `SENT`/`DELIVERED` or a newly explained failure;
5. retain audit evidence.

Do not directly mutate delivery rows.

## Retention

Preview by default:

```bash
python manage.py runNotificationCleanup --tenant-id UUID --actor-id UUID --retention-days 365
python manage.py runNotificationCleanup --tenant-id UUID --actor-id UUID --retention-days 365 --execute
```

The admin API offers the same dry-run/execute behavior. Cleanup is tenant-scoped, records cutoff/counts/requestor, removes eligible operational rows in dependency order, and deliberately preserves notification audit evidence.

## Security controls

- Every user/admin query derives tenant and actor from authenticated context.
- Public provider callbacks authenticate with timestamped HMAC and are separately rate limited.
- Broadcast creation requires `notification.send`; delivery/provider/cleanup operations require `notification.manage`.
- Device tokens and Web Push endpoint/key/auth material use authenticated versioned at-rest envelopes.
- Metadata is size-bounded and recursively redacts secret-like keys.
- Fan-out is hard-limited to 10,000 recipients and writes in 1,000-row batches.
- Synchronous WebSocket hints stop above 100 recipients.

## Monitoring and alerts

Track notification volume, created/delivered/failed counts, delivery latency, channel usage, retries, provider failure rate, read and acknowledgement rates, digest/escalation counts, Celery queue depth, oldest queued age, callback rejection rate, and dead-letter growth.

Alert when:

- oldest high/critical queued delivery exceeds its SLO;
- queue depth grows continuously;
- provider failure/retry rate rises above baseline;
- callbacks fail signature validation or stop arriving;
- dead letters increase;
- active device/subscription count drops unexpectedly;
- worker or beat heartbeat is missing.

## Incident recovery

Redis loss does not erase notifications. Restore Redis, start workers, then run one worker tick/schedule tick; due rows are rediscovered from SQL. After provider outage, restore configuration, requeue dead letters deliberately, and monitor duplicate suppression/provider idempotency. After database restore, reconcile outbox/delivery state before opening external traffic.
