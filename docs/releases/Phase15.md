# Tekarai 0.15.0 — Notification Platform

**Release date:** 2026-09-06  
**Specification:** `docs/Phases/Phase15.md`

## Highlights

Phase 15 turns notifications into a durable, tenant-isolated platform rather than an HTTP side effect.

- Canonical notification, recipient, and per-channel delivery records with explicit lifecycle timestamps.
- In-app inbox/read, unread, archive, dismiss, acknowledgement, search, filtering, and cursor pagination.
- Tenant/user/category/type/channel preference hierarchy, quiet hours, mandatory security/system bypass, digests, escalation, deduplication, and anti-spam controls.
- Immutable, versioned, multilingual templates with safe variable rendering.
- Policy/event/outbox-based creation and replay-safe asynchronous dispatch.
- Celery 5.5 worker/beat integration backed by Redis in production and deterministic eager execution in tests.
- Persistent retries with exponential backoff, attempt history, dead-letter state, manual retry, and provider failover ports.
- Email, SMS, mobile/desktop/browser/Web Push adapters plus WebSocket inbox optimization. Database state remains the source of truth.
- Signed provider callbacks with HMAC-SHA256, replay tolerance, payload-conflict detection, idempotent receipts, and monotonic delivery transitions.
- Encrypted device tokens and Web Push subscription material at rest; legacy tokens are encrypted by migration.
- Tenant-scoped provider configuration using secret-manager references only.
- Retention cleanup with dry-run mode, immutable cleanup/audit evidence, and preserved notification audit rows.
- Notification-specific authorization and rate-limit policies, metadata redaction, payload bounds, tenant isolation, and bounded fan-out.

## Schema

Migrations:

1. `notifications.0003_phase15_platform`
2. `notifications.0004_alter_notificationdevicemodel_pushtoken`
3. `notifications.0005_encrypt_legacy_device_tokens`

Apply before starting 0.15 workers:

```bash
cd backend
python manage.py migrate
```

The token-encryption migration is reversible and processes rows in bounded iterator batches.

## Runtime

Production requires Redis and separate worker/beat processes:

```bash
celery -A config worker -l INFO -Q notifications
celery -A config beat -l INFO
```

Set `REDIS_URL`, a strong stable `SECRET_KEY`, provider implementation paths, and per-provider callback secrets. See `docs/operations/notificationPlatform.md` and `backend/.env.example`.

## Compatibility

Phase 9 single-recipient notifications remain readable. Phase 15 search spans the Phase 9 and canonical Phase 12/15 stores while migration proceeds. `BROWSER` remains a compatible alias; `WEB_PUSH` is the canonical browser push channel.

## Validation

The Phase 15 focused suite covers lifecycle, HMAC callbacks, idempotency/conflicts, encrypted secrets, secret references, tenant-scoped search, 1,000-recipient fan-out/query bounds, cleanup/audit preservation, Celery post-commit publication, authentication, authorization, and API callback contracts.

The full backend suite runs **2,248 tests and all pass**. Architecture guards were evolved for standard Celery task discovery and later-phase context composition, while retaining layer-placement enforcement.
