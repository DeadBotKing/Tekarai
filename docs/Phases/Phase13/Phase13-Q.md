# Phase 13-Q — Embedding Foundation

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** Q از A تا Z
**وضعیت:** COMPLETED — Embedding Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§7، §18، §19، §20، §35، §37، §38، §40، §42، §43، §46، §47)
**قراردادهای قبلی:** [B](Phase13-B.md) (موجودیت‌های پایه)، [C](Phase13-C.md) (`embed`/`embedBatch`)،
[D](Phase13-D.md)/[E](Phase13-E.md) (رجیستری Provider و Model)، [K](Phase13-K.md) (مجوز)،
[L](Phase13-L.md) (آداپتورها)، [M](Phase13-M.md) (تاب‌آوری)، [N](Phase13-N.md) (اندازه‌گیری)،
[O](Phase13-O.md) (حسابرسی)، [P](Phase13-P.md) (صف و ورکر)
**گزارش اجرا:** [`Phase13-Q-ExecutionReport.md`](Phase13-Q-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز Q پایهٔ برداری پلتفرم را می‌سازد: تبدیل متن به بردار، نگه‌داری آن
بردار در کنار *ارجاع* به ردیف کسب‌وکار، و جست‌وجوی شباهت روی همان بردارها.
این کف لازم برای R (ingestion و chunking)، S (retrieval و RAG) و T (حافظه)
است.

سؤال معماری Q یکی است و همه‌چیز از آن مشتق می‌شود:

> **چه تضمینی باعث می‌شود دو بردار قابل مقایسه باشند، و چه چیزی مقایسه را
> ممنوع می‌کند؟**

پاسخ Q: **Vector Space**. بردارها فقط وقتی قابل مقایسه‌اند که کد فضا، مدل،
نسخهٔ مدل، بُعد، متریک و نُرمال‌سازی‌شان یکی باشد. هر مقایسهٔ بین‌فضایی خطای
دامنه است، نه یک تبدیل ضمنی. این تصمیم، سؤال «مدل را عوض کردیم، ایندکس قدیمی
چه می‌شود؟» را از یک فاجعهٔ خاموش به یک خطای صریح تبدیل می‌کند.

Q مالک محتوای کسب‌وکار نیست: از هر منبع فقط `sourceType` + `sourceId`،
اثر انگشت محتوا (SHA-256) و بردار را نگه می‌دارد (§37).

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. واژگان بستهٔ منبع، متریک و نُرمال‌سازی؛
2. `VectorSpace` به‌عنوان هویت تغییرناپذیر یک مجموعهٔ قابل‌مقایسه؛
3. ریاضی برداری قطعی: نُرم، نُرمال‌سازی، cosine، dot، euclidean، تبدیل
   فاصله به شباهت؛
4. اثر انگشت محتوا برای کش و idempotency؛
5. دو موجودیت: تعریف فضا و بردار ذخیره‌شده، با Invariantهای کامل؛
6. موتور خالص: برنامه‌ریزی (canonicalization، حذف تکراری، کسر کش، بودجهٔ
   توکن، دسته‌بندی)، ساخت موجودیت از پاسخ Provider، رتبه‌بندی top-K قطعی؛
7. پورت‌های persistence و دو پورت باریک برای N و O؛
8. سرویس اپلیکیشن: مدیریت فضا، embedding، جست‌وجو، حذف و retention؛
9. Persistence جنگو با دو جدول و مهاجرت؛
10. اتصال به N (اندازه‌گیری)، O (حسابرسی) و P (کار ناهمگام `EMBEDDING`)؛
11. پیکربندی محیط‌محور و کلیدهای `AI_EMBEDDING_*`؛
12. تست واحد خالص، تست کاربردی روی SQLite واقعی و تست قرارداد persistence.

### 2.2 خارج از Scope

- **Chunking و ingestion دانش** — زیر‌فاز R؛
- **Retrieval pipeline، permission filtering و RAG** — زیر‌فاز S (فیلتر مجوز
  با موتور K انجام می‌شود، **قبل از** ساخت Context، §20)؛
- **حافظهٔ AI** — زیر‌فاز T؛
- **Reranking** — زیر‌فاز S؛
- **ANN/Vector Store تخصصی** (pgvector، FAISS، Qdrant) — تصمیم Q-D2 پایین؛
- **API عمومی و permission codeها** — زیر‌فاز Z؛
- تغییر در کد N، O، P، M یا L به‌جز الحاقیهٔ مستندشدهٔ واژگان O.

---

## 3. جایگاه معماری

```text
Application (EmbeddingApplicationService، EmbeddingJobHandler)
        ↓ پورت‌ها
Domain   (VectorSpace، AIVectorSpaceDefinition، AIStoredEmbedding،
          EmbeddingEngine، rankBySimilarity)         ← خالص، بدون جنگو
        ↑ پیاده‌سازی
Infrastructure (DjangoVectorSpaceStore، DjangoEmbeddingStore، مهاجرت 0005)
        ↓ مصرف
Provider Port (C) → آداپتورهای L → مدل واقعی
```

- دامنه هیچ import از Django، ORM، HTTP، شبکه، SDK یا صف ندارد؛
- سرویس اپلیکیشن هیچ ریاضی برداری ندارد؛ همه در `embeddingEngine`؛
- Q هیچ Provider را انتخاب نمی‌کند: `EmbeddingProviderResolver` را
  composition root از روی رجیستری D/E می‌سازد.

---

## 4. قرارداد Embedding (§18)

### 4.1 موجودیت `AIStoredEmbedding`

| فیلد | قاعده |
|---|---|
| `tenantId` | UUID اجباری؛ همهٔ خواندن/نوشتن‌ها tenant-scoped |
| `space` | `VectorSpace`؛ بُعد بردار باید دقیقاً برابر `space.dimensions` باشد |
| `sourceType` | از واژگان بسته (`KNOWLEDGE_CHUNK`, `DOCUMENT`, `MESSAGE`, `TASK`, `PROJECT`, `MEMORY`, `QUERY`, `KNOWLEDGE_ITEM`, `CUSTOM`) |
| `sourceId` | رشتهٔ ارجاع، حداکثر ۱۶۰ کاراکتر، بدون FK (§37) |
| `vector` | tuple از floatهای متناهی؛ `nan`/`inf` رد می‌شود |
| `contentHash` | SHA-256 شصت‌وچهار حرفی؛ کلید کش و idempotency |
| `chunkId` | اختیاری؛ پل به `AIKnowledgeChunk` فاز B برای R |
| `tokenCount` | ≥ 0؛ تخمین محافظه‌کارانهٔ `aiRules.estimateTokens` |

اگر فضا `normalization=L2` اعلام کند، بردار **باید** واحد باشد؛ موجودیت
بردار غیرواحد را نمی‌پذیرد (خطا، نه نُرمال‌سازی خاموش).

### 4.2 پل به فاز B

`toDomainEmbedding()` موجودیت Q را به `AIEmbedding` فاز B تبدیل می‌کند تا
مصرف‌کنندگان قبلی نشکنند. چون `AIEmbedding` به `modelId` قطعی نیاز دارد،
ردیف بدون `modelId` صریحاً تبدیل نمی‌شود و خطا می‌دهد.

---

## 5. قرارداد Vector Space (Invariant مرکزی)

1. امضای فضا: `code|modelCode|modelVersion|dimensions|metric|normalization`؛
2. دو بردار فقط با امضای یکسان قابل مقایسه‌اند؛ هر مقایسهٔ دیگر
   `AI_VECTOR_SPACE_MISMATCH` است؛
3. فضا قبل از استفاده باید در همان Tenant ثبت شده باشد؛
4. **فضای غیرفعال فقط برای نوشتن بسته است، برای خواندن باز می‌ماند** — تا
   مهاجرت مدل بتواند ایندکس قدیمی را تخلیه کند بدون از دست دادن جست‌وجو؛
5. یکتایی `(tenantId, code)` در سطح دیتابیس؛ همان کد در Tenant دیگر مجاز است.

---

## 6. قرارداد متریک (§18)

| متریک | تعریف | جهت |
|---|---|---|
| `COSINE` | شباهت کسینوسی، clamp به `[-1, 1]` | بزرگ‌تر = شبیه‌تر |
| `DOT_PRODUCT` | ضرب داخلی | بزرگ‌تر = شبیه‌تر |
| `EUCLIDEAN` | فاصله، تبدیل‌شده به `1/(1+d)` | بزرگ‌تر = شبیه‌تر |

`similarityFor` تضمین می‌کند در هر سه متریک «بزرگ‌تر یعنی شبیه‌تر»، پس
مصرف‌کننده هرگز لازم نیست جهت را بداند. بردار صفر برای cosine تعریف‌نشده
است و رد می‌شود، نه اینکه صفر برگرداند.

---

## 7. قرارداد رتبه‌بندی

1. امتیازها به ۹ رقم اعشار گرد می‌شوند (`SCORE_PRECISION`) تا خطای شناور
   ترتیب را عوض نکند؛
2. مرتب‌سازی: `(-score, sourceType, sourceId, embeddingId)` — دو اجرا روی
   یک داده هرگز نتیجهٔ متفاوت نمی‌دهند؛
3. **`SimilarityMatch` هیچ محتوایی حمل نمی‌کند**: فقط شناسه، ارجاع، امتیاز،
   اثر انگشت و متادیتای غیرحساس. متن در S از دامنهٔ مالک خوانده می‌شود، آن هم
   بعد از فیلتر مجوز؛
4. `minScore` قبل از `topK` اعمال می‌شود.

---

## 8. قرارداد برنامه‌ریزی (Plan)

`EmbeddingEngine.plan` ترتیب ورودی را حفظ می‌کند و:

1. متن را canonical می‌کند (NFC + فشرده‌سازی فاصله)؛
2. اثر انگشت را داخل فضا می‌سازد (فضا بخشی از digest است)؛
3. اثر انگشت‌های شناخته‌شده (کش) را کسر می‌کند → `cached`؛
4. تکراری‌های داخل همان درخواست را حذف می‌کند → `duplicates`؛
5. متن بزرگ‌تر از بودجهٔ توکن را **رد می‌کند، truncate نمی‌کند**؛
6. باقی‌مانده را به دسته‌های `maxBatchSize` می‌شکند؛
7. سقف مطلق ۵۱۲ آیتم را مستقل از پیکربندی اعمال می‌کند.

---

## 9. قرارداد فراخوانی Provider

1. یک متن → `provider.embed`؛ چند متن → `provider.embedBatch` (قرارداد C)؛
2. تعداد بردارهای برگشتی باید با تعداد ورودی برابر باشد، وگرنه **کل دسته**
   رد می‌شود (بردار ناهم‌تراز هرگز ذخیره نمی‌شود)؛
3. بُعد هر بردار باید با فضا بخواند، وگرنه `AI_VECTOR_SPACE_MISMATCH`؛
4. نُرمال‌سازی طبق سیاست فضا اعمال می‌شود؛
5. هیچ SDK فروشنده‌ای در Q import نمی‌شود.

---

## 10. قرارداد کش و Idempotency (§45)

- کلید کش: `(tenantId, spaceCode, contentHash)`، یکتا در سطح دیتابیس؛
- همان متن در همان فضا دوباره Provider را صدا نمی‌زند و ردیف موجود
  به‌عنوان `reused` برمی‌گردد؛
- `useCache=False` کش را دور می‌زند ولی یکتایی دیتابیس باقی است: نوشتن
  هم‌زمان یا تکراری به‌جای خطا، ردیف موجود را برمی‌گرداند (idempotent-save)؛
- `replaceExisting=True` ابتدا بردارهای همان منبع را حذف و سپس بازتولید
  می‌کند (به‌روزرسانی سند).

---

## 11. قرارداد جست‌وجو

1. ورودی یا بردار پرس‌وجو است یا متن؛ متن با همان فضا embed می‌شود و
   **ذخیره نمی‌شود** (`QUERY` گذرا است)؛
2. اسکن brute-force با سقف `candidateLimit` و فیلتر اختیاری `sourceTypes`؛
3. رتبه‌بندی با قواعد §7؛
4. خروجی `SearchResult` شامل تعداد اسکن‌شده و اینکه پرس‌وجو embed شد یا نه —
   برای رصدپذیری W.

---

## 12. مرز مجوز (§20، §40)

Q **هیچ authorization انجام نمی‌دهد**. تنها تضمین‌های امنیتی Q:
ایزولاسیون Tenant در هر خواندن/نوشتن، و یکپارچگی فضا. فیلتر دسترسی سطح
منبع با موتور K و در pipeline زیر‌فاز S اعمال می‌شود، **قبل از** ساخت
Context. این مرز عمداً در Q بسته نشده تا دو نقطهٔ تصمیم مجوز به وجود نیاید.

---

## 13. قرارداد پیکربندی (§42)

| کلید | پیش‌فرض | معنی |
|---|---|---|
| `aiEmbeddingEnabled` | `true` | سوئیچ fail-closed؛ `false` خواندن و نوشتن را رد می‌کند |
| `aiEmbeddingMaxBatchSize` | `32` | سقف دستهٔ Provider (سقف مطلق ۵۱۲) |
| `aiEmbeddingMaxInputTokens` | `8192` | سقف توکن یک متن |
| `aiEmbeddingDefaultMetric` | `COSINE` | متریک پیش‌فرض فضای جدید |
| `aiEmbeddingDefaultNormalization` | `L2` | نُرمال‌سازی پیش‌فرض فضای جدید |
| `aiEmbeddingCacheEnabled` | `true` | کش اثر انگشت |
| `aiEmbeddingSearchCandidateLimit` | `1000` | سقف اسکن جست‌وجو |
| `aiEmbeddingRetentionDays` | `365` | افق نگه‌داری بردار (§46) |

---

## 14. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIVectorSpaceAlreadyRegistered` | `AI_VECTOR_SPACE_ALREADY_REGISTERED` | 409 |
| `AIVectorSpaceNotFound` | `AI_VECTOR_SPACE_NOT_FOUND` | 404 |
| `AIVectorSpaceInvalid` | `AI_VECTOR_SPACE_INVALID` | 422 |
| `AIVectorSpaceInactive` | `AI_VECTOR_SPACE_INACTIVE` | 409 |
| `AIVectorSpaceMismatch` | `AI_VECTOR_SPACE_MISMATCH` | 409 |
| `AIEmbeddingInvalid` | `AI_EMBEDDING_INVALID` | 422 |
| `AIEmbeddingNotFound` | `AI_EMBEDDING_NOT_FOUND` | 404 |
| `AIEmbeddingAlreadyRegistered` | `AI_EMBEDDING_ALREADY_REGISTERED` | 409 |
| `AIEmbeddingBatchTooLarge` | `AI_EMBEDDING_BATCH_TOO_LARGE` | 422 |

بودجهٔ توکن از `AITokenLimitExceeded` موجود استفاده می‌کند و سوئیچ خاموش از
`AIConfigurationError` — کد جدید بی‌دلیل ساخته نشد.

---

## 15. تصمیم‌های ثبت‌شده

- **Q-D1 — فضا هویت است، نه برچسب.** مقایسه بین دو فضا خطاست. هزینه: مهاجرت
  مدل نیاز به فضای جدید و بازتولید دارد؛ سود: هیچ ایندکس آلوده‌ای بی‌صدا
  تولید نمی‌شود.
- **Q-D2 — بستن Open Question #7 برای Q: بدون Vector Store اختصاصی.**
  بردارها در ستون JSON و جست‌وجو brute-force با سقف پیکربندی‌شده است.
  دلیل: قاعدهٔ «بدون وابستگی جدید» و پشتیبانی SQL Server بدون افزونهٔ برداری.
  `EmbeddingStore` یک پورت است، پس pgvector/FAISS/Qdrant بعداً فقط یک آداپتور
  دیگر است. انتخاب ANN و Reranker همچنان برای S باز است.
- **Q-D3 — نُرمال‌سازی L2 پیش‌فرض.** cosine و dot را هم‌ارز و امتیازها را
  بین Providerها پایدار می‌کند.
- **Q-D4 — رد کردن به‌جای truncate.** متن بلندتر از بودجه خطا می‌دهد؛ برش
  متن تصمیم R (chunking) است، نه یک اثر جانبی خاموش.
- **Q-D5 — اندازه‌گیری فقط با هویت.** بدون `UsageAttribution` هیچ رکورد
  مصرفی ساخته نمی‌شود؛ Q شناسهٔ ساختگی تولید نمی‌کند.
- **Q-D6 — فضای غیرفعال خواندنی می‌ماند** (بند §5.4).
- **Q-D7 — بردار در descriptor نیست.** خروجی‌های خواندنی فقط ابرداده دارند.

---

## 16. Open Questions برای زیر‌فازهای بعدی

1. الگوریتم ANN و آستانهٔ گذار از brute-force به ایندکس تخصصی (S/W)؛
2. الگوریتم Reranker و مدل آن (S)؛
3. سیاست chunking (اندازه، هم‌پوشانی، مرز جمله) (R)؛
4. سیاست بازتولید ایندکس هنگام تعویض مدل: نسخهٔ موازی یا بازنویسی (R/Z)؛
5. آیا embedding پرس‌وجو باید کش شود (T/W)؛
6. جای permission filtering در pipeline نهایی و کد مجوزها (S/K/Z).

---

## 17. Acceptance Criteria

- [x] واژگان بسته و ریاضی برداری قطعی با تست؛
- [x] `VectorSpace` با امضا، تطبیق و سیاست نُرمال‌سازی؛
- [x] رد مقایسهٔ بین‌فضایی؛
- [x] دو موجودیت با Invariant کامل و پل به فاز B؛
- [x] برنامه‌ریزی با canonicalization، حذف تکراری، کسر کش و دسته‌بندی؛
- [x] رد متن فراتر از بودجهٔ توکن (بدون truncate)؛
- [x] سقف مطلق و سقف پیکربندی‌شدهٔ دسته؛
- [x] اعتبارسنجی تعداد و بُعد پاسخ Provider قبل از ذخیره؛
- [x] رتبه‌بندی قطعی با tie-break پایدار و خروجی بدون محتوا؛
- [x] کش اثر انگشت و ذخیرهٔ idempotent در سطح دیتابیس؛
- [x] `replaceExisting` برای به‌روزرسانی منبع؛
- [x] ایزولاسیون Tenant در فضا، بردار، جست‌وجو و حذف؛
- [x] فضای غیرفعال: نوشتن ممنوع، خواندن مجاز؛
- [x] سوئیچ fail-closed؛
- [x] اندازه‌گیری N فقط با attribution و با فرمان درست؛
- [x] چهار action حسابرسی O و زنجیرهٔ سالم پس از آن‌ها؛
- [x] handler صف P برای kind `EMBEDDING` به‌صورت end-to-end؛
- [x] دو جدول + مهاجرت `0005_embeddingFoundation` بدون drift؛
- [x] هشت کلید پیکربندی محیط‌محور؛
- [x] ۱۳۰ تست جدید سبز؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های Q تمیز؛
- [x] بدون وابستگی جدید و بدون Secret؛
- [x] مستندات قرارداد و گزارش اجرا.

**نتیجهٔ Gate:** `GREEN — Phase 13-R may begin.`
