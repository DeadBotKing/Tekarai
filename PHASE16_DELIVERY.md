# Phase 16 Delivery — Self-Learning Platform

**Release:** Tekarai 0.16.0  
**Completion date:** 2026-09-06  
**Specification:** `docs/Phases/Phase16.md`

فاز ۱۶ به‌صورت کامل و تجمعی روی فازهای ۱ تا ۱۵ پیاده‌سازی شده است. این خروجی یک ماژول ساده ML نیست؛ یک زیرسیستم کامل، tenant-aware، versioned، auditable، reproducible، validation-gated و rollback-capable برای چرخه یادگیری است.

## چرخه تحویل‌شده

```text
OBSERVE → COLLECT → STORE → BUILD DATASET → EXPERIMENT → LEARN
→ EVALUATE → VALIDATE → APPROVE → CANARY DEPLOY → MONITOR
→ FEEDBACK → RELEARN
```

و در خرابی:

```text
MONITOR → DETECT FAILURE/DRIFT → ROLLBACK → RESTORE STABLE VERSION
```

## اجزای اصلی

- LearningExperience immutable و traceable
- Dataset/Sample versioning، source validation و deterministic hash
- Experiment و Run مستقل و کاملاً reproducible
- Artifact storage غیرقابل overwrite با SHA-256
- ModelVersion و PolicyVersion مستقل
- Evaluation و baseline comparison
- Validation برای performance، regression، safety، leakage، compatibility، latency، resource و business constraints
- Human approval/rejection با separation of duties
- Deployment مرحله‌ای 5% → 25% → 50% → 100% با metric gate در هر مرحله
- Snapshot و rollback به آخرین نسخه پایدار
- Feedback انسانی/سیستمی/کسب‌وکاری
- Drift detection برای Data، Concept، Prediction و Performance
- Celery jobهای durable/idempotent و اجرای خارج از HTTP
- Events، Metrics و Audit immutable
- Permission، rate limit، tenant isolation و payload security
- ۱۸ جدول persistence با migration برگشت‌پذیر
- API، تست، runbook و release documentation

## نتایج تست و Quality Gate

- تست‌های اختصاصی فاز ۱۶: **15/15 موفق**
- کل تست‌های Backend: **2263/2263 موفق**
- Django Check: **موفق**
- Migration Drift: **بدون تغییر معوق**
- Migration Forward: ساخت هر **۱۸ جدول** موفق
- Migration Rollback: حذف امن هر **۱۸ جدول** موفق
- Ruff Check کل Repository: **موفق**
- Ruff Format: **667 فایل، کاملاً منطبق**
- Mypy کل Repository: **627 فایل، بدون خطا**
- Mypy فاز ۱۶ بدون ignore: **54 فایل، بدون خطا**
- Python Compile: **موفق**
- Pip Dependency Check: **موفق**
- Git Diff Whitespace Check: **موفق**

## مستندات

- گزارش اجرا: `docs/Phases/Phase16Report.md`
- API: `docs/api/selfLearningPlatform.md`
- Runbook عملیاتی: `docs/operations/selfLearningPlatform.md`
- Release notes: `docs/releases/Phase16.md`

## راه‌اندازی

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements/base.txt -r requirements/development.txt
.venv/bin/python manage.py migrate
```

Workerهای Production:

```bash
celery -A config worker -l INFO -Q learning.training
celery -A config worker -l INFO -Q learning.monitoring
celery -A config beat -l INFO
```

برای Production باید storage adapter پایدار و immutable، engine مورد تأیید، محدودیت منابع worker، مانیتورینگ و backup هماهنگ SQL/Artifact مطابق runbook تنظیم شود.

## Archive

فایل نهایی `Tekarai-Phase16-complete.zip` است. فایل checksum استاندارد `Tekarai-Phase16-complete.zip.sha256` پس از integrity test در کنار ZIP تحویل می‌شود. نگهداری digest در sidecar از self-reference و تغییر hash بر اثر قراردادن hash داخل خود آرشیو جلوگیری می‌کند.
