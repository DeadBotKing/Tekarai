# Phase 13-S — Retrieval، RAG و Reranking

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** S از A تا Z
**وضعیت:** COMPLETED — Retrieval Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§18، §19، §20، §21، §22، §37، §38، §40، §42، §43، §47)
**قراردادهای قبلی:** [J](Phase13-J.md) (Context Engine)، [K](Phase13-K.md) (مجوز، fail-closed)،
[I](Phase13-I.md) (Prompt)، [N](Phase13-N.md) (اندازه‌گیری)، [O](Phase13-O.md) (حسابرسی)،
[Q](Phase13-Q.md) (پایهٔ برداری)، [R](Phase13-R.md) (chunkها)
**گزارش اجرا:** [`Phase13-S-ExecutionReport.md`](Phase13-S-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز S زنجیرهٔ §20 را می‌بندد:

```text
Query → Query Embedding → Candidate Retrieval → Permission Filtering
      → Ranking → Context Construction → AI
```

سؤال معماری S:

> **چطور مطمئن شویم هیچ‌وقت داده‌ای که کاربر حق دیدنش را ندارد وارد
> Context مدل نمی‌شود؟**

پاسخ S: **با ساختار، نه با انضباط بازبین.** Pipeline یک ماشین حالت است و
`assembleContext` بدون اجرای مرحلهٔ `AUTHORIZE` اصلاً کار نمی‌کند و
`AI_RETRIEVAL_STAGE_VIOLATION` می‌دهد. یعنی «فراموش کردن فیلتر مجوز» یک
اشتباه ممکن نیست، نه یک اشتباه نامحتمل.

سؤال دوم: **وقتی هیچ شاهد مجازی پیدا نشد، چه باید کرد؟** پاسخ S: **پاسخ
ندادن.** با `requireGrounding` (پیش‌فرض روشن) به‌جای تولید پاسخ بی‌پشتوانه،
خطای `AI_RAG_UNGROUNDED` برمی‌گردد.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. واژگان بستهٔ استراتژی، rerank و مراحل pipeline؛
2. `RetrievalPolicy` تغییرناپذیر و اعتبارسنجی‌شده؛
3. ریاضی واژگانی قطعی: توکن‌سازی زبان‌خنثی، پوشش پرس‌وجو، Jaccard؛
4. Reciprocal Rank Fusion برای ترکیب برداری و کلیدواژه‌ای؛
5. سه استراتژی کاندیدا: `VECTOR`، `LEXICAL`، `HYBRID`؛
6. سه استراتژی rerank: `NONE`، `LEXICAL_BOOST`، `MMR`؛
7. `RetrievalPipeline` با ترتیب اجباری مراحل و `RetrievalTrace` قابل‌حسابرسی؛
8. ساخت Context بودجه‌دار با citation شماره‌دار؛
9. `GroundedPrompt` و پاسخ RAG با استناد؛
10. سرویس اپلیکیشن که Q، R، K و C را به هم وصل می‌کند؛
11. پیکربندی `AI_RETRIEVAL_*` و `AI_RAG_*`؛
12. سه سطح تست: خالص، کاربردی روی DB واقعی، و یکپارچگی کل زنجیره.

### 2.2 خارج از Scope

- **ذخیره‌سازی**: S هیچ جدولی ندارد (تصمیم S-D5)؛
- **مدل Reranker یادگیرنده (cross-encoder)** — زیر‌فاز W/U؛
- **حافظهٔ گفت‌وگو** — زیر‌فاز T؛
- **چرخهٔ Request/Response و ثبت مصرف پاسخ** — زیر‌فاز G/N (S فقط
  Context و Prompt را می‌سازد و از پورت تولید استفاده می‌کند)؛
- **API عمومی و permission codeهای نهایی** — زیر‌فاز Z.

---

## 3. جایگاه معماری

```text
Application (RetrievalApplicationService)
   │  ├─ CandidateSearcher      → Phase 13-Q  (بردار)
   │  ├─ ChunkTextResolver      → Phase 13-R  (متن chunk)
   │  ├─ SourcePermissionFilter → Phase 13-K  (مجوز، fail-closed)
   │  └─ GroundedGenerator      → Phase 13-C  (Provider)
   ↓
Domain (RetrievalPipeline، Reranker، RetrievalTrace، GroundedPrompt)
   ← خالص، بدون جنگو، بدون I/O
```

S هیچ‌کدام از سرویس‌های Q/R/K را import نمی‌کند؛ فقط چهار پورت باریک را
می‌شناسد که امضایشان دقیقاً منطبق بر همان سرویس‌هاست.

---

## 4. قرارداد سیاست (§S.4)

| فیلد | پیش‌فرض | معنی |
|---|---|---|
| `strategy` | `HYBRID` | منبع کاندیداها |
| `topK` | `5` | شاهد نهایی پس از rerank (سقف ۱۰۰) |
| `candidateLimit` | `200` | سقف کاندیدا قبل از مجوز (سقف ۵۰۰۰) |
| `minScore` | `None` | کف امتیاز نهایی |
| `rerank` | `LEXICAL_BOOST` | استراتژی مرتب‌سازی |
| `lexicalWeight` | `0.3` | وزن پوشش کلیدواژه در ترکیب |
| `mmrLambda` | `0.7` | توازن ربط/تنوع در MMR |
| `maxContextTokens` | `4000` | بودجهٔ توکن Context |
| `maxContextSources` | `10` | سقف بلوک شاهد |
| `requireGrounding` | `True` | پاسخ بدون شاهد ممنوع |
| `dedupeBySource` | `False` | حداکثر یک بلوک از هر سند |

---

## 5. قرارداد ترتیب مراحل (Invariant مرکزی)

`EMBED → CANDIDATES → RESOLVE → AUTHORIZE → RERANK → CONTEXT → ANSWER`

- هر مرحله یک `StageRecord` با ورودی/خروجی/دلیل ثبت می‌کند؛
- `rerank` و `assembleContext` بدون `authorize` استثنا می‌دهند؛
- خروجی `AUTHORIZE` جایگزین مجموعهٔ کاندیدا می‌شود، پس هیچ مرحلهٔ بعدی
  حتی *دسترسی* به کاندیدای ردشده ندارد؛
- `RetrievalTrace.summary()` عمداً **بدون محتوا** است: فقط شمارش و دلیل،
  تا لاگ و حسابرسی هرگز حامل متن محرمانه نشود.

---

## 6. قرارداد کاندیداها

| استراتژی | رفتار |
|---|---|
| `VECTOR` | پرس‌وجو با Q embed می‌شود؛ کاندیداها از `aiEmbeddingVectors` با `sourceType=KNOWLEDGE_CHUNK` می‌آیند |
| `LEXICAL` | هیچ embedding انجام نمی‌شود؛ پویش کلیدواژه‌ای روی chunkهای منابع `READY` با سقف `lexicalScanLimit` |
| `HYBRID` | هر دو، سپس **Reciprocal Rank Fusion** (`k=60`) |

RRF عمدی است: امتیاز کسینوسی و پوشش کلیدواژه‌ای هم‌مقیاس نیستند؛ ترکیب
رتبه‌ای این مشکل را حذف می‌کند.

**chunk حذف‌شده بین جست‌وجو و hydration** نتیجه را کوچک می‌کند، نه اینکه
کل پاسخ را بشکند.

---

## 7. قرارداد فیلتر مجوز (§20، §40)

- تنها مرجع تصمیم: `AuthorizationService.filterSources` از زیر‌فاز K؛
- هر کاندیدا به `ContextSourceCandidate` تبدیل می‌شود (همان نوعی که K
  و J می‌فهمند) و با هویت `(sourceDomain, sourceEntityType, sourceEntityId)`
  تطبیق داده می‌شود؛
- **بدون فیلتر تزریق‌شده، هیچ چیز مجاز نیست**: S به‌جای سرو کردن نتیجهٔ
  فیلترنشده، `AIConfigurationError` می‌دهد؛
- طبقه‌بندی هر chunk از منبعش به ارث رسیده و همان چیزی است که K روی آن
  تصمیم می‌گیرد.

---

## 8. قرارداد rerank

| استراتژی | رفتار |
|---|---|
| `NONE` | ترتیب بازیابی حفظ می‌شود |
| `LEXICAL_BOOST` | `(1-w)·score_norm + w·coverage_norm`؛ **هر دو سری min-max نرمال می‌شوند** تا پراکندگی یکی بر دیگری غلبه نکند |
| `MMR` | انتخاب حریصانه با `λ·ربط − (1−λ)·بیشترین شباهت به انتخاب‌شده‌ها`؛ شباهت روی **متن** (Jaccard) محاسبه می‌شود، نه بردار |

مرتب‌سازی نهایی همیشه قطعی است: `(-score, sourceReference, chunkId)`.

---

## 9. قرارداد Context و Citation

- بلوک‌ها به ترتیب رتبه و زیر سقف توکن/تعداد بسته می‌شوند؛
- هر بلوک با `[n] (reference) text` رندر می‌شود و `Citation` متناظر
  شمارهٔ همان بلوک، `chunkId`، ارجاع منبع، ordinal و امتیاز را دارد؛
- بلوک اول همیشه جا می‌گیرد (حتی اگر از بودجه بزرگ‌تر باشد) تا یک سند
  بلند به «بدون شاهد» تبدیل نشود؛
- `dedupeBySource` برای پاسخ‌هایی که تنوع منبع مهم‌تر از عمق است.

---

## 10. قرارداد RAG

1. بازیابی کامل طبق §5 تا §9؛
2. اگر شاهدی نماند و `requireGrounding` روشن باشد → `AI_RAG_UNGROUNDED`
   (بدون هیچ فراخوانی Provider)؛
3. در غیر این صورت Prompt (دستور + بلوک‌های شماره‌دار + سؤال) به پورت
   تولید می‌رود؛
4. پاسخ به‌همراه همان citationها برگردانده می‌شود؛
5. حسابرسی `RAG_ANSWERED` با outcome و تعداد استناد.

دستور پیش‌فرض grounding در دامنه است (نه در آداپتور Provider) تا همهٔ
Providerها یک قاعده بگیرند.

---

## 11. قرارداد حسابرسی (§28)

| رویداد | Action |
|---|---|
| بازیابی با حداقل یک شاهد مجاز | `RETRIEVAL_EXECUTED` (`ALLOWED`) |
| کاندیدا وجود داشت ولی همه رد شدند | `RETRIEVAL_DENIED` (`DENIED`) |
| پاسخ RAG (موفق یا امتناع) | `RAG_ANSWERED` |

جزئیات ثبت‌شده: کد فضا، شمارش کاندیدا/مجاز/ردشده/استناد، توکن Context و
خلاصهٔ trace — **بدون هیچ متن منبع**.

---

## 12. قرارداد پیکربندی (§42)

`aiRetrievalEnabled`, `aiRetrievalStrategy`, `aiRetrievalTopK`,
`aiRetrievalCandidateLimit`, `aiRetrievalMinScore`, `aiRetrievalRerank`,
`aiRetrievalLexicalWeight`, `aiRetrievalMmrLambda`,
`aiRetrievalMaxContextTokens`, `aiRetrievalMaxContextSources`,
`aiRetrievalLexicalScanLimit`, `aiRagRequireGrounding`, `aiRagAnswerModel`.

---

## 13. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIRetrievalInvalid` | `AI_RETRIEVAL_INVALID` | 422 |
| `AIRetrievalPolicyInvalid` | `AI_RETRIEVAL_POLICY_INVALID` | 422 |
| `AIRetrievalStageViolation` | `AI_RETRIEVAL_STAGE_VIOLATION` | 500 |
| `AIRagUngrounded` | `AI_RAG_UNGROUNDED` | 422 |

---

## 14. تصمیم‌های ثبت‌شده

- **S-D1 — ترتیب مراحل ساختاری است.** مجوز قبل از Context، با استثنا در
  سطح نوع، نه با بازبینی کد.
- **S-D2 — ترکیب رتبه‌ای (RRF) به‌جای نرمال‌سازی امتیاز** برای hybrid.
- **S-D3 — MMR روی متن، نه بردار.** بردارهای Q از فروشگاه خارج نمی‌شوند و
  S به هندسهٔ فضا وابسته نمی‌ماند (بستن بخشی از Open Question الگوریتم
  Reranker: reranker یادگیرنده به U/W موکول شد).
- **S-D4 — grounding پیش‌فرض اجباری.** بدون شاهد، پاسخ نه.
- **S-D5 — S هیچ جدولی ندارد.** trace در خروجی و در دفتر O زندگی می‌کند؛
  هیچ مهاجرت جدیدی در این زیر‌فاز نیست.
- **S-D6 — بلوک اول همیشه جا می‌گیرد** تا سند بلند «بی‌شاهد» نشود.
- **S-D7 — بدون handler صف.** بازیابی مسیر خواندن هم‌زمان است؛ سوءاستفاده
  از یک `JOB_KIND` نامرتبط انجام نشد.

---

## 15. Open Questions برای زیر‌فازهای بعدی

1. reranker مبتنی بر مدل (cross-encoder) و معیار پذیرشش (U/W)؛
2. کش کردن embedding پرس‌وجوهای پرتکرار (T/W)؛
3. ادغام chunkهای هم‌پوشان در یک بلوک شاهد (W)؛
4. بازنویسی/گسترش پرس‌وجو (query expansion) و اثرش بر ایزولاسیون (U)؛
5. سهمیهٔ بازیابی به‌ازای Tenant و کاربر (N/Z).

---

## 16. Acceptance Criteria

- [x] واژگان بسته و اعتبارسنجی کامل `RetrievalPolicy`؛
- [x] توکن‌سازی زبان‌خنثی (فارسی و لاتین) و پوشش پرس‌وجوی کران‌دار؛
- [x] RRF و نرمال‌سازی امتیاز با تست؛
- [x] سه استراتژی کاندیدا، شامل مسیر بدون embedding؛
- [x] سه استراتژی rerank، شامل تنوع MMR در هر دو جهت λ؛
- [x] ترتیب اجباری مراحل با استثنای صریح؛
- [x] `authorize` مجموعهٔ کاندیدا را جایگزین می‌کند؛
- [x] trace کامل، قابل‌حسابرسی و بدون محتوا؛
- [x] بودجهٔ Context، سقف منابع، dedupe و citation شماره‌دار؛
- [x] فیلتر مجوز واقعی K با grant سراسری، grant سند-محور و طبقه‌بندی؛
- [x] نبود فیلتر ⇒ امتناع (fail-closed)؛
- [x] پاسخ RAG با استناد و امتناع در نبود شاهد؛
- [x] ایزولاسیون Tenant و فضا در کل زنجیره؛
- [x] تخریب مهربان وقتی chunk بین جست‌وجو و hydration حذف شده؛
- [x] سه action حسابرسی و زنجیرهٔ سالم؛
- [x] بدون جدول و بدون مهاجرت جدید؛
- [x] ۱۰۰ تست جدید سبز (۹۶ برای S + ۴ برای اصلاح R)؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های S تمیز؛
- [x] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `GREEN — Phase 13-T may begin.`
