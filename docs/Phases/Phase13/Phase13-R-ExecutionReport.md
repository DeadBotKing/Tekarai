# گزارش اجرا — Phase 13-R: Knowledge Ingestion، Chunking و Indexing

**تاریخ:** 2026-09-05 · **وضعیت:** Knowledge Gate GREEN
**قرارداد:** [`Phase13-R.md`](Phase13-R.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل Q (سوییت ۱۱۹۱ تست)

---

## ۱. خلاصهٔ تحویل

دروازهٔ ورود دانش ساخته شد: رجیستر منبع بر پایهٔ کلید طبیعی دامنهٔ مالک
(بدون ذخیرهٔ محتوا، §37)، سه استراتژی chunking قطعی با تضمین بودجه و
offsetهای دقیق، بازتوزیع دنبالهٔ کوتاه، `IndexPlanner` افزایشی که تصمیم
می‌گیرد چه چیزی واقعاً باید دوباره ساخته شود، سرویس اپلیکیشن با چرخهٔ حیات
کامل (ingest/reindex/archive/delete/retention) و اتصال عمودی به **Q**
(ساخت و حذف بردار chunkها)، **O** (چهار action جدید) و **P** (کار
`INDEXING`)، به‌همراه دو جدول و مهاجرت `0006`.

**۱۲۱ تست جدید سبز** (۵۵ واحد + ۴۰ کاربردی + ۲۶ یکپارچگی). کل سوییت از
۱۱۹۱ به **۱۳۱۲ تست** رسید با **همان ۶ شکست پیشین**. سطح R در هر سه گیت
کیفیت تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۸۳ mypy، عین
عدد pristine).

