# Phase 13-Z — Execution Report

**تاریخ اجرا:** 2026-09-06  
**قرارداد:** [Phase13-Z.md](Phase13-Z.md)  
**نتیجه:** `GATE_Z=GREEN — PHASE_13=COMPLETE`

## ۱. خلاصهٔ تحویل

زیر‌فاز Z مرز انتشار AI Platform را تکمیل کرد. API عمومی نسخه‌دار اکنون
Registry، Versioning، اجرای Sync/Async، Trace گام‌ها، Approval Queue، Job status
و Release Readiness را از طریق Application Layer ارائه می‌دهد. Worker فاز P
نوع `AGENT_RUN` را اجرا می‌کند و Permission را در لحظهٔ Execute دوباره از
Identity می‌پرسد.

۹ تست عمودی جدید از HTTP login واقعی تا ORM و Provider قطعی اجرا شدند. کل Suite
از ۲۲۱۰ به **۲۲۱۹ تست** رسید و همان **۶ شکست baseline پیشین** باقی ماند؛ هیچ
شکست جدیدی اضافه نشد.

## ۲. فایل‌های جدید

| فایل | خط | نقش |
|---|---:|---|
| `backend/apps/ai/presentation/api/serializers.py` | 63 | اعتبارسنجی Inputهای Registry/Run/Approval |
| `backend/apps/ai/presentation/api/views.py` | 370 | مرز نازک REST و DTO امن |
| `backend/apps/ai/presentation/api/urls.py` | 51 | Routeهای `/api/v1/ai/` |
| `backend/apps/ai/infrastructure/container.py` | 174 | Composition Root و Readiness |
| `backend/apps/ai/infrastructure/agentRuntime.py` | 178 | Provider caller و Live Permission adapters |
| `backend/apps/ai/application/services/agentJobService.py` | 62 | Handler نوع `AGENT_RUN` |
| `backend/apps/ai/management/commands/checkPhase13Release.py` | 32 | Release gate عملیاتی |
| `backend/release_phase13.sh` | 17 | گیت Linux |
| `backend/release_phase13.ps1` | 14 | گیت Windows |
| `backend/tests/integration/testPhase13ReleaseApiContract.py` | 202 | ۹ تست API/Security/Async/Approval/Readiness |
| `docs/Phases/Phase13/Phase13-Z.md` | 283 | قرارداد و Runbook کامل Z |
| `docs/releases/Phase13.md` | Release notes | راهنمای Upgrade و Compatibility |

## ۳. فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `config/urls.py` | Mount کردن `/api/v1/ai/` |
| `config/settings/base.py` | Provider/Model پیش‌فرض و opt-in fake provider |
| `config/settings/testing.py` | Provider قطعی آفلاین برای تست |
| `.env.example` | سه کلید Z بدون Secret |
| `queueTypes.py` | افزودن Kind بستهٔ `AGENT_RUN` |
| `runAiWorker.py` | استفاده از Composition Root و ثبت Handler Z |
| `permissionCatalog.py` | پنج Action AI و Role presetها |
| `agentService.py` | اصلاح Clock تزریقی برای Replay/Test قطعی |
| `testPhase13QueueWorker.py` | تثبیت واژگان نسخه‌شدهٔ Queue |
| `docs/Phases/Phase13.md` | وضعیت نهایی و DoD کامل |
| `docs/Phases/Phase13/README.md` | Z و گزارش آن |
| `backend/pyproject.toml` | نسخهٔ Release از 0.1.0 به 0.13.0 |

## ۴. API تحویل‌شده

- ۵ مسیر Registry/Version/Lifecycle؛
- ۴ مسیر Run و Step؛
- ۳ مسیر Approval؛
- ۳ مسیر Job؛
- ۱ مسیر Release Readiness؛
- در مجموع ۱۶ الگوی Route با Methodهای کنترل‌شده.

همهٔ پاسخ‌ها Envelope استاندارد دارند، Correlation ID را حفظ می‌کنند، Tenant را
فقط از Context می‌گیرند و Descriptorهای عمومی Instructions و Job Payload را
نمایش نمی‌دهند.

## ۵. تصمیم Async و Approval

- Async فقط با Idempotency Key پذیرفته می‌شود؛
- ورودی پیش از صف با `redactInput` پاک‌سازی می‌شود؛
- Worker هویت را از Job بازسازی می‌کند اما مجوز را زنده دوباره بررسی می‌کند؛
- `PENDING approval` یک Business outcome موفق برای Queue است و Retry نمی‌شود؛
- صف Approval به شکل Pull API تحویل شد؛ Notification خودکار تا تعریف Assignment
  Policy انجام نمی‌شود تا داده به Approver اشتباه نشت نکند؛
