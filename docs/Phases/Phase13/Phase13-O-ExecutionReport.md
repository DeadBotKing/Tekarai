# گزارش اجرا — Phase 13-O: Audit و Governance

**تاریخ:** 2026-09-05 · **وضعیت:** Audit/Governance Gate GREEN
**قرارداد:** [`Phase13-O.md`](Phase13-O.md) · **مجری:** Arena.ai Agent Mode

---

## 1. خلاصهٔ تحویل

دو ستون «قابل‌حسابرسی‌بودن» پلتفرم ساخته شد: دفتر حسابرسی append-only با
زنجیرهٔ hash ضد-دستکاری (GENESIS-anchored، link-walking، تشخیص fork)،
scrubber بازگشتی Secret با قاعدهٔ RESTRICTED، و موتور حکمرانی fail-closed
با ترتیب ثابت شش‌قاعده‌ای (قابلیت، allowlistها، مرز داده، بودجه). هر تصمیم
(ALLOW و DENY) با snapshot قواعد ثبت می‌شود؛ ingestion حامل `AIUsageRecorded`
فاز N و ثبت `QUOTA_DENIED` تحقق bindingای است که N به O سپرده بود؛ retention
audit و جدول‌های N با meta رکورد خودگزارش‌ده پیاده شد. ۸۷ تست جدید سبز است
و سطح O در هر سه گیت کیفیت تمیز است.

## 2. فایل‌های ایجادشده

### 2.1 کد

| فایل | نقش |
|---|---|
| `backend/apps/ai/domain/valueObjects/auditTypes.py` | واژگان بستهٔ ۱۵تایی action، actor، outcome، الگوهای scrub، `isSecretKey` |
| `backend/apps/ai/domain/entities/auditRecords.py` | `AIAuditEntry` (ارجاع بدون FK)، `AIGovernancePolicy` (تک‌تایی tenant)، `GovernanceRequest/Decision/Reason` |
| `backend/apps/ai/domain/services/auditTrail.py` | `AuditTrailService`، `scrubDetail`، `auditEntryHash`، `verifyAuditChain` (link-walking) |
| `backend/apps/ai/domain/services/governance.py` | `GovernanceService` (رجیستری + ارزیابی شش‌مرحله‌ای)، `raiseForDecision`، coercionهای boundary |
| `backend/apps/ai/domain/auditPorts.py` | `AuditRecordStore`، `GovernancePolicyStore`، `RetentionPurger` |
| `backend/apps/ai/application/services/auditService.py` | `AuditApplicationService` (سیاست، ارزیابی+ثبت، log/ingest، خواندن، purgeها) + `AuditUsageEventSink` |
| `backend/apps/ai/infrastructure/repositories/auditRepositories.py` | سه store دjango (+rebase زنجیره پس از purge؛ purge جدول‌های N بدون لمس فایل‌های N) |
| `backend/apps/ai/infrastructure/models.py` | `AIAuditTrailModel` + `AIGovernancePolicyModel` (استایل تمیز) |
| `backend/apps/ai/infrastructure/migrations/0003_auditGovernance.py` | مهاجرت کم‌حجم O |
| `backend/apps/ai/domain/exceptions/aiExceptions.py` | ۷ خطای O: `AIGovernanceDenied` (403)، `AIGovernancePolicy{AlreadyRegistered,NotFound,Invalid}`، `AIAuditRecord{Invalid,NotFound}`، `AIAuditTrailTampered` (500) |
| `backend/config/settings/base.py` + `backend/.env.example` | شش کلید `AI_AUDIT_*`/`AI_GOVERNANCE_*` |
| شش `__init__.py` دامنه/repository | export موجودیت‌ها/سرویس‌ها/خطاها/storeها |

### 2.2 تست

| فایل | حجم |
|---|---|
| `backend/tests/unit/testPhase13AuditGovernance.py` | ۴۷ تست آفلاین خالص |
| `backend/tests/application/testPhase13AuditUseCases.py` | ۲۰ تست روی SQLite واقعی |
| `backend/tests/integration/testPhase13AuditContract.py` | ۲۰ تست قرارداد persistence |