هیچ وابستگی جدیدی اضافه نشد و هیچ Secret یا SDK فروشنده‌ای وارد نشد.

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۲۱۸۱ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/knowledgeTypes.py` | ۲۰۳ | واژگان (۱۲ دامنه، ۳ استراتژی، ۴ verdict)، `ChunkingPolicy`، canonical کردن، checksumها، شکستن پاراگراف/جمله |
| `backend/apps/ai/domain/entities/knowledgeRecords.py` | ۲۹۰ | `AIKnowledgeSourceRecord` (کلید طبیعی، ماشین حالت، markIndexed/markFailed/archive)، `AIKnowledgeChunkRecord` (+ پل به فاز B) |
| `backend/apps/ai/domain/services/knowledgeChunker.py` | ۴۴۷ | `ChunkingService` (سه استراتژی، overlap، offset، بازتوزیع)، `IndexPlanner`، `buildChunkRecords` |
| `backend/apps/ai/domain/knowledgePorts.py` | ۹۱ | `KnowledgeSourceStore`، `KnowledgeChunkStore`، `ChunkEmbedder`، `KnowledgeAuditLogger` |
| `backend/apps/ai/application/services/knowledgeService.py` | ۷۷۱ | `KnowledgeSettings`، فرمان‌ها و descriptorها، `KnowledgeApplicationService`، `KnowledgeIngestionJobHandler` |
| `backend/apps/ai/infrastructure/repositories/knowledgeRepositories.py` | ۲۷۸ | دو store جنگو + reorder دومرحله‌ای + sweep نگه‌داری |
| `backend/apps/ai/infrastructure/migrations/0006_knowledgeIngestion.py` | ۱۰۱ | `aiKnowledgeSources` + `aiKnowledgeChunkRecords` |

### ۲.۲ تست (۳ فایل، ۱۴۸۸ خط، ۱۲۱ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Knowledge.py` | ۵۵ | واژگان، canonical/checksum، سیاست، سه استراتژی، overlap، offset، بازتوزیع، قطعیت، دو موجودیت، planner |
| `backend/tests/application/testPhase13KnowledgeUseCases.py` | ۴۰ | ingestion، noop، reindex افزایشی (append/insert/delete/edit)، اتصال به Q، شکست، archive/delete/retention، ایزولاسیون، کار صف |
| `backend/tests/integration/testPhase13KnowledgeContract.py` | ۲۶ | قرارداد persistence دو store روی SQLite واقعی |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | دو مدل جدید (استایل تمیز) |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۷ خطای جدید R |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۴ action جدید (۲۳ → ۲۷) — الحاقیهٔ هماهنگ با O |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های R |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export دو store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_KNOWLEDGE_*` (۹ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۲۳ به ۲۷ |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت R |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **بازتوزیع جایگزین ادغام شد.** پیاده‌سازی اولیه دنبالهٔ کوتاه را در
   chunk قبلی «ادغام» می‌کرد؛ هنگام تست معلوم شد این شاخه عملاً
   **دست‌نیافتنی** است: وقتی تقسیم به‌خاطر بودجه رخ داده، ادغام هم همان
   بودجه را می‌شکند و همیشه رد می‌شود. الگوریتم با **بازتوزیع کلمه** از
   chunk قبلی به دنباله جایگزین شد تا هر دو طرف بالای `minTokens` بمانند،
   و برای حالت غیرممکن (فقیر شدن chunk قبلی) شاخهٔ صریح «دست نزن» اضافه
   شد. هر دو شاخه تست دارند و تست «نه حذف نه تکرار» متن را تضمین می‌کند.
2. **حذف بردار قبل از حذف chunk.** ترتیب عمدی است: قطع در میانه حداکثر یک
   chunk بدون بردار می‌گذارد (بی‌ضرر و قابل بازسازی)، نه یک بردار یتیم که
   در جست‌وجو ظاهر شود.
3. **reorder دومرحله‌ای.** ordinalها اول به آفست ثابت شیفت می‌شوند و سپس
   به مقصد؛ swap کامل دو موقعیت هم بدون برخورد کار می‌کند و آماده برای
   افزودن unique constraint در آینده است.
4. **`resolveChunks` شناسه‌های ناشناخته را رد می‌کند، نه اینکه خطا بدهد.**
   یک hit بازیابی که chunkاش هم‌زمان purge شده باید نتیجه را کوچک کند، نه
   کل پاسخ RAG را بشکند.
5. **`FIXED_TOKEN` تنها استراتژی با overlap فعال است**؛ در حالت پاراگراف و
   جمله، مرز طبیعی خودش زمینه را حفظ می‌کند و تکرار فقط هزینهٔ بردار
   می‌سازد.
6. **پورت باریک `ChunkEmbedder`** با امضای دقیقاً منطبق بر Q؛ mypy تأیید
   می‌کند که `EmbeddingApplicationService` بدون هیچ import ساختاری آن را
   ارضا می‌کند.
7. **`WordSpan` به‌جای `_Word`.** تست معماری نام کلاس‌ها را PascalCase
   اجباری می‌کند؛ نام خصوصی با زیرخط آن گیت را قرمز کرد و اصلاح شد.

## ۴. اثبات عمودی

- **زنجیرهٔ کامل:** `ingestSource` → ۳ chunk → ۳ بردار در
  `aiEmbeddingVectors` → `searchSimilar` روی متن پاراگراف چهارم →
  `resolveChunks` متن همان chunk را برمی‌گرداند. (تست
  `testSearchFindsTheReindexedContent`.)
- **افزایشی بودن:** افزودن یک پاراگراف ⇒ `chunksAdded=1`,
  `chunksReused=3`, فراخوانی Provider **دقیقاً یک متن بیشتر**.
- **ناهمگام:** `submitJob(kind="INDEXING")` → `runOnce()` → `SUCCEEDED` با
  `resultSummary={"action": "CREATE", "chunksAdded": 3,
  "embeddingsCreated": 3}` و ردیف‌های واقعی در دیتابیس.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد R | ۵۵/۵۵ ✅ |
| تست کاربردی R | ۴۰/۴۰ ✅ |
| تست یکپارچگی R | ۲۶/۲۶ ✅ |
| سوییت کامل | **۱۳۱۲ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح R | ✅ All checks passed |
| format سطح R | ✅ ۹ فایل formatted |
| type سطح R | ✅ صفر خطا در فایل‌های R |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون drift |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`. هیچ‌کدام مربوط
به R نیست و R هیچ‌کدام را بدتر نکرد.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۲۴ بند §۱۷ قرارداد با اجرای مستقیم تست تأیید شد. استثنای آگاهانه: بند
مجوز (§۱۲) عمداً پیاده‌سازی نشده — chunkها `classification` را حمل می‌کنند
تا موتور K در S فیلتر کند.

## ۸. درخت بایگانی تحویل R

```text
backend/apps/ai/
├── domain/
│   ├── knowledgePorts.py
│   ├── valueObjects/knowledgeTypes.py
│   ├── entities/knowledgeRecords.py
│   └── services/knowledgeChunker.py
├── application/services/knowledgeService.py
└── infrastructure/{models.py,migrations/0006_knowledgeIngestion.py,
    repositories/knowledgeRepositories.py}
backend/tests/{unit/testPhase13Knowledge.py,
  application/testPhase13KnowledgeUseCases.py,
  integration/testPhase13KnowledgeContract.py}
docs/Phases/Phase13/{Phase13-R.md,Phase13-R-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

**Phase 13-S — Retrieval، RAG و Reranking**: تنها مصرف‌کنندهٔ باقی‌ماندهٔ
این زنجیره. همه‌چیزِ لازم آماده است — بردارها (Q)، chunkها با
classification (R)، موتور مجوز (K) و Context Engine (J). S باید
`Query → Embedding → Candidate → Permission Filter → Rank → Context`
را ببندد، و فیلتر مجوز **باید قبل از ساخت Context** اجرا شود (§20).

**تحویل:** فایل `Tekarai-Phase13-R.zip` (checksum در فایل جانبی `.sha256`).
