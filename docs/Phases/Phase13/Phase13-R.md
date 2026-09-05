# Phase 13-R — Knowledge Ingestion، Chunking و Indexing

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** R از A تا Z
**وضعیت:** COMPLETED — Knowledge Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§7، §17، §18، §19، §20، §35، §37، §38، §40، §42، §43، §46، §47)
**قراردادهای قبلی:** [B](Phase13-B.md) (`AIKnowledgeItem`/`AIKnowledgeChunk`)، [J](Phase13-J.md) (Context)،
[K](Phase13-K.md) (مجوز)، [N](Phase13-N.md) (اندازه‌گیری)، [O](Phase13-O.md) (حسابرسی)،
[P](Phase13-P.md) (صف)، [Q](Phase13-Q.md) (پایهٔ برداری)
**گزارش اجرا:** [`Phase13-R-ExecutionReport.md`](Phase13-R-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز R دروازهٔ ورود دانش به پلتفرم است: یک ردیف کسب‌وکار (سند، جلسه،
پروژه، پیام، گزارش، دستورالعمل) را می‌گیرد، به واحدهای قابل بازیابی
می‌شکند، و آن واحدها را از طریق پایهٔ برداری Q ایندکس می‌کند.

سؤال معماری R:

> **وقتی یک سند تغییر می‌کند، چقدر کار باید دوباره انجام شود؟**

پاسخ R: **فقط همان تکه‌ای که واقعاً عوض شده**. اثر انگشت محتوا تصمیم می‌گیرد
که آیا اصلاً کاری لازم است، و اثر انگشت هر chunk تصمیم می‌گیرد کدام
بردارها معتبر می‌مانند. یک ویرگول در پاراگراف سوم نباید هزینهٔ embedding کل
سند را دوباره بدهد.

سؤال دوم که R پاسخ می‌دهد: **AI چه چیزی از دانش را نگه می‌دارد؟** پاسخ §37:
فقط **Reference، Index، Metadata** — نه خود محتوای منبع. رجیستر R یک ارجاع
به ردیف مالک به‌علاوهٔ checksum است؛ chunkها ایندکس مشتق و همیشه قابل
بازتولیدند.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. واژگان بستهٔ دامنهٔ منبع، استراتژی chunking و verdict ایندکس؛
2. `ChunkingPolicy` تغییرناپذیر و اعتبارسنجی‌شده؛
3. canonical کردن محتوا و اثر انگشت SHA-256 (تشخیص تغییر واقعی)؛
4. سه استراتژی chunking قطعی: `PARAGRAPH`، `SENTENCE`، `FIXED_TOKEN`؛
5. overlap، سقف بودجه، offsetهای دقیق و بازتوزیع دنبالهٔ کوتاه؛
6. دو موجودیت: رجیستر منبع (با ماشین حالت مشترک B) و chunk مشتق؛
7. `IndexPlanner` افزایشی: CREATE / UNCHANGED / REINDEX با تفکیک
   added/reused/removed؛
8. سرویس اپلیکیشن: ingest، reindex، archive، delete، retention، خواندن؛
9. اتصال عمودی به Q (ساخت و حذف بردار chunkها)، O (چهار action) و P
   (کار `INDEXING`)؛
10. Persistence جنگو با دو جدول و مهاجرت `0006`؛
11. پیکربندی `AI_KNOWLEDGE_*`؛
12. تست واحد خالص، تست کاربردی روی SQLite و تست قرارداد persistence.

### 2.2 خارج از Scope

- **Retrieval، فیلتر مجوز، ساخت Context و RAG** — زیر‌فاز S؛
- **Reranking** — زیر‌فاز S؛
- **حافظهٔ AI** — زیر‌فاز T؛
- **استخراج متن از PDF/DOCX/صوت** — مالک محتوا (Documents/Meetings) متن را
  آماده تحویل می‌دهد؛ R پارسر فرمت نیست؛
- **Knowledge Graph و روابط معنایی** — خارج از فاز ۱۳؛
- **API عمومی و permission codeها** — زیر‌فاز Z.

---

## 3. جایگاه معماری

```text
Application (KnowledgeApplicationService، KnowledgeIngestionJobHandler)
        ↓ پورت‌ها
Domain   (ChunkingService، IndexPlanner، AIKnowledgeSourceRecord،
          AIKnowledgeChunkRecord)                   ← خالص، بدون جنگو
        ↑ پیاده‌سازی
Infrastructure (DjangoKnowledgeSourceStore، DjangoKnowledgeChunkStore،
                مهاجرت 0006)
        ↓ مصرف
Phase 13-Q (EmbeddingApplicationService) → Provider Port → مدل واقعی
```

R هرگز `EmbeddingApplicationService` را مستقیم import نمی‌کند؛ فقط پورت
باریک `ChunkEmbedder` (دو متد) را می‌شناسد.

---

## 4. قرارداد رجیستر منبع (§37)

| فیلد | قاعده |
|---|---|
| کلید طبیعی | `(tenantId, sourceDomain, sourceEntityType, sourceEntityId)` — یکتا در دیتابیس؛ یک ردیف کسب‌وکار = یک منبع |
| `checksum` | SHA-256 محتوای canonical؛ تنها معیار «تغییر کرد یا نه» |
| `status` | همان `KNOWLEDGE_STATUSES` فاز B: PENDING → INDEXING → READY/FAILED → ARCHIVED |
| `revision` | فقط با ingestion موفق یک واحد بالا می‌رود |
| `policySignature` | امضای سیاست chunking؛ تغییرش خودش باعث reindex است |
| `spaceCode` | فضای برداری Q که این منبع در آن ایندکس شده |
| `chunkCount`/`tokenCount` | شمارنده‌های ایندکس فعلی |
| `errorCode` | کد پایدار آخرین شکست؛ با موفقیت پاک می‌شود |

**محتوای منبع ذخیره نمی‌شود.** جدول `aiKnowledgeSources` هیچ ستون `content`
ندارد.

---

## 5. قرارداد Chunking (§18)

| قاعده | تضمین |
|---|---|
| قطعیت | یک متن + یک سیاست ⇒ همیشه همان chunkها و همان checksumها |
| بودجه | هیچ chunk از `maxTokens` عبور نمی‌کند |
| ساختار | `PARAGRAPH` پاراگراف‌ها را تا سقف بودجه کنار هم می‌گذارد؛ `SENTENCE` همین کار را با جمله می‌کند؛ `FIXED_TOKEN` صرفاً کلمه‌ای پر می‌کند |
| سرریز | پاراگراف/جملهٔ بزرگ‌تر از بودجه با قاعدهٔ FIXED_TOKEN شکسته می‌شود، نه اینکه بودجه نقض شود |
| overlap | دنبالهٔ chunk قبلی به اندازهٔ `overlapTokens` تکرار می‌شود |
| offset | هر chunk `startOffset`/`endOffset` دقیق در متن canonical دارد |
| دنبالهٔ کوتاه | قطعهٔ پایانی کوچک‌تر از `minTokens` با **بازتوزیع** کلمه از chunk قبلی ترمیم می‌شود (نه ادغام، چون ادغام همان بودجه‌ای را می‌شکند که باعث تقسیم شده بود) |
| بدون حذف | بازتوزیع هیچ کلمه‌ای را حذف یا تکرار نمی‌کند؛ اگر ممکن نباشد، قطعه دست‌نخورده می‌ماند |

---

## 6. قرارداد چرخهٔ حیات

`PENDING → INDEXING → READY` مسیر موفق است. شکست ⇒ `FAILED` با
`errorCode` (هرگز نیمه-READY). `ARCHIVED` پایانی است: chunkها و بردارها
حذف می‌شوند، ردیف رجیستر به‌عنوان سنگ‌قبر قابل‌حسابرسی می‌ماند و
re-ingest ممنوع است (`AI_KNOWLEDGE_SOURCE_ARCHIVED`).

---

## 7. قرارداد ایندکس افزایشی

`IndexPlanner` سه تصمیم می‌گیرد:

- **CREATE** — منبع تازه است؛
- **UNCHANGED** — checksum، سیاست، تعداد chunk و وضعیت READY همه یکسان‌اند؛
  هیچ نوشتنی، هیچ فراخوانی Provider و هیچ افزایش revision رخ نمی‌دهد؛
- **REINDEX** — در غیر این صورت، با دلیل صریح (`reason`).

قاعدهٔ بازاستفاده (**R-D3**): تطبیق بر اساس **checksum**، مستقل از
ordinal. افزودن یک پاراگراف در ابتدای سند فقط یک chunk جدید می‌سازد و بقیه
صرفاً جابه‌جا (reorder) می‌شوند؛ بردارهایشان معتبر می‌ماند. یک checksum
تکراری دو بار مصرف نمی‌شود.

---

## 8. قرارداد Ingestion

ترتیب اجرا عمداً این است:

1. chunk کردن و ساخت plan؛
2. اگر UNCHANGED ⇒ خروج فوری؛
3. `INDEXING` روی رجیستر؛
4. reorder کردن chunkهای بازاستفاده‌شده؛
5. **اول** حذف بردار chunkهای حذف‌شده، **بعد** حذف خود chunkها (قطع در
   میانه هرگز بردار یتیم باقی نمی‌گذارد)؛
6. ذخیرهٔ chunkهای جدید و embed کردن آن‌ها؛
7. `markIndexed` (checksum، شمارنده‌ها، امضای سیاست، revision+1)؛
8. حسابرسی.

هر استثنا در گام‌های ۴ تا ۶ ⇒ `markFailed` + حسابرسی با outcome=FAILED و
سپس `AIKnowledgeIngestionFailed`.

---

## 9. قرارداد اتصال به Q

- هر chunk با `sourceType="KNOWLEDGE_CHUNK"` و `sourceId=str(chunk.id)`
  ایندکس می‌شود؛ پس بازیابی S از شناسهٔ بردار مستقیماً به chunk می‌رسد؛
- `chunkId` هم روی بردار ثبت می‌شود و metadata شامل ارجاع منبع، ordinal و
  classification است؛
- بدون `spaceCode` هیچ embedding انجام نمی‌شود (ingestion فقط ساختاری)؛
- اگر `autoEmbed` روشن باشد ولی embedder تزریق نشده باشد ⇒ خطای پیکربندی
  (fail-closed)، نه ایندکس نیمه‌کاره.

---

## 10. قرارداد Persistence

| جدول | نکته |
|---|---|
| `aiKnowledgeSources` | یکتایی چهارتایی کلید طبیعی؛ ایندکس روی (tenant, status, updatedAt) و (tenant, sourceDomain) |
| `aiKnowledgeChunkRecords` | FK با `CASCADE` به منبع (chunk بدون منبع بی‌معناست)؛ ایندکس روی (tenant, source, ordinal) و (tenant, checksum) |
| بردارها | در `aiEmbeddingVectors` می‌مانند و **بدون FK**‌اند؛ حذفشان صریح و از لایهٔ اپلیکیشن است |
| `reorderChunks` | جابه‌جایی دومرحله‌ای (شیفت به آفست ثابت، سپس مقصد) تا حتی swap کامل هم برخورد نکند |

---

## 11. قرارداد حذف و Retention (§46)

- `archiveSource` — chunkها و بردارها حذف، رجیستر می‌ماند؛
- `deleteSource` — همه‌چیز حذف؛
- `purgeKnowledgeRetention` — **فقط** ردیف‌های `ARCHIVED` قدیمی‌تر از افق
  نگه‌داری؛ یک ایندکس زنده هرگز خاموش حذف نمی‌شود.

---

## 12. مرز مجوز (§20، §40)

R هیچ authorization انجام نمی‌دهد. هر chunk `classification` منبع را به ارث
می‌برد تا موتور K در pipeline زیر‌فاز S بتواند **قبل از ساخت Context**
فیلتر کند. R فقط ایزولاسیون Tenant را تضمین می‌کند.

---

## 13. قرارداد پیکربندی (§42)

| کلید | پیش‌فرض | معنی |
|---|---|---|
| `aiKnowledgeEnabled` | `true` | سوئیچ fail-closed |
| `aiKnowledgeChunkStrategy` | `PARAGRAPH` | استراتژی پیش‌فرض |
| `aiKnowledgeChunkTokens` | `512` | بودجهٔ chunk (سقف مطلق ۴۰۹۶) |
| `aiKnowledgeChunkOverlapTokens` | `64` | هم‌پوشانی |
| `aiKnowledgeMinChunkTokens` | `32` | حداقل قطعهٔ پایانی |
| `aiKnowledgeAutoEmbed` | `true` | embed خودکار chunkهای جدید |
| `aiKnowledgeEmbedBatchSize` | `32` | اندازهٔ دستهٔ embedding |
| `aiKnowledgeMaxChunksPerSource` | `500` | سقف chunk هر منبع (سقف مطلق ۲۰۰۰) |
| `aiKnowledgeRetentionDays` | `730` | افق نگه‌داری منابع بایگانی‌شده |

---

## 14. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIKnowledgeSourceAlreadyRegistered` | `AI_KNOWLEDGE_SOURCE_ALREADY_REGISTERED` | 409 |
| `AIKnowledgeSourceNotFound` | `AI_KNOWLEDGE_SOURCE_NOT_FOUND` | 404 |
| `AIKnowledgeSourceInvalid` | `AI_KNOWLEDGE_SOURCE_INVALID` | 422 |
| `AIKnowledgeSourceArchived` | `AI_KNOWLEDGE_SOURCE_ARCHIVED` | 409 |
| `AIKnowledgeChunkInvalid` | `AI_KNOWLEDGE_CHUNK_INVALID` | 422 |
| `AIKnowledgeChunkNotFound` | `AI_KNOWLEDGE_CHUNK_NOT_FOUND` | 404 |
| `AIKnowledgeIngestionFailed` | `AI_KNOWLEDGE_INGESTION_FAILED` | 500 |

---

## 15. تصمیم‌های ثبت‌شده

- **R-D1 — محتوای منبع ذخیره نمی‌شود** (فقط ارجاع + checksum + chunkها).
  متن chunk ذخیره می‌شود چون ایندکس قابل‌بازیابی است، همیشه بازتولیدپذیر
  است و با archive/delete پاک می‌شود.
- **R-D2 — چهار تصمیم تغییر با دو اثر انگشت.** checksum سند تصمیم
  «کار لازم است؟» و checksum chunk تصمیم «کدام بردار معتبر است؟».
- **R-D3 — بازاستفاده بر اساس checksum، نه ordinal** (بستن Open Question
  «سیاست بازتولید ایندکس»).
- **R-D4 — بازتوزیع به‌جای ادغام برای دنبالهٔ کوتاه.** ادغام همان بودجه‌ای
  را می‌شکست که تقسیم را ایجاب کرده بود؛ بازتوزیع هر دو طرف را بالای
  `minTokens` نگه می‌دارد و اگر ممکن نباشد دست نمی‌زند.
- **R-D5 — canonical کردن قبل از checksum.** تغییر فاصله و خط‌ خالی
  «تغییر محتوا» محسوب نمی‌شود.
- **R-D6 — بردار قبل از chunk حذف می‌شود** تا قطع در میانه بردار یتیم
  نگذارد.
- **R-D7 — R پارسر فرمت نیست.** استخراج متن از PDF/صوت وظیفهٔ دامنهٔ مالک
  است؛ ورودی R متن است.
- **R-D8 — retention فقط ARCHIVED را می‌برد.**

---

## 16. Open Questions برای زیر‌فازهای بعدی

1. chunking معنایی (semantic/hierarchical) و مدل تعیین مرز (S/W)؛
2. سیاست نسخه‌بندی موازی ایندکس هنگام تعویض مدل: فضای جدید در کنار قدیمی
   یا بازنویسی درجا (S/Z)؛
3. آیا chunkهای هم‌پوشان باید در نتیجهٔ بازیابی ادغام شوند (S)؛
4. سیاست به‌روزرسانی رویداد-محور: چه کسی ingestion را trigger می‌کند
   (دامنهٔ مالک از طریق رویداد §36 یا زمان‌بندی) (S/Z)؛
5. سقف اندازهٔ منبع در سطح Tenant و سهمیهٔ دانش (N/Z).

---

## 17. Acceptance Criteria

- [x] واژگان بسته و اعتبارسنجی سیاست chunking؛
- [x] canonical کردن محتوا و اثر انگشت مقاوم به نویز؛
- [x] سه استراتژی chunking با تضمین بودجه؛
- [x] شکستن پاراگراف/جملهٔ بزرگ‌تر از بودجه؛
- [x] overlap واقعی و offsetهای دقیق؛
- [x] بازتوزیع دنبالهٔ کوتاه بدون حذف یا تکرار متن؛
- [x] قطعیت و idempotency کامل split؛
- [x] دو موجودیت با Invariant و ماشین حالت مشترک با B + پل به B؛
- [x] plan افزایشی با CREATE/UNCHANGED/REINDEX و دلیل صریح؛
- [x] بازاستفاده از chunk جابه‌جاشده بدون embedding مجدد؛
- [x] حذف chunk یتیم به‌همراه بردارش؛
- [x] ingestion تکراری بدون تغییر = صفر نوشتن و صفر فراخوانی Provider؛
- [x] شکست ⇒ FAILED با کد پایدار و امکان تلاش مجدد؛
- [x] archive و delete با پاک‌سازی بردارها؛
- [x] retention فقط روی ARCHIVED؛
- [x] ایزولاسیون Tenant در همهٔ مسیرها؛
- [x] سوئیچ fail-closed؛
- [x] چهار action حسابرسی و زنجیرهٔ سالم؛
- [x] handler صف P برای kind `INDEXING` به‌صورت end-to-end؛
- [x] دو جدول + مهاجرت `0006_knowledgeIngestion` بدون drift؛
- [x] نُه کلید پیکربندی محیط‌محور؛
- [x] ۱۲۱ تست جدید سبز؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های R تمیز؛
- [x] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `GREEN — Phase 13-S may begin.`
