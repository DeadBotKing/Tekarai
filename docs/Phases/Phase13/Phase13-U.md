# Phase 13-U — Evaluation

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** U از A تا Z
**وضعیت:** COMPLETED — Evaluation Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§16، §32، §33، §34، §38، §40، §42، §43، §46)
**قراردادهای قبلی:** [B](Phase13-B.md) (`AIEvaluation` و `EVALUATION_METHODS`)،
[H](Phase13-H.md) (Structured Output)، [N](Phase13-N.md) (هزینه و تأخیر)،
[O](Phase13-O.md) (حسابرسی)، [P](Phase13-P.md) (صف)، [S](Phase13-S.md) (RAG)،
[T](Phase13-T.md) (حافظه)
**گزارش اجرا:** [`Phase13-U-ExecutionReport.md`](Phase13-U-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

سؤال معماری U همان **Open Question شمارهٔ ۹** زیر‌فاز A است:

> **کیفیت خروجی AI چطور سنجیده می‌شود و «قابل قبول» یعنی چه؟**

پاسخ U سه بخش دارد:

1. **سنجش، قطعی و آفلاین است.** هیچ متریکی به فراخوانی یک مدل نیاز ندارد.
   یک گیت کیفیت که برای تصمیم‌گیری به مدل زنده نیاز داشته باشد، گیت نیست؛
   منبع دوم بی‌ثباتی است.
2. **«قابل قبول» داده است، نه عرف شفاهی.** `EvaluationCriteria` آستانه،
   وزن و اجباری‌بودن هر متریک را نگه می‌دارد و امضایش روی هر Run حک می‌شود.
3. **افت کیفیت خودش یک شکست است.** هر Run با Run قبلی مقایسه می‌شود و
   افت بیشتر از `regressionTolerance` (یا هر Case تازه‌شکسته) رگرسیون
   اعلام می‌شود.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. هشت متریک بستهٔ `EVALUATION_METRICS` و ریاضی قطعی هرکدام؛
2. `MetricThreshold` و `EvaluationCriteria` (بستن Open Question #9)؛
3. سه موجودیت: Case طلایی، Run و Result، با پل به فاز B؛
4. موتور امتیازدهی، داور Case و تجمیع‌گر Run؛
5. تشخیص رگرسیون بین دو Run؛
6. سرویس اپلیکیشن: ثبت Case، اجرای Suite، خواندن، مقایسه، نگه‌داری؛
7. پورت `AnswerProducer` تا هر چیزی (RAG فاز S، Provider خام، Agent آینده)
   با همان Suite سنجیده شود؛
8. سه جدول و مهاجرت `0008`؛
9. پیکربندی `AI_EVALUATION_*` و handler صف روی kind تازهٔ `EVALUATION`؛
10. سه سطح تست، شامل سنجش **واقعی** خط لولهٔ S.

### 2.2 خارج از Scope

- **داوری با مدل (LLM-as-judge)** — تصمیم U-D2؛
- **جمع‌آوری بازخورد انسانی** — زیر‌فاز V؛
- **داشبورد و هشدار کیفیت** — زیر‌فاز W؛
- **آموزش/تنظیم مدل بر اساس نتیجه** — فاز ۱۶؛
- **API عمومی** — زیر‌فاز Z.

---

## 3. جایگاه معماری

```text
Application (EvaluationApplicationService، EvaluationJobHandler)
   │  ├─ EvaluationCaseStore / EvaluationRunStore → سه جدول
   │  ├─ AnswerProducer  → هر چیزی که سنجیده می‌شود (مثلاً S)
   │  └─ EvaluationAuditLogger → Phase 13-O
   ↓
Domain (EvaluationEngine، EvaluationJudge، RunAggregator، compareRuns)
   ← خالص، بدون جنگو، بدون I/O
```

---

## 4. قرارداد Case طلایی

| فیلد | نقش |
|---|---|
| `suiteCode`/`caseCode` | کلید طبیعی، یکتا در سطح دیتابیس |
| `question` | ورودی‌ای که به سیستم تحت آزمون داده می‌شود |
| `expectedTerms` | عباراتی که یک پاسخ خوب باید داشته باشد (COMPLETENESS) |
| `forbiddenTerms` | عباراتی که هرگز نباید ظاهر شوند (SAFETY) |
| `expectedSchema` | زیرمجموعهٔ JSON Schema فاز H (SCHEMA_VALIDITY) |
| `minimumCitations` | حداقل استناد (CITATION_COVERAGE) |
| `latencyBudgetMs`/`costBudget` | بودجه‌های §26/§27 (LATENCY، COST) |

---

## 5. قرارداد معیار پذیرش (Open Question #9)

هر متریک یک باند دارد: `score < failBelow` ⇒ FAIL، `score < warnBelow` ⇒
WARN، وگرنه PASS. متریک‌های `required` اگر اصلاً سنجیده نشوند، Case را
می‌شکنند.

پیش‌فرض پلتفرم:

| متریک | failBelow | warnBelow | وزن | اجباری |
|---|---|---|---|---|
| GROUNDEDNESS | 0.50 | 0.75 | ۲.۰ | ✅ |
| SAFETY | 1.00 | 1.00 | ۲.۰ | ✅ |
| RELEVANCE | 0.40 | 0.70 | ۱.۵ | — |
| COMPLETENESS | 0.40 | 0.70 | ۱.۰ | — |
| CITATION_COVERAGE | 0.50 | 0.80 | ۱.۰ | — |
| SCHEMA_VALIDITY | 1.00 | 1.00 | ۱.۰ | — |
| LATENCY | 0.25 | 0.50 | ۰.۵ | — |
| COST | 0.25 | 0.50 | ۰.۵ | — |

در سطح Run: `minimumOverallScore=0.7`، `maximumFailedCases=0`،
`maximumWarnRatio=0.3`، `regressionTolerance=0.02`.

---

## 6. قرارداد متریک‌ها

| متریک | تعریف قطعی |
|---|---|
| GROUNDEDNESS | نسبت توکن‌های محتوایی پاسخ که در شواهد دیده می‌شوند |
| RELEVANCE | نسبت عبارت‌های **قابل‌پاسخ** پرسش (پرسش ∩ شواهد) که پاسخ به آن‌ها پرداخته |
| COMPLETENESS | نسبت `expectedTerms` موجود در پاسخ |
| CITATION_COVERAGE | استنادها تقسیم بر `minimumCitations` |
| SCHEMA_VALIDITY | دودویی، با اعتبارسنج فاز H |
| SAFETY | دودویی؛ هر عبارت ممنوع ⇒ صفر |
| LATENCY / COST | نسبت بودجه به مشاهده (سقف ۱.۰) |

نکتهٔ RELEVANCE: کلمهٔ پرسشی («what»، «چرا») هرگز در پاسخ خوب نمی‌آید؛
اندازه‌گیری در برابر شواهد انجام می‌شود تا پاسخ درست جریمه نشود.

---

## 7. قرارداد Run

`PENDING → RUNNING → COMPLETED | FAILED | CANCELLED`. Run پس از تسویه
ویرایش نمی‌شود؛ امضای معیار روی آن حک است و فقط Runهای هم‌امضا قابل
مقایسه‌اند.

---

## 8. قرارداد Result

هر Case یک ردیف: امتیاز هر متریک با verdict و توضیح، امتیاز وزنی، تأخیر،
توکن، هزینه، تعداد استناد و اثر انگشت پاسخ. `caseCode` روی Result تکرار
می‌شود تا حذف یک Case طلایی، تاریخِ نمرهٔ آن را پاک نکند.

---

## 9. قرارداد تجمیع Run

FAIL اگر: تعداد Case شکست‌خورده از سقف بیشتر باشد، یا میانگین وزنی زیر
`minimumOverallScore` باشد. WARN اگر: نسبت هشدار از سقف بیشتر باشد یا
هشداری وجود داشته باشد. وگرنه PASS.

---

## 10. قرارداد رگرسیون

مقایسه با Run قبلیِ **COMPLETED** با همان امضای معیار. رگرسیون یعنی:
Case تازه‌شکسته، یا افت کل بیشتر از tolerance، یا افت هر متریک بیشتر از
tolerance. Runهای ثابت رگرسیون نیستند. `fixedFailures` هم گزارش می‌شود.

---

## 11. قرارداد اجرا و ایزوله‌سازی خطا

- استثنای Producer در یک Case ⇒ همان Case با کد خطا FAIL می‌شود و Suite
  ادامه می‌یابد؛
- خطای سیستم تحت آزمون (`observation.errorCode`) ⇒ همان رفتار؛
- خروجی نامعتبر Producer (نه `CaseObservation`) ⇒ کل Run با FAILED تسویه
  و حسابرسی می‌شود و خطا بالا می‌رود (این نقص برنامه‌نویسی است، نه کیفیت).

---

## 12. قرارداد پیکربندی (§42)

`aiEvaluationEnabled`, `aiEvaluationMinOverallScore`,
`aiEvaluationMaxFailedCases`, `aiEvaluationMaxWarnRatio`,
`aiEvaluationRegressionTolerance`, `aiEvaluationGroundednessFailBelow`,
`aiEvaluationGroundednessWarnBelow`, `aiEvaluationMaxCasesPerRun`,
`aiEvaluationRetentionDays`, `aiEvaluationForbiddenTerms`.

---

## 13. اصلاحیهٔ واژگان صف

kind تازهٔ `EVALUATION` به `JOB_KINDS` فاز P افزوده شد (۸ → ۹) — همان الگوی
مستندی که برای واژگان حسابرسی O به کار رفت. `EvaluationJobHandler` روی همین
kind ثبت می‌شود؛ سوءاستفاده از `GENERIC` (که T از آن استفاده می‌کند) انجام
نشد.

---

## 14. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIEvaluationInvalid` | `AI_EVALUATION_INVALID` | 422 |
| `AIEvaluationCriteriaInvalid` | `AI_EVALUATION_CRITERIA_INVALID` | 422 |
| `AIEvaluationCaseAlreadyRegistered` | `AI_EVALUATION_CASE_ALREADY_REGISTERED` | 409 |
| `AIEvaluationCaseNotFound` | `AI_EVALUATION_CASE_NOT_FOUND` | 404 |
| `AIEvaluationRunNotFound` | `AI_EVALUATION_RUN_NOT_FOUND` | 404 |
| `AIEvaluationFailed` | `AI_EVALUATION_FAILED` | 500 |

---

## 15. تصمیم‌های ثبت‌شده

- **U-D1 — بستن Open Question #9 با `EvaluationCriteria`.** معیار پذیرش
  داده است و امضایش روی Run حک می‌شود.
- **U-D2 — بدون LLM-as-judge.** داوری با مدل، گیت کیفیت را غیرقطعی، گران و
  وابسته به دسترسی شبکه می‌کند. Reranker/داور مدل‌محور به W موکول شد.
- **U-D3 — GROUNDEDNESS یک کف است، نه حقیقت مطلق.** پوشش توکنی، اختراع
  آزاد را می‌گیرد ولی جای بازبینی انسانی (زیر‌فاز V) را نمی‌گیرد؛ این
  محدودیت صریحاً ثبت شده.
- **U-D4 — RELEVANCE در برابر شواهد سنجیده می‌شود** تا کلمات پرسشی پاسخ
  درست را جریمه نکنند.
- **U-D5 — یک Case خراب، Run را نمی‌کشد.**
- **U-D6 — `caseCode` روی Result تکرار می‌شود** تا تاریخ کیفیت با حذف
  Case از بین نرود.
- **U-D7 — `AnswerProducer` به‌جای وابستگی به S.** U خودش نمی‌داند چه
  چیزی را می‌سنجد؛ همین باعث شد بتواند بدون تغییر، هم S و هم Agent آیندهٔ
  Y را بسنجد.

---

## 16. Open Questions برای زیر‌فازهای بعدی

1. داور مدل‌محور و روش اعتبارسنجی خودِ داور (W)؛
2. اتصال بازخورد انسانی V به‌عنوان یک متریک (V)؛
3. آستانهٔ هشدار عملیاتی و کانال اعلان رگرسیون (W)؛
4. نمونه‌گیری خودکار Caseهای طلایی از ترافیک واقعی (W/Z)؛
5. سنجش Agentهای چندمرحله‌ای با همین Suite (Y).

---

## 17. Acceptance Criteria

- [x] هشت متریک با ریاضی قطعی و آفلاین؛
- [x] `MetricThreshold`/`EvaluationCriteria` با اعتبارسنجی کامل و امضا؛
- [x] پیش‌فرض پلتفرم با اجباری‌بودن GROUNDEDNESS و SAFETY؛
- [x] سه موجودیت با Invariant، ماشین حالت Run و پل به فاز B؛
- [x] داور Case: باندها، متریک اجباری غایب، حداقل امتیاز کل؛
- [x] تجمیع Run: سقف شکست، میانگین، نسبت هشدار؛
- [x] تشخیص رگرسیون: Case تازه‌شکسته، افت کل، افت متریک، بهبودها؛
- [x] رد مقایسهٔ Runهای با معیار متفاوت؛
- [x] ایزوله‌سازی خطای Case و تسویهٔ FAILED برای خطای برنامه‌نویسی؛
- [x] ثبت/جایگزینی/غیرفعال‌سازی Case و فهرست Suiteها؛
- [x] ایزولاسیون Tenant در Case، Run و Result؛
- [x] سوئیچ fail-closed؛
- [x] چهار action حسابرسی و زنجیرهٔ سالم؛
- [x] سه جدول + مهاجرت `0008_evaluationPlatform` بدون drift؛
- [x] handler صف روی kind تازهٔ `EVALUATION`؛
- [x] سنجش واقعی خط لولهٔ S با Q/R/K واقعی؛
- [x] ۱۳۲ تست جدید سبز؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های U تمیز؛
- [x] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `GREEN — Phase 13-V may begin.`