- High-risk flow با درخواست‌کننده و Reviewer دوم در HTTP test واقعی اثبات شد.

## ۶. اصلاح پایداری کشف‌شده در Gate

تست‌های Y یک `now` ثابت تزریق می‌کردند، ولی Budget در نبود `clock` صریح به ساعت
واقعی برمی‌گشت. چند ساعت بعد از `CLOCK` ثابت، Run پیش از اولین Model Call با
`AI_AGENT_BUDGET_EXCEEDED` شکست می‌خورد. `_currentClock` اکنون به ترتیب از
`clock`، سپس `now` تزریقی و در نهایت UTC واقعی استفاده می‌کند. این اصلاح باعث
قطعی‌شدن Replay/Worker/Test شد؛ تمام ۴۵ تست کاربردی Y دوباره سبز شدند.

## ۷. شواهد تست

| Gate | نتیجه |
|---|---|
| تست API جدید Z | **۹/۹ سبز** |
| بستهٔ Agent/Queue/Z | **۱۹۶/۱۹۶ سبز** |
| کل Suite | **۲۲۱۹ تست، ۶ شکست baseline** |
| Django system check | ۰ issue |
| AI migration drift | `No changes detected in app 'ai'` |
| Readiness در Testing | `ready=true` |
| Secret literal scan روی سطح جدید | Clean |
| `git diff --check` | Clean |

شش شکست baseline دقیقاً همان بدهی ثبت‌شده در Y هستند: دو قالب/فایل legacy در
`apps/ai` و چهار تست معماری/نام‌گذاری وابسته. Z شکست هفتم ایجاد نکرد.

## ۸. Quality Debt Delta

برای جلوگیری از ادعای مبهم، HEAD اولیه (`2646d11`) در Worktree جدا با همان
Interpreter و همان Command اندازه‌گیری شد:

| معیار | Pristine HEAD | پس از Z | Delta |
|---|---:|---:|---:|
| Ruff | 293 | 293 | **0** |
| Mypy | 583 | 583 | **0** |

فایل‌های ایجاد/تغییر‌یافتهٔ Z با Ruff و Format به‌طور مستقل کاملاً تمیزند؛ Mypy
هیچ خطایی با Path مربوط به فایل‌های جدید Z گزارش نکرد.

## ۹. Migration

Z Schema جدیدی نساخت؛ Migration نهایی AI همان `0012_agentPlatform` است.

- اجرای Migrationهای `ai.0001` تا `ai.0012` در DB تست: موفق؛
- `makemigrations ai --check --dry-run`: بدون تغییر؛
- Drift سراسری مخزن در `communication.0005` از baseline است و به Z/AI مربوط نیست؛
- Readiness از `MigrationExecutor` استفاده می‌کند و فقط Migrationهای معوق AI را
  Fail می‌کند.

## ۱۰. امنیت اثبات‌شده

1. درخواست بدون Bearer با 401 رد شد؛
2. Actionهای جداگانه برای Read/Manage/Run/Approve/Tool وجود دارد؛
3. Tenant از Body قابل تزریق نیست؛
4. Foreign Tenant definition در List دیده نشد؛
5. `apiKey` داخل Job با `[REDACTED]` ذخیره شد؛
6. Job API هیچ Payloadی برنگرداند؛
7. Fake Provider در Production پیش‌فرض خاموش است؛
8. Worker مجوز زمان Submit را Trust نمی‌کند؛
9. View هیچ ORM یا Provider SDK را import نمی‌کند.

## ۱۱. عملیات Release

دو Script متناظر Linux و Windows اضافه شد. ترتیب Gate:

1. `check --deploy`؛
2. `migrate --plan`؛
3. `makemigrations --check`؛
4. `checkPhase13Release`؛
5. Unit/Application/Integration tests؛
6. Ruff، Format و Mypy؛
7. چاپ `GATE_Z=GREEN` فقط پس از موفقیت همهٔ مراحل.

## ۱۲. وضعیت نهایی

تمام معیارهای قرارداد Z تحقق یافتند؛ DoD سند مادر به‌روز شد و Package A تا Z
کامل است.

**نتیجه:** `GATE_Z=GREEN — PHASE_13=COMPLETE`
