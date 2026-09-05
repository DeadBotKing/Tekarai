# گزارش اجرا — Phase 13-Q: Embedding Foundation

**تاریخ:** 2026-09-05 · **وضعیت:** Embedding Gate GREEN
**قرارداد:** [`Phase13-Q.md`](Phase13-Q.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** `faca17a` (phase13-P)

---

## ۱. خلاصهٔ تحویل

پایهٔ برداری پلتفرم ساخته شد: `VectorSpace` به‌عنوان هویت تغییرناپذیر یک
مجموعهٔ قابل‌مقایسه (مقایسهٔ بین‌فضایی خطای صریح است)، ریاضی برداری قطعی با
سه متریک هم‌جهت، دو موجودیت با Invariant کامل، موتور خالص برنامه‌ریزی
(canonical کردن متن، حذف تکراری با اثر انگشت، کسر کش، بودجهٔ توکن،
دسته‌بندی) و رتبه‌بندی top-K با tie-break پایدار، سرویس اپلیکیشن با
ایزولاسیون Tenant و سوئیچ fail-closed، دو جدول با مهاجرت `0005`، و اتصال
واقعی به N (اندازه‌گیری)، O (چهار action حسابرسی) و P (handler کار
`EMBEDDING` به‌صورت end-to-end).

**۱۳۰ تست جدید سبز** (۶۳ واحد + ۴۰ کاربردی + ۲۷ یکپارچگی). کل سوئیت از
۱۰۶۱ به **۱۱۹۱ تست** رسید با **دقیقاً همان ۶ شکست پیشین** درخت pristine.
سطح Q در هر سه گیت کیفیت تمیز است و بدهی مخزن **صفر واحد** رشد کرد
(۲۹۳ ruff قبل و بعد).

هیچ وابستگی جدیدی اضافه نشد (بدون numpy، pgvector، FAISS، jsonschema)،
هیچ Secret و هیچ SDK فروشنده‌ای وارد نشد.

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۲۱۳۲ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/embeddingTypes.py` | ۲۹۶ | واژگان بسته (۹ نوع منبع، ۳ متریک، ۲ نُرمال‌سازی)، `VectorSpace`، ریاضی برداری، `contentFingerprint`، `normalizeText` |
| `backend/apps/ai/domain/entities/embeddingRecords.py` | ۲۱۰ | `AIVectorSpaceDefinition`، `AIStoredEmbedding` (+ پل `toDomainEmbedding` به فاز B) |
| `backend/apps/ai/domain/services/embeddingEngine.py` | ۳۴۶ | `EmbeddingItem`/`EmbeddingPlan`/`EmbeddingEngine`، `SimilarityMatch`، `rankBySimilarity` |
| `backend/apps/ai/domain/embeddingPorts.py` | ۱۰۴ | `VectorSpaceStore`، `EmbeddingStore` + دو پورت باریک `EmbeddingUsageRecorder`/`EmbeddingAuditLogger` |
| `backend/apps/ai/application/services/embeddingService.py` | ۸۲۰ | `EmbeddingSettings`، فرمان‌ها و descriptorها، `EmbeddingApplicationService`، `EmbeddingJobHandler` |
| `backend/apps/ai/infrastructure/repositories/embeddingRepositories.py` | ۲۶۹ | `DjangoVectorSpaceStore`، `DjangoEmbeddingStore` (ذخیرهٔ idempotent روی کلید کش) |
| `backend/apps/ai/infrastructure/migrations/0005_embeddingFoundation.py` | ۸۷ | `aiVectorSpaces` + `aiEmbeddingVectors` |

### ۲.۲ تست (۳ فایل، ۱۶۲۸ خط، ۱۳۰ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Embedding.py` | ۶۳ | واژگان، ریاضی، `VectorSpace`، موجودیت‌ها، برنامه‌ریزی، ساخت، رتبه‌بندی — کاملاً آفلاین |
| `backend/tests/application/testPhase13EmbeddingUseCases.py` | ۴۰ | مدیریت فضا، نوشتن، کش، جست‌وجو، اندازه‌گیری، حسابرسی، حذف/retention، کار صف |
| `backend/tests/integration/testPhase13EmbeddingContract.py` | ۲۷ | قرارداد persistence دو store روی SQLite واقعی |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | دو مدل جدید به استایل تمیز (کلاس‌های minified قدیمی دست‌نخورده) |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۹ خطای جدید Q |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۴ action جدید (۱۹ → ۲۳) — الحاقیهٔ هماهنگ با O |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های Q |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export دو store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_EMBEDDING_*` (۸ کلید) + **بازگردانی `AI_RESILIENCE`** (بخش ۵) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۱۹ به ۲۳ (همان الگوی الحاقیهٔ P) |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت Q و **اصلاح وضعیت M** |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **کلید کش شامل هویت فضا است.** `contentFingerprint` کد و بُعد فضا را وارد
   digest می‌کند، پس یک متن در دو فضا دو ردیف مستقل دارد و مدل جدید هرگز کش
   مدل قدیم را نمی‌خورد.
2. **ذخیرهٔ idempotent به‌جای خطای یکتایی.** برخورد روی
   `(tenantId, spaceCode, contentHash)` در تراکنش جداگانه گرفته می‌شود و ردیف
   موجود برمی‌گردد؛ دو نویسندهٔ هم‌زمان یک ردیف می‌سازند، نه یک استثنا.
3. **دو پورت باریک به‌جای وابستگی به N و O.** `EmbeddingUsageRecorder` و
   `EmbeddingAuditLogger` فقط یک متد دارند و امضایشان دقیقاً همان چیزی است که
   Q می‌فرستد؛ سرویس‌های واقعی N/O بدون هیچ import ساختاری آن‌ها را ارضا
   می‌کنند (تأییدشده با mypy).
4. **تک‌متن از `embed`، چند‌متن از `embedBatch`.** مطابق قرارداد C؛ تست
   `testBatchesRespectTheConfiguredCeiling` این رفتار را تثبیت می‌کند.
5. **`QUERY` گذرا است.** بردار پرس‌وجو هرگز ذخیره نمی‌شود (تست شمارش ردیف
   قبل/بعد از جست‌وجوی متنی).
6. **مخزن، فضا را از رجیستری می‌خواند، نه از ردیف بردار.** اگر ثبت فضا حذف
   شده باشد، رهیدریشن با `AI_VECTOR_SPACE_INVALID` رد می‌شود به‌جای ساختن
   موجودیتی با هندسهٔ حدسی.
7. **گرد کردن امتیاز به ۹ رقم** پیش از مقایسه، تا ترتیب روی معماری‌های
   مختلف یکسان بماند.

## ۴. اثبات عمودی (کار ناهمگام)

`submitJob(kind="EMBEDDING")` → `runOnce()` → `SUCCEEDED` با
`resultSummary={"created": 2, ...}` و دو ردیف واقعی در `aiEmbeddingVectors`،
همراه با زنجیرهٔ حسابرسی `JOB_ENQUEUED → JOB_STARTED → EMBEDDING_CREATED →
JOB_COMPLETED`. payload نامعتبر کار را با `AI_EMBEDDING_INVALID` شکست
می‌دهد، نه ورکر را.

## ۵. اصلاح خارج از Scope (ثبت‌شده و عمدی)

هنگام افزودن بلوک تنظیمات Q مشخص شد بلوک `AI_RESILIENCE` که زیر‌فاز M
(کامیت `0df22be`) به `config/settings/base.py` و `.env.example` افزوده بود،
در کامیت بعدی `fd9b289` (PHASE13-N) **حذف شده است**؛ در نتیجه
`resilienceWiring.buildResilientExecutor` روی mapping خالی کار می‌کرد و
پیکربندی واقعی retry/fallback/timeout هیچ اثری نداشت. همچنین وضعیت M در
`Phase13/README.md` به «⏳ بعدی» برگردانده شده بود و از فهرست سند مادر حذف
شده بود، در حالی که کد و ۲۷ تست M در مخزن حاضر و سبز است.

اقدام Q (حداقلی و مستند):

- بازگردانی عین بلوک `AI_RESILIENCE` و شش متغیر `.env.example` از کامیت
  `0df22be`، با یادداشت اصلاحیه در خود فایل؛
- اصلاح وضعیت M در `Phase13/README.md` و `docs/Phases/Phase13.md`.

هیچ خط دیگری از کد M/N/O/P لمس نشد. تست‌های M (۲۲ واحد + ۵ یکپارچگی) پس از
بازگردانی سبز اجرا شدند و `settings.AI_RESILIENCE` مقدار واقعی برمی‌گرداند.

## ۶. گیت‌ها (اجرا شده)

| گیت | دستور | نتیجه |
|---|---|---|
| تست واحد Q | `manage.py test tests.unit.testPhase13Embedding` | ۶۳/۶۳ ✅ |
| تست کاربردی Q | `… tests.application.testPhase13EmbeddingUseCases` | ۴۰/۴۰ ✅ |
| تست یکپارچگی Q | `… tests.integration.testPhase13EmbeddingContract` | ۲۷/۲۷ ✅ |
| سوئیت کامل | `manage.py test` | **۱۱۹۱ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح Q | `ruff check` روی ۹ مسیر Q | ✅ All checks passed |
| format سطح Q | `ruff format --check` روی ۹ مسیر Q | ✅ ۹ فایل formatted |
| type سطح Q | `mypy` روی ۹ مسیر Q | ✅ صفر خطا در فایل‌های Q |
| lint مخزن | `ruff check .` | ۲۹۳ = دقیقاً عدد pristine (افزودهٔ Q صفر) |
| type مخزن | `mypy .` | ۵۸۳ = دقیقاً عدد pristine |
| مهاجرت | `makemigrations ai --check` | بدون drift |
| بررسی سیستم | `manage.py check` | تمیز (۰ issue) |

## ۷. بدهی پیشین (دست‌نخورده)

شش شکست معماری از دو فایل ولگرد `apps/ai/models.py` و
`apps/ai/tests/test_provider.py` (ثبت‌شده در گزارش L §۶)، ۲۹۳ خطای ruff و
۵۸۳ خطای mypy مخزن، و drift مهاجرت `communication`. هیچ‌کدام به Q مربوط
نیست و Q هیچ‌کدام را بدتر نکرد.

## ۸. راستی‌آزمایی معیارهای پذیرش

هر ۲۳ بند §۱۷ قرارداد با اجرای مستقیم تست و گیت تأیید شد. تنها استثنای
آگاهانه: بند مجوز (§۱۲) عمداً پیاده‌سازی **نشده** — Q فقط Tenant و فضا را
تضمین می‌کند و فیلتر دسترسی به S/K سپرده شده است.

## ۹. درخت بایگانی تحویل Q

```text
backend/apps/ai/
├── domain/
│   ├── embeddingPorts.py
│   ├── valueObjects/embeddingTypes.py
│   ├── entities/embeddingRecords.py
│   └── services/embeddingEngine.py
├── application/services/embeddingService.py
└── infrastructure/{models.py,migrations/0005_embeddingFoundation.py,
    repositories/embeddingRepositories.py}
backend/tests/{unit/testPhase13Embedding.py,
  application/testPhase13EmbeddingUseCases.py,
  integration/testPhase13EmbeddingContract.py}
docs/Phases/Phase13/{Phase13-Q.md,Phase13-Q-ExecutionReport.md}
```

## ۱۰. زیر‌فاز بعدی

**Phase 13-R — Knowledge Ingestion، Chunking و Indexing**: مصرف‌کنندهٔ همین
پایه؛ نقطهٔ اتصال `embedTexts` با `sourceType="KNOWLEDGE_CHUNK"` و `chunkId`
واقعی، به‌همراه سیاست chunking و بازتولید ایندکس.

**تحویل:** فایل `Tekarai-Phase13-Q.zip` (checksum در فایل جانبی `.sha256`).