### 2.3 پیکربندی

`AI_AUDIT_ENABLED=true`، `AI_AUDIT_RETENTION_DAYS=365`،
`AI_AUDIT_INCLUDE_RESTRICTED_DETAIL=false`، `AI_GOVERNANCE_ENABLED=true`،
`AI_GOVERNANCE_DEFAULT_MAX_COST_PER_DAY=0` (نامحدود)،
`AI_GOVERNANCE_DEFAULT_CURRENCY=USD`.

### 2.4 مستندات

قرارداد O، همین گزارش، به‌روزرسانی README فاز ۱۳ و سند مادر (تیک DoD «Audit»).

## 3. تغییرات اصلاحی مستند

| # | مسئله | رفتار پیشین | رفتار پسین | چرا |
|---|---|---|---|---|
| 1 | `raiseForDecision` روی ALLOW هم raise می‌کرد | همیشه `AIGovernanceDenied` | guard `if decision.allowed: return None` | تابع raise خالص برای DENY است (تست واحد گرفت) |
| 2 | verify با مرتب‌سازی `(occurredAt, id)` رکوردهای هم‌میکروثانیه را می‌شکست | link شکستهٔ کاذب | `verifyAuditChain` لینک‌به‌لینک راه می‌رود (genesis واحد، فرزند واحد، پوشش کامل) | ترتیب زنجیره از لینک‌هاست نه زمان (تست واحد گرفت) |
| 3 | `latestHash` (دامنه و store) آخر مرتب‌سازی را برمی‌گرداند نه نوک زنجیره | head اشتباه در append هم‌زمان | نوک = رکوردی که هیچ‌کس به آن اشاره نکرده (fallback قطعی max) | head باید از گراف باشد نه sort |
| 4 | purge پیشوند، verify بازماندگان را می‌شکست | «no genesis» پس از purge | rebase در همان تراکنش حذف (genesis جدید + بازمحاسبهٔ روبه‌جلو) + سند meta | verify سخت‌گیرانه باید همیشه برقرار بماند |
| 5 | scrubber کلمهٔ `token` را fragment می‌گرفت | `totalTokens` → `[REDACTED]` | `token` فقط whole-word/`*_token`؛ الگوهای ترکیبی صریح | شمارنده‌های metering باید از scrub بگذرند (تست کاربردی گرفت) |
| 6 | تایپ ورودی‌های `list`/`Decimal`/`dict` در boundary سرویس‌ها | خطای mypy در ۱۱ call-site | `_coerceCodes`/`_coerceBudget` + coercion در `logEntry` (همان الگوی `_coerceLimit` فاز N) | entity تایپ باریک می‌ماند؛ تبدیل خطادار مال boundary است |
| 7 | پیام «Projected daily cost» | شکست تست معماری `testNoBusinessEntityNamesAppearInSourceCode` | «Forecast daily cost» | `Project` (case-sensitive substring) واژهٔ تجاری بازنشده است |
| 8 | دو edit_file اول نوبت روی `aiExceptions.py`/`__init__` ننشست | ImportError در smoke | اعمال مجدد با python + راستی‌آزمایی grep từng فایل | ابزار ویرایش گاه success کاذب می‌دهد — درس: verify-after-edit |

## 4. تصمیم‌ها و سؤال‌های باز

- ارجاع‌های audit (`requestId`/`attemptId`/`policyId`) عمداً FK ندارند تا
  purgeها هرگز cascade نکنند و ترتیب حذف مهم نباشد (اثبات با تست بقا)؛
- لیست خالی allowlist = بدون محدودیت (مستند، default-open)؛ deny صریح با
  `disabledCapabilities`؛ جایگزینی پیش‌فرض پلتفرم در سطح کل آبجکت؛
