# Phase 13-P — Execution Report (Async Execution، Queue و Worker)

**تاریخ اجرا:** 2026-09-05
**قرارداد:** [`Phase13-P.md`](Phase13-P.md)
**نتیجه:** `GREEN — Phase 13-M may begin.`

---

## 1. خلاصه

زیر‌فاز P کامل ساخته، تست و تحویل شد: صف durable با پشتوانهٔ دیتابیس
(بدون Celery/Redis — هیچ وابستگی جدیدی اضافه نشد)، ورکر lease-محور با
retry نمایی و dead-letter، حمل durable رویدادهای §36 از روی همان صف، پل
N→P (`QueuedUsageEventSink`) و P→O (مشترک حسابرسی `USAGE_RECORDED`) بدون
دست‌خوردن به کد N و O، ثبت حسابرسی هر گذار کار با ۴ action جدید واژگان O،
جدول `aiJobs` با مهاجرت `0004_queueWorker`، دستور مدیریتی `runAiWorker`
هم‌الگوی worker فاز ۹، و تنظیمات `AI_QUEUE_*`/`AI_WORKER_*`.

- تست‌های جدید: **۶۵** (واحد ۳۰ + کاربردی ۲۰ + یکپارچگی ۱۵) — همه سبز؛
- کل سوئیت: **۱۰۳۴ تست** با دقیقاً همان **۶ خطای پیشین** درخت pristine
  (تست‌های architecture/context فازهای قدیمی — هیچ violation جدیدی از
  فایل‌های P گزارش نشد)؛
- کیفیت سطح P: `ruff check` سبز، `ruff format` سبز، `mypy` سبز؛
  `models.py` روی همان ۱۲۹ خطای پیشین؛ `makemigrations --check` بدون drift؛
  `django check` تمیز؛
- اثبات عمودی روی SQLite واقعی: submit → ‏`runAiWorker --once` →
  settle + زنجیرهٔ audit (`JOB_ENQUEUED/STARTED/FAILED`).

## 2. فایل‌های تحویلی

**دامنه (خالص):** `queueTypes.py` (واژگان ۸ kind و ۶ status + ریاضی
backoff)، `jobRecords.py` (موجودیت `AIJob`)، `jobQueue.py`
(`JobQueueService` + `JobOutcome`/`JobDescriptor`/`JobFilter` +
`jobFingerprint`)، `eventBus.py` (`AIEventEnvelope` + `EventBusService`)،
`queuePorts.py` (پورت‌های `JobStore`/`JobHandler`/`EventBusPort`)؛
**اپلیکیشن:** `queueService.py` (`QueueApplicationService` +
`QueuedEventBus` + `QueuedUsageEventSink` + `AuditEventSubscriber`)؛
**زیرساخت:** `AIJobModel`، `queueRepositories.py` (`DjangoJobStore`)،
مهاجرت `0004_queueWorker`، دستور `runAiWorker.py`؛
**پیکربندی:** ۱۰ کلید `AI_QUEUE_*`/`AI_WORKER_*` در `base.py` و
`.env.example`؛ **خطاها:** ۶ خطای جدید `AIJob*`/`AIEvent*`؛
**تست‌ها:** `testPhase13QueueWorker.py`، `testPhase13QueueUseCases.py`،
`testPhase13QueueContract.py`.

## 3. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **یکتای DB با sentinel:** به‌جای «بدون constraint» اولیه،
   `unique_together (tenantId, idempotencyKey)` با sentinel ‏`none:<jobId>`
   برای کلید خالی — race-safe روی همهٔ backendها (از جمله MSSQL بدون
   partial index)؛ برخورد هم‌زمان = بازگشت رکورد موجود (idempotent-save).
   دقت شد `save` بعد از `IntegrityError` در تراکنش تازه بخواند (تراکنش
   مسموم قابل query نیست).
2. **`claimRow` بدون row-lock:** انتخاب نامزد + یک `UPDATE` نگهبانی‌شده
   (`status` هنوز PENDING/RUNNING و lease آزاد) + بازخوانی فقط سطرهای برده‌شده —
   روی SQLite/MSSQL/Postgres کار می‌کند و نیازی به `select_for_update`
   ندارد.
3. **reclaim کار RUNNING با lease منقضی** (مکانیزم timeout سطح P) در هر دو
   مسیر حافظه‌ای و Django.
