# Phase 13-P — Async Execution، Queue و Worker

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** P از A تا Z
**وضعیت:** COMPLETED — Queue/Worker Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§8، §13، §28، §35، §36، §38، §40، §42، §43، §45، §46)
**قراردادهای قبلی:** [G](Phase13-G.md) (idempotency)، [K](Phase13-K.md) (ایزولاسیون)،
[N](Phase13-N.md) (حامل `AIUsageRecorded` و sink)، [O](Phase13-O.md) (دفتر حسابرسی،
حکمرانی، واژگان action)
**گزارش اجرا:** [`Phase13-P-ExecutionReport.md`](Phase13-P-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز P اجرای ناهمگام عملیات سنگین AI (§35: تحلیل سند، رونویسی، گزارش
بزرگ، embedding، ایندکس دانش، پیش‌بینی بزرگ) را می‌سازد: یک صف durable
پشتوانه-دیتابیس (بدون وابستگی به Redis/Celery)، ورکر lease-محور با retry
نمایی و dead-letter، حمل durable رویدادها (§36) از طریق همان صف، و ثبت
حسابرسی هر گذار کار از روی قرارداد O — همه tenant-scoped، idempotent
(§45) و بدون Secret.

P به این سؤال پاسخ می‌دهد:

> چگونه کارهای AI را چنان صف کنیم که ارسال دوباره همان کلید هرگز کار
> تکراری نسازد، هر کار دقیقاً یک‌بار توسط یک ورکر اجرا شود (حتی با چند
> ورکر هم‌زمان)، شکست‌ها با backoff نمایی retry و سپس dead-letter شوند،
> رویدادهای §36 به‌صورت durable به مشترکین (از جمله دفتر حسابرسی O)
> برسند، و همهٔ این‌ها بدون هیچ وابستگی زیرساختی جدید (فقط Django ORM)
> کار کند؟

**یادداشت ترتیب اجرا:** P قبل از M ساخته شد اما هیچ وابستگی به کد M ندارد.
M و Z مصرف‌کنندهٔ همین قراردادند: retryهای آینده، تحلیل‌های سنگین و فن‌اوت
رویداد از `submitJob`/`runUntilIdle` و `QueuedEventBus` استفاده می‌کنند
(§2.2 و §14).

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

- موجودیت `AIJob`: tenant، kind از واژگان بسته (۷ kind دامنه‌ای + داخلی
  `EVENT_DISPATCH`)، payload دیکشنری، کلید idempotency tenant-scoped با
  fingerprint، وضعیت (`PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED/DEAD`)،
  شمارش تلاش/سقف تلاش، `runAt` زمان‌بندی، lease (`claimedBy`/`leaseExpiresAt`)،
  اولویت، ارجاع `requestId` بدون FK، خلاصهٔ نتیجه، کد خطا، correlation/trace؛
- سرویس دامنهٔ `JobQueueService`: ارسال idempotent (کلید تکراری + fingerprint
  یکسان = بازگشت رکورد؛ محتوای متفاوت = `AIIdempotencyConflict`، همان
  قرارداد G/N)، claim اتمیکِ منطقی (یک کار، یک ورکر)، heartbeat تمدید lease،
  complete، fail با retry نمایی یا dead، cancel؛ ریاضی backoff خالص؛
- ورکر (`QueueApplicationService.runOnce/runUntilIdle` + `tick()` + دستور
  مدیریتی `runAiWorker` با `--once/--interval`، هم‌الگوی worker فاز ۹): رجیستری
  handler بر اساس kind، اجرای هر کار، settle، گزارش `WorkReport`؛
- قاعدهٔ خطا: missing-handler و خطای قطعی = dead فوری (بدون retry)؛ exception
  handler = شکست retryable (محافظه‌کار؛ طبقه‌بندی دقیق خطا با M)؛
- حمل رویداد: `AIEventEnvelope` (نام رویداد محدود به `AUDIT_ACTIONS`)،
  `EventBusService` درون‌حافظه‌ای (subscribe/dispatch با گزارش تحویل)،
  `QueuedEventBus` (انتشار = ارسال job با کلید `event:{envelopeId}`)، هندلر
  `EVENT_DISPATCH` در ورکر، و `QueuedUsageEventSink` (پل N→P: حامل N به پاکت
  و صف) + مشترک حسابرسی O برای `USAGE_RECORDED` (پل P→O)؛
- مصرف قرارداد O در ورکر: هر گذار (`JOB_ENQUEUED/STARTED/COMPLETED/FAILED`)
  با `logAudit` ثبت می‌شود (۴ action جدید در واژگان O — تنها اصلاح مشترک،
  مستند در §13)؛ ارزیابی حکمرانی اختیاری پیش از اجرا وقتی payload کدها را
  حمل کند (deny = dead فوری)؛
- جدول `aiJobs` + مهاجرت `0004_queueWorker`؛ retention کارهای terminal با
  `AI_QUEUE_RETENTION_DAYS` (+meta audit از طریق همان سرویس O)؛
- تنظیمات `AI_QUEUE_*/AI_WORKER_*` در `base.py` و `.env.example` (§42)؛
  شش خطای جدید با پیشوند `AI` (§43)؛
- تست واحد آفلاین + تست application روی SQLite واقعی (شامل سناریوی end-to-end
  sink→queue→worker→audit) + تست یکپارچگی قرارداد store.

### 2.2 خارج از Scope

- طبقه‌بندی retryable/permanent خطاهای provider و timeout اجرا — زیر‌فاز
  **M** (P قرارداد `JobOutcome` را می‌دهد)؛
- هندلرهای واقعی kindهای دامنه‌ای (تحلیل سند، embedding، …) — فازهای Q/R و
  M/Z (kindها واژگان‌اند، handler را caller ثبت می‌کند)؛
- transport بین‌فرایندی (Redis pub/sub، Channels layer) — پاکت transport-agnostic
  است؛ اتصال با **Z** اگر لازم شد؛ اجرای چندورکری روی چند process با lease
  دیتابیسی کار می‌کند، mutex درون‌فرایندی لازم ندارد؛
- API عمومی صف/ورکر و داشبورد — زیر‌فاز **Z**؛
- بازنویسی `AIService.generate` سنکرون قدیمی — با **Z**؛
- امضای HSM پاکت‌ها و replay-protection بین‌سرویسی — خارج از فاز ۱۳.

---

## 3. جایگاه معماری

```text
manage.py runAiWorker ──tick()──▶ Application (QueueApplicationService — این زیر‌فاز)
   ├── submitJob / cancelJob / describeJob / listJobs / purgeJobRetention
   ├── registerHandler / runOnce / runUntilIdle  (worker loop)
   ├── EVENT_DISPATCH handler ──▶ EventBusService ──▶ subscribers (audit O, …)
   ├── QueuedEventBus(EventBusPort): publish = submitJob(EVENT_DISPATCH)
   └── QueuedUsageEventSink(UsageEventSink): AIUsageRecorded → envelope → bus
        │ hydrate (importJob) + audit/governance via O contracts (injected, optional)
        ▼
Domain (خالص، بدون Django)
   ├── queueTypes (JOB_KINDS/JOB_STATUSES، ensureها، computeBackoff)
   ├── jobRecords (AIJob — lease، retry، idempotency، fingerprint)
   ├── jobQueue (JobQueueService، JobDescriptor، JobOutcome، fingerprint)
   ├── eventBus (AIEventEnvelope، EventBusService، DispatchReport)
   └── queuePorts (JobStore، JobHandler، EventBusPort)
        │  پیاده‌سازی Django
        ▼
Infrastructure (apps/ai/infrastructure/)
   ├── models (AIJobModel — استایل تمیز)
   ├── repositories/queueRepositories (DjangoJobStore — فقط نگاشت + claim اتمیک)
   ├── management/commands/runAiWorker.py (هم‌الگوی فاز ۹)
   └── migrations/0004_queueWorker
```

قواعد وابستگی:

1. دامنه هیچ importای از Django/ORM/HTTP/Redis/Queue/Provider SDK ندارد؛
2. اپلیکیشن فقط پورت‌ها را می‌شناسد (+ سرویس‌های O به‌صورت تزریقی و اختیاری)؛
3. منطق کسب‌وکار (idempotency، lease، backoff، ترتیب dispatch) فقط در دامنه است؛
4. vocabulary تجاری بازنشده (`Project`، `Task`، …) در source ممنوع است (تست
   معماری) — در کل سطح P از واژهٔ `job` استفاده می‌شود، نه `task`؛
5. هیچ Secret، prompt، completion یا محتوای context وارد auditها، پاکت‌ها
   (به‌جز payload اجرایی) و پیام‌های خطا نمی‌شود؛
6. تغییر خارج از محدودهٔ P بدون ثبت در گزارش اجرا ممنوع (قرارداد README) —
   تنها استثنا افزودن ۴ action به واژگان O (§13).

---

## 4. قرارداد Job (§35 و §45)

### 4.1 فیلدها و واژگان

`JOB_KINDS` دقیقاً این ۸ مقدار است: `DOCUMENT_ANALYSIS`، `TRANSCRIPTION`،
`REPORT_GENERATION`، `EMBEDDING`، `INDEXING`، `PREDICTION`، `GENERIC` (دریچهٔ
فرار صریح فازهای آینده با handler خودشان)، `EVENT_DISPATCH` (داخلی حمل
رویداد). kind نامعتبر در enqueue → `AIJobInvalid` (422).
`JOB_STATUSES` شش مقدار: `PENDING`، `RUNNING`، `SUCCEEDED`، `FAILED`،
`CANCELLED`، `DEAD`. اولویت 0..9 (پیش‌فرض 5)؛ ترتیب claim:
اولویت نزولی، بعد `runAt`، بعد `createdAt`.

### 4.2 Idempotency (§45)

کلید tenant-scoped + fingerprint پایدار (sha256 روی tenant/kind/payload
canonical/کلید). تکرار = بازگشت رکورد ذخیره‌شده بدون اثر؛ محتوای متفاوت =
`AIIdempotencyConflict` (همان قرارداد G/N). کلید خالی مجاز است (بدون
حفاظت idempotency — مستند).

### 4.3 Lease و Claim

claim موفق: `PENDING` + `runAt<=now` + (lease آزاد/منقضی) → `RUNNING` با
`claimedBy`/`leaseExpiresAt=now+lease` + `attempts+1` — در store با
`select_for_update` در تراکنش تا دو ورکر هم‌زمان یک کار را نگیرند.
`heartbeat` lease را تمدید می‌کند (فقط دارندهٔ lease). claim روی کارِ
leaseدارِ دیگری → `AIJobLeaseConflict` (409). کار `RUNNING` با lease منقضی،
دوباره claimable است (مکانیزم timeout سطح P؛ timeout اجرای M جداست).

### 4.4 Retry و Dead

شکست با `retryable=True` و `attempts < maxAttempts` → `PENDING` با
`runAt = now + computeBackoff(attempts)` (نمایی: `min(cap, base·mult^(n-1))`)؛
اتمام تلاش‌ها → `DEAD` (poison، نیازمند توجه اپراتور)؛ refusal قطعی
(`retryable=False`: handler غایب، deny حکمرانی، پاکت نامعتبر) → `FAILED`
(نهایی، بدون retry). هر چهار `SUCCEEDED`/`FAILED`/`CANCELLED`/`DEAD`
نهایی‌اند. cancel فقط روی `PENDING/RUNNING` (leaseدارِ دیگری → 409).

---

## 5. قرارداد Worker

- `runOnce(limit)` یک گذر claim→execute→settle است و `WorkReport`
  (claimed/succeeded/retried/dead/failed/audited) برمی‌گرداند؛
  `runUntilIdle` تا خالی‌شدن صف با سقف تکرار می‌چرخد؛ `tick()` همان یک گذر
  محدود برای دستور مدیریتی است؛
- handler غایب برای kind → dead فوری با `errorCode=HANDLER_MISSING` (بدون
  retry)؛ exception handler → شکست retryable؛ خروجی handler از نوع
  `JobOutcome(outcome، retryable، errorCode، summary)` است؛
- پیش از اجرا (اگر payload کدهای capability/provider/model را داشت):
  `evaluateGovernance`؛ deny → dead فوری (تصمیم DENY را همان سرویس O ثبت
  کرده؛ ورکر فقط `JOB_FAILED` با `GOVERNANCE_DENIED` می‌نویسد)؛
- پس از هر گذار، در صورت تزریق `auditService`، رکورد `JOB_*` با ارجاع
  `requestId` و شناسهٔ کار در detail (نه payload کامل — audit محتوا نمی‌برد)؛
  لغو (cancel) روی همین کانال گذار با action ‏`JOB_FAILED` و
  `errorCode=CANCELLED` ثبت می‌شود تا واژگان ۴تایی بماند؛
- ورکر payload را دست‌نخورده به handler می‌دهد؛ اعتبارسنجی payload هر kind
  با صاحب kind است، به‌جز `EVENT_DISPATCH` که پاکت را بازسازی و اعتبارسنجی
  می‌کند (`AIEventInvalid` در payload خراب = dead فوری).

---

## 6. قرارداد Event Transport (§36)

- `AIEventEnvelope`: `envelopeId`، `eventName` (عضو `AUDIT_ACTIONS` — بسته
  بودن دوطرفه: فقط رویدادهای شناخته‌شده حمل می‌شوند)، `tenantId`،
  `occurredAt` صریح، `payload` دیکشنری ارجاع‌ها/شمارش‌ها، correlation/trace؛
- `EventBusService` درون‌حافظه‌ای: `subscribe(subscriber)`،
  `dispatch(envelope)` به همهٔ مشترکینِ نام رویداد؛ exception یک مشترک،
  بقیه را متوقف نمی‌کند (`DispatchReport` با جزئیات)؛
- `QueuedEventBus.publish` = `submitJob(EVENT_DISPATCH، idempotencyKey=
  f"event:{envelopeId}")` → تحویل durable و idempotent؛
- `QueuedUsageEventSink(UsageEventSink)`: حامل N را به پاکت
  `USAGE_RECORDED` تبدیل و publish می‌کند (ترکیب‌بندی در Z؛ کد N دست
  نمی‌خورد)؛ مشترک حسابرسی O پاکت `USAGE_RECORDED` را با
  `ingestUsageRecorded` می‌بلعد (بازسازی حامل از payload)؛
- ترتیب تحویل تضمین نمی‌شود (مثل همهٔ صف‌ها)؛ تکرار تحویل ممکن است پس
  مشترکین باید idempotent باشند (sink حسابرسی O با زنجیره مشکلی ندارد —
  تکرار = رکورد جدید؛ در §12 مستند).

---

## 7. قرارداد Ports و Application Service

پورت‌ها (`queuePorts.py`): `JobStore` (save/get/listDue/list/filtered-list/
update/deleteBefore + `claimRow` اتمیک)، `JobHandler` (`kind()` + `execute`)،
`EventBusPort` (`publish`). `QueueApplicationService`:

- `submitJob` / `cancelJob` / `describeJob` / `listJobs` / `purgeJobRetention`
  (purge کارهای terminal قدیمی + meta audit از همان سرویس O)؛
- `registerHandler` / `runOnce` / `runUntilIdle` / `tick`؛
- `QueueSettings.fromDjangoSettings`؛ غیرفعال بودن (`AI_QUEUE_ENABLED=false`)
  → `AIConfigurationError`، fail-closed؛
- وابستگی O (`auditService`، و حکمرانی از دل آن) اختیاری است تا ورکر خالص هم
  تست‌پذیر بماند؛ وقتی هست، هر گذار audit می‌شود.

---

## 8. قرارداد Persistence

جدول `aiJobs`: یکتای `(tenantId، idempotencyKey)` در DB — سطرهای بدون
کلید sentinel به شکل `none:<jobId>` می‌گیرند (repository موقع نگاشت به
`""` برمی‌گرداند) تا constraint ساده روی همهٔ backendها (از جمله MSSQL
بدون partial index) کار کند؛ برخورد هم‌زمان دومین `save` با همان کلید،
رکورد موجود را برمی‌گرداند (idempotent-save). ایندکس‌های
`(tenantId، status، runAt)` برای claim و `(tenantId، createdAt)` برای
retention. `requestId` ستون UUID ساده بدون FK (همان الگوی O). `payload` و
`resultSummary` از نوع JSON.

---

## 9. قرارداد Retention (§46)

`AI_QUEUE_RETENTION_DAYS` (پیش‌فرض ۳۰ — کارها عملیاتی‌اند نه سند حسابرسی؛
سندیت با audit O می‌ماند). فقط وضعیت‌های terminal purge می‌شوند
(`SUCCEEDED/FAILED/CANCELLED/DEAD`)؛ meta رکورد `RETENTION_PURGED` با شمارش.

---

## 10. قرارداد Configuration (§42)

```text
AI_QUEUE_ENABLED / AI_QUEUE_RETENTION_DAYS / AI_QUEUE_DEFAULT_MAX_ATTEMPTS
AI_QUEUE_CLAIM_LIMIT / AI_WORKER_ID / AI_WORKER_LEASE_SECONDS
AI_WORKER_RETRY_BASE_SECONDS / AI_WORKER_RETRY_MULTIPLIER / AI_WORKER_RETRY_MAX_SECONDS
AI_WORKER_IDLE_SLEEP_SECONDS (پیش‌فرض فاصلهٔ دستور مدیریتی)
```

کلیدهای `aiQueue*`/`aiWorker*` در `.env.example` با همان مقادیر پیش‌فرض.

---

## 11. خطاها (§43)

جدید P: `AIJobAlreadyRegistered` (409)، `AIJobNotFound` (404)،
`AIJobInvalid` (422)، `AIJobLeaseConflict` (409)، `AIJobHandlerMissing`
(500)، `AIEventInvalid` (422). تعارض کلید از `AIIdempotencyConflict`
موجود (409).

---

## 12. Purity و Dependency Rules

- دامنهٔ P هیچ import از `django`/`rest_framework`/`redis`/`channels` و هیچ
  ماژول infrastructure ندارد (تست معماری)؛
- vocabulary تجاری در کل سطح P ممنوع (تست معماری) — واژهٔ `job`، نه `task`؛
  «forecast» نه «projected»؛
- `mypy` روی هر ۸ فایل جدید P بدون خطا؛ `ruff check` و `ruff format` روی
  سطح P سبز؛ `models.py` روی ۱۲۹ خطای پیشین می‌ماند (افزودهٔ P صفر)؛
- محدودیت‌های ثبت‌شده: ترتیب تحویل رویداد تضمین نمی‌شود؛ تکرار تحویل envelope
  ممکن است (مشترکین idempotent باشند)؛ claim و settle دو فراخوانی‌اند (کار
  RUNNING با lease منقضی reclaim می‌شود، نه گم)؛ worker تک‌فرایندیِ
  چندنخی‌امن نیست — اجرای موازی چند process با lease دیتابیسی امن است؛
- caveat تست (از N/O): `createdAt` سطرها زمان persistence است؛ `runAt` و
  `occurredAt` صریح دامنه‌اند و قطعی می‌مانند.

---

## 13. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/valueObjects/queueTypes.py
backend/apps/ai/domain/entities/jobRecords.py
backend/apps/ai/domain/services/jobQueue.py
backend/apps/ai/domain/services/eventBus.py
backend/apps/ai/domain/queuePorts.py
backend/apps/ai/application/services/queueService.py
backend/apps/ai/infrastructure/repositories/__init__.py   (export جدید)
backend/apps/ai/infrastructure/repositories/queueRepositories.py
backend/apps/ai/infrastructure/models.py                (افزایشی: ۱ مدل)
backend/apps/ai/infrastructure/migrations/0004_queueWorker.py
backend/apps/ai/management/__init__.py
backend/apps/ai/management/commands/__init__.py
backend/apps/ai/management/commands/runAiWorker.py
backend/apps/ai/domain/entities/__init__.py
backend/apps/ai/domain/valueObjects/__init__.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py       (۶ خطای جدید)
backend/apps/ai/domain/exceptions/__init__.py
backend/apps/ai/domain/valueObjects/auditTypes.py       (۴ action جدید JOB_*)
backend/config/settings/base.py                         (AI_QUEUE_*/AI_WORKER_*)
backend/.env.example                                    (aiQueue*/aiWorker*)

backend/tests/unit/testPhase13QueueWorker.py
backend/tests/unit/testPhase13AuditGovernance.py        (فقط شمارش ۱۵→۱۹)
backend/tests/application/testPhase13QueueUseCases.py
backend/tests/integration/testPhase13QueueContract.py

docs/Phases/Phase13/Phase13-O.md                        (یادداشت اصلاحیهٔ واژگان)
docs/Phases/Phase13/Phase13-P.md
docs/Phases/Phase13/Phase13-P-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

APIهای اصلی:

```text
JOB_KINDS / JOB_STATUSES / ensureJobKind / ensureJobStatus / computeBackoff
AIJob / jobFingerprint
JobQueueService / JobDescriptor / JobOutcome / JobFilter / WorkReport? (app)
AIEventEnvelope / EventBusService / EventDispatchReport / DispatchReport
JobStore / JobHandler / EventBusPort
QueueApplicationService / QueueSettings / SubmitJobCommand / QueuedEventBus
QueuedUsageEventSink / AuditEventSubscriber (registerAuditSubscriber)
DjangoJobStore / tick / Command (runAiWorker)
```

Aliasها:

```text
AIJobQueue / InMemoryJobQueue / AIQueueService
AIEventBus / InMemoryEventBus
QueueWorkerService / AIWorkerService
```

---

## 14. Open Questions برای زیر‌فازهای بعدی

1. **M:** طبقه‌بندی retryable/permanent خطاهای provider در `JobOutcome`؛
   timeout اجرای handler؛ آیا retry بودجهٔ جداگانه (quota) می‌خواهد؟
2. **Z:** کدام عملیات سنکرون پشت صف می‌روند (حل race پذیرش N با serialize
   در ورکر؟)؛ transport بین‌فرایندی پاکت‌ها (Redis/Channels) لازم است یا
   DB کافی است؛ API و داشبورد صف؛
3. **Q/R:** هندلرهای واقعی `EMBEDDING`/`INDEXING`/`DOCUMENT_ANALYSIS`؛
4. **تکرار تحویل:** آیا sink حسابرسی باید برای پاکت‌های تکراری dedupe کند
   (idempotencyKey پاکت) یا رکورد جدید قابل‌قبول است؟ (فعلاً دومی — §6)؛
5. **اولویت:** آیا اولویت 0..9 کافی است یا starvation-prevention لازم است؟

---

## 15. Acceptance Criteria

- [x] موجودیت `AIJob` با همهٔ فیلدهای §4 و ارجاع بدون FK ساخته شد؛
- [x] واژگان بستهٔ kind (۸تایی) و status (۶تایی) با خطای 422 پیاده شد؛
- [x] ارسال idempotent با fingerprint (تکرار=بازگشت، تعارض=409) پیاده شد؛
- [x] claim اتمیک (یک کار، یک ورکر) با lease و heartbeat پیاده شد؛
- [x] claim روی lease دیگری 409؛ lease منقضی reclaimable است؛
- [x] retry نمایی با سقف + dead-letter + cancel قانون‌مند پیاده شد؛
- [x] handler غایب = FAILED فوری (بدون retry)؛ exception = شکست retryable؛
- [x] ورکر runOnce/runUntilIdle/tick + دستور `runAiWorker` پیاده شد؛
- [x] پاکت رویداد با نام محدود به `AUDIT_ACTIONS` + bus درون‌حافظه‌ای با
  گزارش تحویل پیاده شد؛
- [x] تحویل durable رویداد از طریق صف (idempotencyKey پاکت) پیاده شد؛
- [x] پل N→P (`QueuedUsageEventSink`) و P→O (مشترک حسابرسی) بدون لمس کد N/O؛
- [x] سناریوی end-to-end sink→queue→worker→audit روی DB واقعی سبز است؛
- [x] هر گذار کار با `JOB_*` audit می‌شود (۴ action جدید، مستند)؛
- [x] حکمرانی اختیاری پیش از اجرا (deny = dead فوری)؛
- [x] جدول + مهاجرت `0004_queueWorker` بدون drift؛ retention terminalها؛
- [x] تنظیمات `AI_QUEUE_*`/`AI_WORKER_*` پیکربندی‌محور؛
- [x] ایزولاسیون tenant در هر چهار لایه تست شد؛
- [x] تست‌های جدید سبز (واحد + کاربردی + یکپارچگی)؛
- [x] گیت کیفیت سطح P سبز (ruff/mypy/format/tests)؛
- [x] اتصال M/Z بدون نیاز به تغییر اسکیما؛
- [x] مستندات قرارداد و گزارش + به‌روزرسانی README و سند مادر.

**نتیجه:** `GREEN — Phase 13-M may begin.`