- قاعدهٔ بودجه بدون `daySpend` رد می‌شود (نه fail)؛ ناسازگاری ارز
  fail-closed؛ `providerIsExternal` را caller اعلام می‌کند (طبقه‌بندی نوع
  provider اختراع نشد)؛
- جدول legacy `aiAuditRecords` و `AIService.generate` دست‌نخورده‌اند؛
  هم‌گرایی ledger با Z (همان موضع N)؛
- تیک DoD «تمام عملیات حساس Audit شوند» عمداً باز ماند: سازوکار + ثبت
  تصمیم‌ها/مصرف/denyها/purgeها با O است، اتصال وقایع چرخه‌عمر G و executor
  آیندهٔ M با M/Z از روی `logAudit` انجام می‌شود؛
- باگ‌های ۲ تا ۴ در همین نوبت با تست قرمز→سبز شکار و اصلاح شدند (نه پنهان).

## 5. شواهد اجرا

| گیت | فرمان | نتیجه |
|---|---|---|
| تست واحد | `manage.py test tests.unit.testPhase13AuditGovernance` | 47/47 OK |
| تست کاربردی | `manage.py test tests.application.testPhase13AuditUseCases` | 20/20 OK |
| تست یکپارچگی | `manage.py test tests.integration.testPhase13AuditContract` | 20/20 OK |
| سوئیت کامل | `manage.py test tests` | 969 تست (882 پایه + ۸۷ جدید)؛ ۶ شکست دقیقاً همان بدهی پیشین §6 |
| ruff check سطح O | ۱۷ مسیر جدید/لمس‌شده | All checks passed |
| ruff format سطح O | همان مسیرها | already formatted |
| mypy هفت فایل جدید O | دامنه/اپلیکیشن/repository | بدون خطا |
| models.py | ruff | دقیقاً ۱۲۹ = عدد پیشین (افزودهٔ O صفر) |
| مهاجرت ai | `makemigrations --check` | بدون drift (فقط drift پیشین communication) |
| django check | `manage.py check` | بدون issue (در سوئیت کامل) |

## 6. بدهی پیشین (ثبت‌شده، خارج از Scope — دست‌نخورده)

معماری: `apps/ai/models.py` سطح‌بالا + `apps/ai/tests/test_provider.py`
(۶ شکست که روی درخت pristine هم تکرار می‌شوند)؛ ruff: ~۲۲۵؛ mypy: ~۵۶۰؛
drift مهاجرت communication؛ همه در گزارش L §6 ثبت‌اند و هیچ‌کدام به O
مربوط نیستند.

## 7. راستی‌آزمایی معیارهای پذیرش

همهٔ ۲۱ بند §۱۵ قرارداد با اجرای مستقیم تست‌ها و گیت‌ها تأیید شدند؛ تنها
استثنای آگاهانه: اتصال وقایع G/M (بند «اتصال M/Z بدون تغییر اسکیما» به
معنای آمادگی نقطهٔ اتصال است، نه اتصال انجام‌شده — در §14 قرارداد و §4
بالا مستند است).

## 8. درخت بایگانی تحویل O

```text
backend/apps/ai/
├── domain/
│   ├── auditPorts.py
│   ├── valueObjects/auditTypes.py
│   ├── entities/auditRecords.py
│   └── services/{auditTrail.py,governance.py}
├── application/services/auditService.py
└── infrastructure/{models.py,migrations/0003_auditGovernance.py,
    repositories/auditRepositories.py}
backend/tests/{unit/testPhase13AuditGovernance.py,
  application/testPhase13AuditUseCases.py,integration/testPhase13AuditContract.py}
docs/Phases/Phase13/{Phase13-O.md,Phase13-O-ExecutionReport.md}
```

## 9. زیر‌فاز بعدی

**Phase 13-M — Retry / Fallback / Timeout Executor** (مصرف‌کنندهٔ
`evaluateGovernance` پیش از تلاش و `logAudit` پس از هر گذار).