4. **`importJob` با بردِ تازه (later-wins):** کپی تازهٔ claimشده جایگزین
   کپی حافظه می‌شود تا settle روی snapshot مانده انجام نشود.
5. **`forget` + purge دو مرحله‌ای:** حافظهٔ coordinator بعد از purge از
   روح‌ها پاک می‌شود (با پاک‌سازی binding کلید idempotency)؛ ارسال مجدد
   همان کلید بعد از purge یک کار تازه می‌سازد.
6. **exception handler = شکست retryable** (محافظه‌کار)؛ refusal قطعی
   (handler غایب، deny حکمرانی، پاکت خراب/ناهم‌خوان) = `FAILED` بدون retry؛
   اتمام تلاش‌ها = `DEAD`.
7. **`evaluateGovernance` روی deny raise می‌کند** (`AIGovernanceDenied` —
   fail-closed)؛ ورکر آن را `DENIED` می‌خواند و بقیهٔ exceptionها را
   `GOVERNANCE_ERROR` (retryable).
8. **لغو روی کانال `JOB_FAILED` با `errorCode=CANCELLED`** تا واژگان ۴تایی
   بماند (مستند در قرارداد §5).

## 4. باگ‌هایی که تست‌ها گرفتند (۶ باگ واقعی، همه اصلاح و پوشش‌دار)

1. اعتبارسنجی kind بیرون از قرارداد خطا بود (`ValidationFailedError` خام)؛
2. کار `RUNNING` با lease منقضی reclaim نمی‌شد (خلاف §4.3)؛
3. `importJob` کپی تازهٔ claim را نادیده می‌گرفت (۱۱ خطای application)؛
4. `save` بعد از `IntegrityError` در همان تراکنش query می‌زد؛
5. SELECT نامزدهای `claimRow` شرط lease نداشت (claim تکراری همان کار)؛
6. کپی حافظه بعد از purge روح می‌ماند (`listJobs` رکورد پاک‌شده را نشان
   می‌داد)؛

علاوه بر این ۳ باگ تست (limit اشتباه claim، runAt آینده در تست ordering،
ترتیب assertion audit) اصلاح شد.

## 5. تنها اصلاح مشترک با O (ثبت‌شده در هر دو سند)

۴ action چرخه‌عمر کار (`JOB_ENQUEUED/STARTED/COMPLETED/FAILED`) به واژگان
`AUDIT_ACTIONS` افزوده شد (۱۵→۱۹) + شمارش تست واحد O به‌روز شد؛ یادداشت
اصلاحیه در `Phase13-O.md` §4.2. هیچ کد دیگری از N/O لمس نشد.

## 6. گیت‌ها (اجرا شده، همه سبز)

- `tests.unit.testPhase13QueueWorker`: ۳۰/۳۰؛
- `tests.application.testPhase13QueueUseCases`: ۲۰/۲۰ (شامل end-to-end
  sink→queue→worker→audit)؛
- `tests.integration.testPhase13QueueContract`: ۱۵/۱۵؛
- سوئیت کامل: ۱۰۳۴ تست، ۶ خطای پیشین بدون تغییر؛
- `ruff check` / `ruff format --check` / `mypy` روی هر ۱۹ مسیر سطح P سبز؛
- `models.py`: همان ۱۲۹ خطای پیشین (افزودهٔ P صفر)؛
- `makemigrations ai --check`: بدون drift؛ `django check`: تمیز؛
- smoke دستی `runAiWorker --once` روی فایل SQLite واقعی با migrate کامل.

## 7. محدودیت‌های ثبت‌شده (به M/Z منتقل می‌شود)

ترتیب تحویل رویداد تضمین نمی‌شود؛ تکرار تحویل ممکن است (مشترکین باید
idempotent باشند)؛ طبقه‌بندی retryable/permanent خطاهای provider و timeout
اجرا با M است؛ ارسال هم‌زمان تکراریِ یک کلید از دو process ممکن است دو سطر
بسازد (پنجرهٔ race پذیرش — حل با serialize در Z یا M)؛ worker تک‌فرایندی
چندنخی‌امن نیست، چند process با lease دیتابیسی امن است.

**تحویل:** کامیت `Phase 13-P` + فایل `Tekarai-Phase13-P.zip`.
