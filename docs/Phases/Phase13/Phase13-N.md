# Phase 13-N — Usage، Token، Latency، Cost و Quota

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** N از A تا Z
**وضعیت:** COMPLETED — Usage/Metering Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§26، §27، §29، §34، §36، §37، §38، §42، §43، §51)
**قراردادهای قبلی:** [B](Phase13-B.md) (موجودیت‌ها و Value Objectها)،
[C](Phase13-C.md) (پورت Provider)، [E](Phase13-E.md) (رجیستری و Routing مدل)،
[G](Phase13-G.md) (چرخه‌عمر Request/Operation)، [H](Phase13-H.md) (پاسخ)،
[K](Phase13-K.md) (ایزولاسیون و Authorization)، [L](Phase13-L.md) (آداپتورها)
**گزارش اجرا:** [`Phase13-N-ExecutionReport.md`](Phase13-N-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز N لایهٔ اندازه‌گیری و کنترل مصرف AI را می‌سازد: هر تلاش Provider باید
توکن، تأخیر و هزینهٔ خود را ثبت کند (§26 و §27)، هر مصرف باید در برابر
سهمیه‌های صریح Tenant ارزیابی شود (§29 و §42)، و همهٔ این‌ها باید بدون
وابستگی به Vendor، بدون نشت Secret، و با ایزولاسیون کامل Tenant انجام شود
(§38).

N به این سؤال پاسخ می‌دهد:

> چگونه مصرف هر تلاش AI را به‌صورت idempotent، tenant-aware و
> provider-agnostic ثبت کنیم، هزینه را از نرخ مدل محاسبه کنیم، سهمیه‌ها را
> پیش از مصرف enforce کنیم (fail-closed)، و گزارش‌های §26 و متریک‌های §34
> را از همان رکوردها استخراج کنیم — بدون آنکه به اجرای M (Retry/Fallback)،
> صف P، یا باس رویداد O وابسته باشیم؟

**یادداشت ترتیب اجرا:** N از نظر حروفی بعد از M است اما M هنوز ساخته نشده.
N هیچ وابستگی به کد M ندارد: رکورد سطح attempt دقیقاً همان قراردادی است که
executor آیندهٔ M برای هر تلاش (از جمله تلاش‌های retry و fallback) صدا
خواهد زد. M همچنان «زیر‌فاز بعدی» است و بدون تغییر اسکیما به N وصل می‌شود
(§2.2 و §14).

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

- رکورد سطح attempt (`AIUsageAttempt`): توکن ورودی/خروجی/کل، شکست تأخیر
  §27 (queue/contextBuild/provider/validation/total)، هزینه و ارز، نتیجه
  (SUCCEEDED/FAILED)، کد خطا، کلید idempotency، correlation/trace؛
- ثبت idempotent: تکرار کلید یکسان با fingerprint یکسان رکورد ذخیره‌شده را
  برمی‌گرداند (بدون اثر جانبی)؛ استفادهٔ مجدد کلید با محتوای متفاوت
  `AIIdempotencyConflict` می‌دهد (همان قرارداد فاز G)؛
- جمع‌بندی سطح request (rollup از attemptها، بدون dual-write) و گزارش
  تجمیعی سطح tenant با شکست capability/model/provider (§26)؛
- آمار تأخیر §34 (تعداد، جمع، میانگین، p95 با روش nearest-rank، بیشینه)؛
- محاسبهٔ هزینه از `CostRate` مدل (`inputCostPer1k`/`outputCostPer1k`
  جدید روی `aiModels`) + سقف هزینهٔ سطح request و سقف توکن (پیکربندی‌محور،
  §42)؛
- سیاست سهمیه (`AIQuotaPolicy`) روی سه محور scope (TENANT/USER/DEPARTMENT/
  PROJECT/CAPABILITY/MODEL) × بُعد (REQUESTS/INPUT_TOKENS/OUTPUT_TOKENS/
  TOTAL_TOKENS/COST) × پنجره (MINUTE/HOUR/DAY/WEEK/MONTH) با ریاضیات قطعی
  پنجرهٔ UTC؛
- شمارندهٔ پنجره (`AIQuotaCounter`) با مصرف اتمیک سطح سطر؛
- enforcement fail-closed: همهٔ سیاست‌های فعالِ منطبق باید بگذرند؛ رد شدن
  یکی کافی است؛ رد شدن هیچ مصرف جزئی باقی نمی‌گذارد؛ مصرف مستقل از نتیجه
  است (تلاش ناموفق هم سهمیه می‌برد چون Provider آن را صورت‌حساب می‌کند)؛
- پذیرش خشک (admission dry-run) بدون جهش برای تصمیم پیش از اجرای پرهزینه؛
- حامل رویداد `AIUsageRecorded` (§36) بدون محتوا و Secret + پورت
  `UsageEventSink` با دابل درون‌حافظه‌ای؛
- سه جدول جدید (`aiUsageAttempts`، `aiQuotaPolicies`، `aiQuotaCounters`) +
  دو ستون نرخ روی `aiModels` + مهاجرت `0002_usageMetering`؛
- تنظیمات `AI_USAGE_*` در `base.py` و `.env.example` (§42)؛
- تست واحد آفلاین + تست application روی SQLite واقعی + تست یکپارچگی قرارداد
  repositoryها.

### 2.2 خارج از Scope

- Retry / Fallback / Timeout Executor — زیر‌فاز **M** (مصرف‌کنندهٔ آیندهٔ
  همین قرارداد؛ §14)؛
- Audit و Governance خروجی metering — زیر‌فاز **O** (از جمله retention job
  شمارنده‌های قدیمی و پاک‌سازی `fingerprint`ها)؛
- Queue / Worker / اجرای Async — زیر‌فاز **P** (سریال‌سازی پذیرش‌های
  هم‌زمان؛ §10)؛
- اتصال حامل `AIUsageRecorded` به Event Bus — زیر‌فازهای **O/P** (پورت و
  حامل آماده است، binding نداریم)؛
- بازنویسی `AIService.generate` قدیمی و جدول `aiUsage` (rollup تک‌تلاشی
  legacy): N آن را دست نمی‌زند؛ هم‌گرایی ledger در **Z** (سؤال باز §14)؛
- اندپوینت API عمومی metering/quota — زیر‌فاز **Z**؛
- تبدیل ارز (FX)، بودجهٔ تأخیر (latency budget enforcement)، قیمت‌گذاری
  پویا و صورت‌حساب — خارج از فاز ۱۳.

---

## 3. جایگاه معماری

```text
Application (UsageApplicationService — این زیر‌فاز)
   ├── admitRequest (dry-run: caps + evaluate، بدون جهش)
   ├── recordProviderAttempt (rate → cost → caps → evaluate → persist → consume → publish)
   └── reads (rollup / summary / remaining / list / describe)
        │ hydrate (importPolicy/importCounter/importAttempt)
        ▼
Domain (خالص، بدون Django)
   ├── usageTypes (QuotaScope/Dimension/Window، LatencyBreakdown، UsageAttribution، ریاضی پنجره UTC)
   ├── usageRecords (AIUsageAttempt، AIQuotaPolicy، AIQuotaCounter، costForAttempt)
   ├── usageMetering (UsageMeteringService، CostCalculator، latencyStatistics، AIUsageRecorded)
   ├── quotaEnforcement (QuotaEnforcementService، evaluate/checkAndConsume، raiseForDenial)
   └── meteringPorts (UsageAttemptStore، QuotaPolicyStore، QuotaCounterStore، CostRateResolver، UsageEventSink)
        │  پیاده‌سازی Django
        ▼
Infrastructure (apps/ai/infrastructure/)
   ├── models (AIUsageAttemptModel، AIQuotaPolicyModel، AIQuotaCounterModel + نرخ‌های AIModelModel)
   ├── repositories/usageRepositories (Django stores + resolver — فقط نگاشت سطر↔موجودیت)
   └── migrations/0002_usageMetering
```

قواعد وابستگی:

1. دامنه هیچ importای از Django/ORM/HTTP/Redis/Queue/Provider SDK ندارد
   (تست معماری موجود آن را نگه می‌دارد)؛
2. اپلیکیشن فقط پورت‌ها را می‌شناسد؛ پیاده‌سازی Django تزریق می‌شود؛
3. منطق کسب‌وکار (تطبیق سیاست، exhaust، ریاضی پنجره/هزینه/p95) فقط در
   دامنه است؛ repositoryها فقط نگاشت‌اند؛
4. هیچ Secret، کلید API، prompt، completion یا context وارد رکوردها،
   descriptorها، رویدادها و پیام‌های خطا نمی‌شود؛
5. تغییر خارج از محدودهٔ N بدون ثبت در گزارش اجرا ممنوع (قرارداد README).

---

## 4. قرارداد Usage (§26)

### 4.1 رکورد attempt

هر attempt با `(tenantId، requestId، attemptNumber)` شناخته می‌شود؛
`attemptNumber` از ۱ شروع می‌شود تا تلاش‌های آیندهٔ retry/fallback (M) در
همان request جا شوند. حداقل §26 (inputTokens/outputTokens/totalTokens/
estimatedCost/currency/provider/model) به‌علاوهٔ شکست تأخیر §27 روی هر
رکورد ذخیره می‌شود.

### 4.2 Idempotency

کلید tenant-scoped است. fingerprint پایدار (sha256 روی شناسه‌ها + شمارش‌ها
+ هزینه + نتیجه) در دو لایه نگه داشته می‌شود: حافظه (سرویس دامنه) و ستون
`fingerprint` جدول (store). تکرار = بازگشت رکورد ذخیره‌شده **بدون مصرف
مجدد و بدون انتشار مجدد** (اثر جانبی دقیقاً یک‌بار برای هر کلید).
تست‌ها: `testRecordIsIdempotentForSameFingerprint`،
`testReusedKeyWithDifferentFingerprintConflicts`،
`testIdempotentRerecordReturnsSameAttemptAndConsumesOnce`،
`testReusedKeyWithDifferentContentConflicts`.

### 4.3 Rollup و Summary (بدون dual-write)

`RequestUsageRollup` همیشه از attemptها مشتق می‌شود (جمع توکن‌ها/هزینه/
زمان + شمار موفق/ناموفق)؛ هیچ سطر rollup ذخیره نمی‌شود تا ناسازگاری
دو-نوشتنی پیش نیاید. `UsageSummary` سطح tenant با فیلتر
capability/model/provider و بازهٔ زمانی + شکست هر سه محور + آمار تأخیر
است. ارز مخلوط در یک rollup/summary خطای `AIConfigurationError` می‌دهد
(fail-closed؛ §N.6).

---

## 5. قرارداد Latency (§27 و §34)

هر attempt چهار جزء `queueTimeMs`، `contextBuildTimeMs`، `providerTimeMs` و
`validationTimeMs` را جدا نگه می‌دارد؛ `totalTimeMs` صریح بر مجموع اجزا
اولویت دارد (آداپتور L زمان سرتاسری واقعی را می‌سنجد). `latencyStatistics`
روی نمونه‌ها: تعداد، جمع، میانگین (تقسیم صحیح)، **p95 با nearest-rank**
(`ceil(0.95·n)`) و بیشینه. نمونهٔ منفی رد می‌شود؛ مجموعهٔ خالی صفر
برمی‌گرداند.

---

## 6. قرارداد Cost (§26 و §42)

- نرخ از `CostRate(inputCostPer1k، outputCostPer1k، currency)` مدل می‌آید؛
  `CostCalculator.calculate` همان `rate.calculate` دامنهٔ B است؛
- ارز نرخ‌ها = `AI_USAGE_DEFAULT_CURRENCY` (resolver آن را تزریق می‌کند؛
  نرخ‌ها به همان ارز ثبت می‌شوند — بدون FX)؛
- سقف‌ها: `AI_USAGE_DEFAULT_TOKEN_LIMIT` روی total هر attempt (صفر =
  نامحدود) + `maxInputTokens` سطح فراخوانی روی ورودی + سقف هزینهٔ
  `AI_USAGE_DEFAULT_COST_LIMIT`؛ تخطی توکن → `AITokenLimitExceeded` (422)،
  تخطی هزینه → `AICostLimitExceeded` (429، زیرکلاس `AIQuotaExceeded` تا
  هندلرهای موجود کار کنند)؛
- ناسازگاری ارز هزینه/سقف → `AIConfigurationError` (fail-closed، نه چشم‌پوشی).

---

## 7. قرارداد Quota (§29 و §42)

### 7.1 محورها

| محور | مقادیر |
|---|---|
| Scope | TENANT (بدون reference) · USER (UUID کاربر) · DEPARTMENT (کد) · PROJECT (شناسه) · CAPABILITY (کد) · MODEL (کد) |
| Dimension | REQUESTS · INPUT_TOKENS · OUTPUT_TOKENS · TOTAL_TOKENS · COST |
| Window | MINUTE · HOUR · DAY · WEEK (دوشنبهٔ ISO) · MONTH (تقویمی) — همه UTC |

هویت سیاست: `(tenant، scope، reference، dimension، window)` با یکتایی
دیتابیسی. حد سیاست همیشه مثبت است؛ «نامحدود» = نبود سیاست.

### 7.2 تطبیق و تقدم

سیاست فعالِ منطبق با attribution اعمال می‌شود؛ TENANT همیشه منطبق است.
**همهٔ** منطبق‌ها باید بگذرند (سقف tenant و سقف user مستقل رد می‌کنند).
پیام رد، خاص‌ترین سیاست را اول می‌آورد
(USER › PROJECT › DEPARTMENT › CAPABILITY › MODEL › TENANT).

### 7.3 مصرف

`evaluate` (خشک، بدون جهش) و `checkAndConsume` (ارزیابی + مصرف یکجا) روی
یک هستهٔ ارزیابی‌اند تا پیام‌ها تک‌منبع بمانند (`raiseForDenial`).
ارزیابی همهٔ سیاست‌ها **پیش** از هر جهش انجام می‌شود پس رد شدن، مصرف جزئی
نمی‌گذارد. شمارندهٔ هر پنجره با شروع پنجره ساخته می‌شود؛ پنجرهٔ جدید
شمارندهٔ تازه دارد و پنجره‌های قدیمی برای گزارش خوانا می‌مانند (حذف با O).

### 7.4 خطاها (§43)

موجود: `AIQuotaExceeded` (429)، `AITokenLimitExceeded` (422).
جدید N: `AICostLimitExceeded` (429، زیرکلاس Quota)،
`AIQuotaPolicyAlreadyRegistered` (409)، `AIQuotaPolicyNotFound` (404)،
`AIQuotaPolicyInvalid` (422)، `AIUsageAttemptAlreadyRegistered` (409)،
`AIUsageAttemptNotFound` (404). تعارض کلید از `AIIdempotencyConflict`
موجود (409) استفاده می‌کند.

---

## 8. قرارداد Ports و Application Service

پورت‌ها (`meteringPorts.py`): `UsageAttemptStore` (ذخیره/خواندن/فهرست با
فیلتر request/outcome/بازه + `findByIdempotencyKey`)، `QuotaPolicyStore`
(ذخیره/خواندن/فهرست فعال/تغییر وضعیت)، `QuotaCounterStore` (بارگذاری،
ذخیرهٔ مطلق، `addConsumption` اتمیک سطح سطر)، `CostRateResolver`
(نرخ مدل tenant-owned؛ ناموجود → `AIModelNotRegistered`، غیرفعال →
`AIModelInactive`)، `UsageEventSink` + دابل درون‌حافظه‌ای.

`UsageApplicationService`:

- `defineQuotaPolicy` / `deactivateQuotaPolicy` / `listQuotaPolicies`؛
- `admitRequest` (خشک: سقف‌ها + evaluate؛ خطا همان خطاهای رکورد؛
  `AdmissionGrant` با remaining)؛
- `recordProviderAttempt` (نرخ ← هزینه ← سقف‌ها ← replay-check ←
  evaluate ← persist ← consume اتمیک ← publish؛ خروجی `RecordedAttempt`)؛
- خواندن‌ها (`describeAttempt`، `listAttempts`، `requestRollup`،
  `usageSummary`، `remainingQuotas`) با hydration گذرا در هر فراخوانی —
  هیچ state درون‌حافظه‌ای بین درخواست‌ها در این لایه نیست؛
- تنظیمات از `UsageMeteringSettings.fromDjangoSettings` (غیرفعال بودن →
  `AIConfigurationError`، fail-closed).

---

## 9. قرارداد Persistence (§37)

جدول‌های جدید (مهاجرت `0002_usageMetering`):

| جدول | کلیدها |
|---|---|
| `aiUsageAttempts` | یکتا `(tenantId، request، attemptNumber)`؛ ایندکس `(tenantId، createdAt)` و `(tenantId، idempotencyKey)`؛ ستون `fingerprint` برای تعارض کلید |
| `aiQuotaPolicies` | یکتا `(tenantId، scope، scopeReference، dimension، window)` |
| `aiQuotaCounters` | یکتا `(policy، windowStart)`؛ ایندکس `(tenantId، windowStart)` |

تغییر افزایشی `aiModels`: دو ستون `inputCostPer1k`/`outputCostPer1k`
(Decimal 18,8). جدول legacy `aiUsage` دست‌نخورده می‌ماند (§2.2).
`addConsumption` با `select_for_update` + `F()` اتمیک است (روی SQLite
no-op بی‌خطر). یکتایی کلید idempotency عمداً در DB نیست (رشتهٔ خالی در
SQL Server فقط یک NULL مجاز می‌گذاشت) و در repository با تراکنش enforce
می‌شود.

---

## 10. قرارداد Configuration (§42)

```text
AI_USAGE_ENABLED / AI_USAGE_DEFAULT_TOKEN_LIMIT / AI_USAGE_DEFAULT_COST_LIMIT
AI_USAGE_DEFAULT_CURRENCY / AI_USAGE_RETENTION_DAYS
```

کلیدهای `aiUsage*` در `.env.example` با همان مقادیر پیش‌فرض. صفر یعنی
نامحدود؛ سیاست صریح tenant همیشه بر پیش‌فرض پلتفرم مقدم است.

---

## 11. قرارداد Event (§36)

`AIUsageRecorded` فقط شناسه‌ها، شمارش‌ها، پول و زمان‌بندی حمل می‌کند —
بدون prompt/completion/context/secret (اثبات با تست
`testEventCarrierHasNoContentOrSecrets`). انتشار به باس با O/P است؛ پورت
`UsageEventSink` نقطهٔ اتصال آینده است.

---

## 12. Purity و Dependency Rules

- دامنهٔ N هیچ import از `django`/`rest_framework`/`redis`/`channels` و هیچ
  ماژول infrastructure ندارد (تست‌های معماری موجود)؛
- نام‌گذاری camelCase توابع/متغیرها/فایل‌ها و PascalCase کلاس‌ها (تست
  نام‌گذاری موجود)؛
- `mypy` روی هر ۷ فایل جدید N بدون خطا؛ `ruff check` و `ruff format` روی
  سطح N سبز؛ `models.py` دقیقاً روی ۱۲۹ خطای پیشین مانده (افزودهٔ N صفر)؛
- محدودیت شناخته‌شده (ثبت‌شده، نه پنهان): ارزیابی و مصرف دو فراخوانی
  مجزای storeاند؛ پذیرش‌های کاملاً هم‌زمان می‌توانند هر دو بگذرند و بعد هر
  دو مصرف کنند (سریال‌سازی با worker فاز P) — شمارنده‌ها هرگز گم نمی‌کنند
  چون افزایش اتمیک است. سابقهٔ این الگوی ثبت، §10 قرارداد K است.
- caveat تست: `createdAt` سطرها زمان persistence است (auto_now_add) نه
  ساعت دامنه؛ تست‌های persistence با کران wall-clock نوشته شده‌اند.

---

## 13. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/valueObjects/usageTypes.py
backend/apps/ai/domain/entities/usageRecords.py
backend/apps/ai/domain/services/usageMetering.py
backend/apps/ai/domain/services/quotaEnforcement.py
backend/apps/ai/domain/meteringPorts.py
backend/apps/ai/application/services/usageService.py
backend/apps/ai/infrastructure/repositories/__init__.py
backend/apps/ai/infrastructure/repositories/usageRepositories.py
backend/apps/ai/infrastructure/models.py                (افزایشی: ۲ ستون + ۳ مدل)
backend/apps/ai/infrastructure/migrations/0002_usageMetering.py
backend/apps/ai/domain/entities/__init__.py
backend/apps/ai/domain/valueObjects/__init__.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py       (۶ خطای جدید)
backend/apps/ai/domain/exceptions/__init__.py
backend/config/settings/base.py                         (AI_USAGE_*)
backend/.env.example                                    (aiUsage*)

backend/tests/unit/testPhase13UsageMetering.py          (۶۹ تست)
backend/tests/application/testPhase13UsageUseCases.py   (۱۶ تست)
backend/tests/integration/testPhase13UsageContract.py   (۲۵ تست)

docs/Phases/Phase13/Phase13-N.md
docs/Phases/Phase13/Phase13-N-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

APIهای اصلی:

```text
QuotaScope / QuotaDimension / QuotaWindow / LatencyBreakdown / UsageAttribution
windowStart / windowEnd
AIUsageAttempt / AIQuotaPolicy / AIQuotaCounter / costForAttempt
UsageMeteringService / CostCalculator / latencyStatistics / attemptFingerprint
AIUsageRecorded / AttemptDescriptor / RequestUsageRollup / UsageSummary / LatencyStats
QuotaEnforcementService / QuotaEvaluation / PolicyDenial / QuotaConsumption
QuotaRemaining / ConsumedQuota / PolicyDescriptor / raiseForDenial
UsageAttemptStore / QuotaPolicyStore / QuotaCounterStore / CostRateResolver / UsageEventSink
UsageApplicationService / UsageMeteringSettings / RecordUsageAttemptCommand
AdmissionGrant / RecordedAttempt
DjangoUsageAttemptStore / DjangoQuotaPolicyStore / DjangoQuotaCounterStore / DjangoCostRateResolver
```

Aliasها:

```text
UsageMeter / InMemoryUsageMetering / AIUsageMeteringService
QuotaPolicyService / InMemoryQuotaEnforcement / AIQuotaService
UsageMeteringApplicationService / AIUsageService
```

---

## 14. Open Questions برای زیر‌فازهای بعدی

1. **M:** executor پس از هر تلاش (موفق/ناموفق، اصلی/fallback) همین
   `recordProviderAttempt` را صدا می‌زند؛ بودجهٔ retry روی شمارندهٔ
   REQUESTS سوار می‌شود یا سیاست جدا می‌خواهد؟
2. **Z:** هم‌گرایی ledger جدید `aiUsageAttempts` با `aiUsage` قدیمی و
   `AIService.generate` (بازنویسی روی pipeline یکپارچه یا نگاشت read)؛
3. **O:** retention job شمارنده‌ها/attemptهای قدیمی (`AI_USAGE_RETENTION_DAYS`
   آماده است) + اتصال `AIUsageRecorded` به باس + audit مصرف؛
4. **P:** سریال‌سازی پذیرش‌های هم‌زمان در worker (حذف race §12)؛
5. **ارز:** نرخ‌ها تک‌ارزی‌اند؛ اگر tenant ارز پیش‌فرض را عوض کند،
   هزینه‌های تاریخی با کدام ارز گزارش می‌شوند؟ (فعلاً fail-closed)
6. **ابعاد گزارش:** DEPARTMENT/PROJECT فعلاً opaque referenceاند (دامنه‌های
   مالک هنوز باز نشده‌اند) — اتصال به دایرکتوری آن‌ها با فازهای مربوطه.

---

## 15. Acceptance Criteria

- [x] رکورد سطح attempt با همهٔ فیلدهای §26/§27 ایجاد شد؛
- [x] ثبت idempotent با fingerprint و بدون اثر جانبی در تکرار پیاده شد؛
- [x] کلید تکراری با محتوای متفاوت `AIIdempotencyConflict` می‌دهد؛
- [x] rollup سطح request بدون dual-write از attemptها مشتق می‌شود؛
- [x] summary سطح tenant با شکست capability/model/provider و فیلتر زمانی
  پیاده شد؛
- [x] آمار تأخیر (میانگین + p95 nearest-rank) پیاده و تست شد؛
- [x] هزینه از `CostRate` مدل محاسبه می‌شود؛ ارز مخلوط fail-closed است؛
- [x] سقف توکن (پیش‌فرض + سطح فراخوانی) با `AITokenLimitExceeded` enforce شد؛
- [x] سقف هزینه با `AICostLimitExceeded` enforce شد؛
- [x] سیاست سهمیه روی هر سه محور با یکتایی و تطبیق scope پیاده شد؛
- [x] همهٔ سیاست‌های منطبق enforce می‌شوند؛ تقدم خاص‌ترین در پیام رد؛
- [x] رد شدن هیچ مصرف جزئی نمی‌گذارد (اتمیک در سطح دامنه)؛
- [x] مصرف مستقل از نتیجه است (تلاش ناموفق هم سهمیه می‌برد)؛
- [x] پنجره‌های MINUTE تا MONTH با ریاضی قطعی UTC (هفتهٔ ISO، ماه تقویمی)؛
- [x] پذیرش خشک (admission) بدون جهش پیاده شد؛
- [x] شمارنده‌ها با افزایش اتمیک سطح سطر مصرف می‌کنند؛
- [x] حامل `AIUsageRecorded` بدون محتوا/Secret + پورت sink؛
- [x] سه جدول + نرخ‌های مدل + مهاجرت `0002_usageMetering` بدون drift؛
- [x] تنظیمات `AI_USAGE_*` پیکربندی‌محور (هیچ هاردکدی)؛
- [x] ایزولاسیون tenant در هر چهار لایه تست شد؛
- [x] ۱۱۰ تست جدید سبز (۶۹ واحد + ۱۶ کاربردی + ۲۵ یکپارچگی)؛
- [x] گیت کیفیت سطح N سبز (ruff/mypy/format/tests)؛
- [x] سازگاری M بدون نیاز به تغییر اسکیما (attempt-scoped)؛
- [x] مستندات قرارداد و گزارش + به‌روزرسانی README و سند مادر.

**نتیجه:** `GREEN — Phase 13-M may begin.`
