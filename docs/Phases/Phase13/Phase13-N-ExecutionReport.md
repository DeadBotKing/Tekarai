# گزارش اجرا — Phase 13-N: Usage، Token، Latency، Cost و Quota

**تاریخ:** 2026-09-05 · **وضعیت:** Usage/Metering Gate GREEN
**قرارداد:** [`Phase13-N.md`](Phase13-N.md) · **مجری:** Arena.ai Agent Mode

---

## 1. خلاصهٔ تحویل

لایهٔ کامل اندازه‌گیری و کنترل مصرف AI ساخته شد: رکورد idempotent سطح
attempt (توکن/تأخیر/هزینه/نتیجه)، rollup سطح request بدون dual-write،
گزارش تجمیعی سطح tenant (§26)، آمار تأخیر §34، محاسبهٔ هزینه از نرخ مدل،
سقف‌های توکن/هزینه، سیاست سهمیه روی سه محور scope×dimension×window با
مصرف اتمیک و enforcement مردود-بسته، پذیرش خشک، و حامل رویداد بدون محتوا.
۱۱۰ تست جدید سبز است و سطح N در هر سه گیت کیفیت تمیز است.

## 2. فایل‌های ایجادشده

### 2.1 کد

| فایل | نقش |
|---|---|
| `backend/apps/ai/domain/valueObjects/usageTypes.py` | Enumهای QuotaScope/Dimension/Window، `LatencyBreakdown`، `UsageAttribution`، ریاضی قطعی پنجرهٔ UTC |
| `backend/apps/ai/domain/entities/usageRecords.py` | `AIUsageAttempt`، `AIQuotaPolicy`، `AIQuotaCounter`، `costForAttempt` |
| `backend/apps/ai/domain/services/usageMetering.py` | `UsageMeteringService` (ثبت/persist/replay/fingerprint)، `CostCalculator`، `latencyStatistics`، `AIUsageRecorded` |
| `backend/apps/ai/domain/services/quotaEnforcement.py` | `QuotaEnforcementService` (evaluate/checkAndConsume/remaining/describe)، `raiseForDenial` |
| `backend/apps/ai/domain/meteringPorts.py` | پنج پورت + `InMemoryUsageEventSink` |
| `backend/apps/ai/application/services/usageService.py` | `UsageApplicationService` (admit/record/reads + replay دقیقاً‌یک‌بار) |
| `backend/apps/ai/infrastructure/repositories/usageRepositories.py` | چهار store دjango (+resolver نرخ با guard tenant/model فعال) |
| `backend/apps/ai/infrastructure/models.py` | ۲ ستون نرخ روی `AIModelModel` + ۳ مدل جدید (به استایل تمیز) |
| `backend/apps/ai/infrastructure/migrations/0002_usageMetering.py` | مهاجرت کم‌حجم N |
| `backend/apps/ai/domain/exceptions/aiExceptions.py` | ۶ خطای N: `AICostLimitExceeded`، `AIQuotaPolicy{AlreadyRegistered,NotFound,Invalid}`، `AIUsageAttempt{AlreadyRegistered,NotFound}` |
| `backend/config/settings/base.py` + `backend/.env.example` | پنج کلید `AI_USAGE_*` |
| پنج `__init__.py` دامنه | export موجودیت‌ها/سرویس‌ها/خطاها |

### 2.2 تست

| فایل | حجم |
|---|---|
| `backend/tests/unit/testPhase13UsageMetering.py` | ۶۹ تست آفلاین خالص |
| `backend/tests/application/testPhase13UsageUseCases.py` | ۱۶ تست روی SQLite واقعی |
| `backend/tests/integration/testPhase13UsageContract.py` | ۲۵ تست قرارداد persistence |

### 2.3 پیکربندی

`AI_USAGE_ENABLED=true`، `AI_USAGE_DEFAULT_TOKEN_LIMIT=0` (نامحدود)،
`AI_USAGE_DEFAULT_COST_LIMIT=0`، `AI_USAGE_DEFAULT_CURRENCY=USD`،
`AI_USAGE_RETENTION_DAYS=90`.

### 2.4 مستندات

قرارداد N، همین گزارش، به‌روزرسانی README فاز ۱۳ و سند مادر.

## 3. تغییرات اصلاحی مستند

| # | مسئله | رفتار پیشین | رفتار پسین | چرا |
|---|---|---|---|---|
| 1 | `UnboundLocalError: normalizedKey` در مسیر رکورد تکراری | تست‌های idempotency خطا می‌دادند | `normalizedKey` بلافاصله پس از نرمال‌سازی هزینه تعریف شد | تعریف دیرهنگام متغیر در مسیر زودبازگشت |
| 2 | replay کلید یکسان سهمیه را دوباره مصرف می‌کرد (۱۰→۹→۸) | اثر جانبی در تکرار | `_replayIfRecorded`: بازگشت رکورد ذخیره‌شده با شمارنده‌های جاری + رویداد بازسازی‌شده، بدون مصرف و انتشار | replay باید خواندن خالص باشد نه اجرای مجدد |
| 3 | تست dry-run بی‌معنا (policyId ساخته‌نشده) | assert روی `None` | assert نبود سطر شمارنده برای پنجره | dry-run باید چیزی ننویسد |
| 4 | کرن زمانی تست persistence | `since/until` از ساعت ثابت دامنه، صفر سطر | کران wall-clock ±۱ روز | `createdAt` سطر = زمان persistence (auto_now_add) نه ساعت دامنه — ثبت‌شده در قرارداد §12 |
| 5 | تایپ `limitValue` ورودی سرویس | خطای mypy در دو call-site | `_coerceLimit` در boundary سرویس + `try/except` یکدست در `updatePolicyLimit` | entity تایپ `Decimal` می‌ماند؛ تبدیل خطادار مال boundary است |
| 6 | تایپ `requestId` در `listAttempts` | `UUID \| None` با ورودی `str` ناسازگار | `UUID \| str \| None` در پورت و پیاده‌سازی Django | Django خودش normalize می‌کند |
| 7 | `assertRaises(Exception)` در تست خاموش‌کردن | B017 | `(ValidationFailedError, ValueError)` | خطای خاص، نه کور |
| 8 | نام‌های خلاف قرارداد در exceptionها | `QuotaExceededError`/`UsageAttemptNotFoundError` بدون پیشوند AI | `AIQuotaExceeded` (alias قدیمی نگه داشته شد)، `AIUsageAttemptNotFound` | قرارداد README: همهٔ خطاهای دامنه با `AI` |

