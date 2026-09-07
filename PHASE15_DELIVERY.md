# Phase 15 Delivery — Notification Platform

**Release:** Tekarai 0.15.0  
**Completion date:** 2026-09-06  
**Specification:** `docs/Phases/Phase15.md`

فاز ۱۵ به‌صورت تجمعی روی تمام فازهای قبلی پیاده‌سازی شده است. خروجی شامل دامنه مستقل اعلان، inbox و وضعیت خواندن، ترجیحات و policyها، templateهای نسخه‌دار و چندزبانه، event/outbox، Celery/Redis، retry/dead-letter، کانال‌ها و providerها، Web Push/WebSocket، زمان‌بندی و انقضا، digest/escalation/deduplication/rate limit، webhook امن provider، audit/metrics، tenant isolation، migrationها، تست‌ها و مستندات عملیاتی است.

## Release contents

- Backend source and all cumulative prior phases
- Notification migrations `0003`–`0005`
- Celery worker/beat configuration and tasks
- Phase 15 domain/application/infrastructure/presentation code
- Focused application/integration/security/performance tests
- API guide: `docs/api/notificationPlatform.md`
- Operations runbook: `docs/operations/notificationPlatform.md`
- Release notes: `docs/releases/Phase15.md`
- Execution report: `docs/Phases/Phase15Report.md`

## Verification summary

- Phase 15 focused tests: **15/15 passed**
- Phase 12 lifecycle regression: **23/23 passed**
- Django system check: **passed**
- Migration drift check: **passed — no changes**
- Migration forward encryption/reverse decryption test: **passed**
- Python compilation: **passed**
- Focused Phase 15 Ruff: **passed**
- Full backend: **2,248/2,248 passed**.

## Install / migrate

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements/base.txt -r requirements/dev.txt
.venv/bin/python manage.py migrate
```

Production worker processes:

```bash
celery -A config worker -l INFO -Q notifications
celery -A config beat -l INFO
```

Configure a stable strong `SECRET_KEY`, `REDIS_URL`, provider implementation paths, secret-manager references, and `NOTIFICATION_WEBHOOK_SECRETS` before external delivery. Follow the deployment order and key-rotation warning in the operations runbook.

## Archive integrity

The final archive is `Tekarai-Phase15-complete.zip`. Its SHA-256 is provided alongside the delivered file after packaging and integrity verification.
