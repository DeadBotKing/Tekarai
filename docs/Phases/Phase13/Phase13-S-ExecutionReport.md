# گزارش اجرا — Phase 13-S: Retrieval، RAG و Reranking

**تاریخ:** 2026-09-05 · **وضعیت:** Retrieval Gate GREEN
**قرارداد:** [`Phase13-S.md`](Phase13-S.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل R (سوییت ۱۳۱۲ تست)

---

## ۱. خلاصهٔ تحویل

زنجیرهٔ §20 بسته شد. `Query → Embedding → Candidates → Permission Filter →
Ranking → Context → AI` حالا یک مسیر واقعی است که هر حلقه‌اش به سرویس
واقعی همان زیر‌فاز وصل است: بردار از **Q**، متن chunk از **R**، تصمیم
دسترسی از **K**، و تولید پاسخ از پورت Provider **C**.

مهم‌ترین دستاورد معماری، ساختاری‌کردن قاعدهٔ امنیتی §20 است:
`RetrievalPipeline` یک ماشین حالت است و `assembleContext`/`rerank` بدون
اجرای مرحلهٔ `AUTHORIZE` با `AI_RETRIEVAL_STAGE_VIOLATION` رد می‌شوند.
«فراموش کردن فیلتر مجوز» دیگر یک اشتباه ممکن نیست.

**۱۰۰ تست جدید سبز** (۴۵ واحد + ۳۳ کاربردی + ۱۸ یکپارچگی + ۴ تست اصلاحی
R). کل سوییت از ۱۳۱۲ به **۱۴۱۲ تست** رسید با **همان ۶ شکست پیشین**.
هر سه گیت کیفیت روی فایل‌های S تمیز است و بدهی مخزن **صفر واحد** رشد کرد
(۲۹۳ ruff و ۵۸۳ mypy، عین عدد pristine). **هیچ مهاجرت جدیدی** وجود ندارد:
S مسیر خواندن است و عمداً هیچ جدولی ندارد (تصمیم S-D5).

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۴ فایل، ۱۴۲۹ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/retrievalTypes.py` | ۲۳۳ | واژگان (۳ استراتژی، ۳ rerank، ۷ مرحله)، `RetrievalPolicy`، توکن‌سازی، پوشش پرس‌وجو، Jaccard، RRF، نرمال‌سازی |
| `backend/apps/ai/domain/services/retrievalPipeline.py` | ۵۳۹ | `RetrievalCandidate`، `StageRecord`/`RetrievalTrace`، `Reranker` (NONE/LEXICAL_BOOST/MMR)، `RetrievalPipeline`، `Citation`/`GroundedPrompt` |
| `backend/apps/ai/domain/retrievalPorts.py` | ۷۷ | پنج پورت باریک به Q، R، K، C و O |
| `backend/apps/ai/application/services/retrievalService.py` | ۵۸۰ | `RetrievalSettings`، درخواست‌ها و نتایج، `RetrievalApplicationService` (retrieve + answerQuestion) |

### ۲.۲ تست (۳ فایل، ۱۴۵۰ خط، ۹۶ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Retrieval.py` | ۴۵ | واژگان، سیاست، ریاضی واژگانی، RRF، سه rerank، ماشین حالت، trace، بودجهٔ Context و citation |
| `backend/tests/application/testPhase13RetrievalUseCases.py` | ۳۳ | مرز مجوز با K واقعی، سه استراتژی، trace، RAG، ایزولاسیون |
| `backend/tests/integration/testPhase13RetrievalContract.py` | ۱۸ | کل زنجیرهٔ R→Q→K→S روی DB واقعی: reindex، archive، delete، تغییر طبقه‌بندی، چند فضا، چند Tenant، پایداری رتبه‌بندی |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۴ خطای جدید S |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۳ action جدید (۲۷ → ۳۰) |
| `apps/ai/domain/{services,valueObjects}/__init__.py` | re-export ماژول‌های S |
| `config/settings/base.py` + `.env.example` | بلوک `AI_RETRIEVAL_*`/`AI_RAG_*` (۱۳ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۲۷ به ۳۰ |
| **`apps/ai/domain/knowledgePorts.py`**، **`…/knowledgeService.py`**، **`…/knowledgeRepositories.py`** | **اصلاح نشتی طبقه‌بندی در R (بخش ۵)** |
| `tests/{application,integration}/testPhase13Knowledge*.py` | ۴ تست جدید برای همان اصلاح |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت S |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **ترکیب رتبه‌ای به‌جای نرمال‌سازی امتیاز.** امتیاز کسینوسی Q و پوشش
   کلیدواژه‌ای هم‌مقیاس نیستند؛ RRF با ثابت ۶۰ رتبه‌ها را ترکیب می‌کند و
   نتیجه بین استقرارها بازتولیدپذیر است.
2. **نرمال‌سازی min-max داخل `LEXICAL_BOOST`.** بدون آن، هر سری که
   پراکندگی بیشتری داشت عملاً وزن پیکربندی‌شده را نادیده می‌گرفت.
3. **MMR روی متن، نه بردار.** بردارهای Q از فروشگاه خارج نمی‌شوند؛ شباهت
   Jaccard بین متن‌ها S را از هندسهٔ فضا مستقل نگه می‌دارد.
4. **`authorize` مجموعهٔ کاندیدا را جایگزین می‌کند** (نه فقط علامت‌گذاری):
   هیچ مرحلهٔ بعدی حتی به کاندیدای ردشده دسترسی ندارد.
5. **بلوک اول همیشه جا می‌گیرد.** یک پاراگراف بلندتر از بودجه نباید کل
   پاسخ را «بی‌شاهد» کند؛ بلوک‌های بعدی رد می‌شوند نه اولی.
6. **`RetrievalTrace.summary()` بدون محتواست** و تست صریح دارد که متن
   منبع در آن ظاهر نمی‌شود — چون همین خلاصه به دفتر حسابرسی می‌رود.
7. **بدون handler صف.** بازیابی مسیر خواندن هم‌زمان است؛ استفاده از یک
   `JOB_KIND` نامرتبط انجام نشد (S-D7).

## ۴. اثبات عمودی

- **کل زنجیره:** ingest سند (R) → ۲ chunk → ۲ بردار (Q) → پرسش
  «production output» → کاندیدا → فیلتر K → rerank → Context با citation
  → پاسخ Provider. تست تأیید می‌کند هر citation به یک ردیف **واقعی** در
  `aiKnowledgeChunkRecords` و یک بردار **واقعی** در `aiEmbeddingVectors`
  اشاره دارد.
- **چرخهٔ حیات:** پس از `archiveSource` یا `deleteSource`، بازیابی صفر
  کاندیدا می‌بیند و RAG با `AI_RAG_UNGROUNDED` امتناع می‌کند.
- **مرز مجوز:** کاربر بدون grant با وجود ۴ کاندیدای موجود، صفر شاهد
  می‌گیرد؛ با grant سند-محور فقط همان سند؛ با طبقه‌بندی `RESTRICTED`
  هیچ‌کدام.

## ۵. نقص میان‌فازی که تست‌های S پیدا کرد (و اصلاح شد)

تست `testReclassifiedSourceFallsOutOfAnUnprivilegedView` شکست خورد و یک
**نشتی واقعی در زیر‌فاز R** را آشکار کرد:

> وقتی طبقه‌بندی یک منبع از `INTERNAL` به `RESTRICTED` تغییر می‌کرد،
> chunkهایی که با checksum بازاستفاده می‌شدند طبقه‌بندی **قدیمی و
> بازتر** خود را نگه می‌داشتند. چون فیلتر K روی طبقه‌بندی همان chunk
> تصمیم می‌گیرد، محتوای تازه‌محرمانه‌شده همچنان به Context راه پیدا
> می‌کرد — و هر reindex بعدی هم آن را تکرار می‌کرد.

اصلاح (حداقلی و مستند):

- متد `reclassifyChunks(tenantId, sourceId, classification)` به پورت
  `KnowledgeChunkStore` و به `DjangoKnowledgeChunkStore` اضافه شد؛
- `KnowledgeApplicationService._applyPlan` هنگام تفاوت طبقه‌بندی، آن را
  روی همهٔ chunkهای منبع اعمال می‌کند؛
- چهار تست جدید (۲ کاربردی + ۲ یکپارچگی) رفتار درست و idempotent بودنش را
  تثبیت می‌کنند.

این دقیقاً همان چیزی است که تست میان‌فازی برای آن نوشته می‌شود: نقص در R
بود، ولی فقط وقتی S واقعاً از K استفاده کرد دیده شد.

## ۶. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد S | ۴۵/۴۵ ✅ |
| تست کاربردی S | ۳۳/۳۳ ✅ |
| تست یکپارچگی S | ۱۸/۱۸ ✅ |
| تست‌های اصلاحی R | ۴/۴ ✅ |
| سوییت کامل | **۱۴۱۲ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح S | ✅ All checks passed |
| format سطح S | ✅ formatted |
| type سطح S | ✅ صفر خطا در فایل‌های S |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون تغییر (S جدولی ندارد) |
| بررسی سیستم | تمیز (۰ issue) |

## ۷. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`. هیچ‌کدام مربوط
به S نیست.

## ۸. راستی‌آزمایی معیارهای پذیرش

هر ۱۹ بند §۱۶ قرارداد با اجرای مستقیم تست تأیید شد.

## ۹. درخت بایگانی تحویل S

```text
backend/apps/ai/
├── domain/
│   ├── retrievalPorts.py
│   ├── valueObjects/retrievalTypes.py
│   └── services/retrievalPipeline.py
└── application/services/retrievalService.py
backend/tests/{unit/testPhase13Retrieval.py,
  application/testPhase13RetrievalUseCases.py,
  integration/testPhase13RetrievalContract.py}
docs/Phases/Phase13/{Phase13-S.md,Phase13-S-ExecutionReport.md}
```

## ۱۰. زیر‌فاز بعدی

**Phase 13-T — AI Memory**: حافظهٔ کوتاه‌مدت/بلندمدت/گفت‌وگو با همان
قواعد Tenant، مجوز، نسخه‌بندی و حسابرسی. موجودیت `AIMemory` از فاز B و
جدول `aiMemory` از قبل موجودند؛ T باید سیاست سقف و retention (Open
Question شمارهٔ ۸ زیر‌فاز A) را ببندد و حافظه را به‌عنوان یک منبع Context
در کنار خروجی S قرار دهد.

**تحویل:** فایل `Tekarai-Phase13-S.zip` (checksum در فایل جانبی `.sha256`).