## 4. تصمیم‌ها و سؤال‌های باز

- N قبل از M ساخته شد چون وابستگی ندارد؛ attempt-scoped بودن، اتصال M را
  بدون تغییر اسکیما ممکن می‌کند (بودجهٔ retry سؤال باز M است)؛
- `AICostLimitExceeded` زیرکلاس `AIQuotaExceeded` است تا هندلرهای 429 موجود
  کار کنند و `quotaType='COST'` آن را متمایز کند؛
- یکتایی کلید idempotency در DB نیست (محدودیت NULL تکراری SQL Server برای
  رشتهٔ خالی) و در repository با تراکنش enforce می‌شود؛
- ارز مخلوط در rollup/summary خطای پیکربندی می‌دهد (fail-closed) — بدون FX؛
- DEPARTMENT/PROJECT فعلاً opaque referenceاند (دامنه‌های مالک باز نشده‌اند)؛
- جدول legacy `aiUsage` و `AIService.generate` دست‌نخورده‌اند؛ هم‌گرایی با Z؛
- entity دامنه همان‌جا که aggregate روت دارد ثبت شده (`usageRecords.py`).

## 5. شواهد اجرا

| گیت | فرمان | نتیجه |
|---|---|---|
| تست واحد | `manage.py test tests.unit.testPhase13UsageMetering` | 69/69 OK |
| تست کاربردی | `manage.py test tests.application.testPhase13UsageUseCases` | 16/16 OK |
| تست یکپارچگی | `manage.py test tests.integration.testPhase13UsageContract` | 25/25 OK |
| سوئیت کامل | `manage.py test tests` | 882 تست (772 پایه + ۱۱۰ جدید)؛ ۶ شکست دقیقاً همان بدهی پیشین §6 |
| ruff check سطح N | ۱۷ مسیر جدید/لمس‌شده | All checks passed |
| ruff format سطح N | همان مسیرها | already formatted |
| mypy هفت فایل جدید N | دامنه/اپلیکیشن/repository | بدون خطا (۲۷ خطای باقی‌مانده مال سه فایل پیشین‌اند) |
| models.py | ruff | دقیقاً ۱۲۹ = عدد پیشین (افزودهٔ N صفر) |
| مهاجرت ai | `makemigrations --check` | بدون drift (فقط drift پیشین communication) |

## 6. بدهی پیشین (ثبت‌شده، خارج از Scope — دست‌نخورده)

معماری: `apps/ai/models.py` سطح‌بالا + `apps/ai/tests/test_provider.py`
(۶ شکست که با `git stash` روی درخت pristine هم تکرار شدند)؛ ruff: ~۲۲۵؛
mypy: ~۵۶۰؛ drift مهاجرت communication؛ همه در گزارش L §6 ثبت‌اند و هیچ‌کدام
به N مربوط نیستند.

## 7. راستی‌آزمایی معیارهای پذیرش

همهٔ ۲۶ بند §۱۵ قرارداد (رکورد attempt، idempotency، تعارض کلید، rollup بدون
dual-write، summary سه‌محوره، p95، هزینه از نرخ، هر دو سقف، سیاست سه‌محوره،
تقدم خاص‌ترین، اتمیک‌بودن رد، مصرفِ مستقل از نتیجه، پنجره‌های UTC، admission،
افزایش اتمیک، رویداد بدون محتوا، جداول+مهاجرت، پیکربندی، ایزولاسیون چهارلایه،
۱۱۰ تست، گیت‌های سبز، سازگاری M، مستندات) با اجرای مستقیم تست‌ها و گیت‌ها
تأیید شدند.

## 8. درخت بایگانی تحویل N

```text
backend/apps/ai/
├── domain/
│   ├── meteringPorts.py
│   ├── valueObjects/usageTypes.py
│   ├── entities/usageRecords.py
│   └── services/{usageMetering.py,quotaEnforcement.py}
├── application/services/usageService.py
└── infrastructure/{models.py,migrations/0002_usageMetering.py,repositories/usageRepositories.py}
backend/tests/{unit/testPhase13UsageMetering.py,
  application/testPhase13UsageUseCases.py,integration/testPhase13UsageContract.py}
docs/Phases/Phase13/{Phase13-N.md,Phase13-N-ExecutionReport.md}
```

## 9. زیر‌فاز بعدی

**Phase 13-M — Retry / Fallback / Timeout Executor** (مصرف‌کنندهٔ همین
قرارداد؛ نقطهٔ اتصال: `recordProviderAttempt` به‌ازای هر تلاش).
