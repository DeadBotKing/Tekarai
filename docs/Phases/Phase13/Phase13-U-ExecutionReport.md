# گزارش اجرا — Phase 13-U: Evaluation

**تاریخ:** 2026-09-05 · **وضعیت:** Evaluation Gate GREEN
**قرارداد:** [`Phase13-U.md`](Phase13-U.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل T (سوییت ۱۵۳۶ تست)

---

## ۱. خلاصهٔ تحویل

**Open Question شمارهٔ ۹ زیر‌فاز A بسته شد.** «کیفیت خروجی AI چطور سنجیده
می‌شود و قابل قبول یعنی چه» حالا دو شیء مشخص است: هشت متریک قطعی و
`EvaluationCriteria` که آستانه، وزن و اجباری‌بودن هر متریک را نگه می‌دارد و
امضایش روی هر Run حک می‌شود.

مهم‌تر از خودِ متریک‌ها، دو خاصیت معماری است: **سنجش کاملاً آفلاین است**
(هیچ متریکی به مدل زنده نیاز ندارد، پس گیت کیفیت منبع دوم بی‌ثباتی نیست)، و
**افت کیفیت خودش یک شکست است** (`compareRuns` هر Run را با قبلی می‌سنجد).

**۱۳۲ تست جدید سبز** (۶۳ واحد + ۴۱ کاربردی + ۲۸ یکپارچگی). کل سوییت از
۱۵۳۶ به **۱۶۶۸ تست** رسید با **همان ۶ شکست پیشین**. هر سه گیت کیفیت روی
فایل‌های U تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۸۳ mypy).

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۲۵۴۲ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/evaluationTypes.py` | ۳۶۲ | هشت متریک، `MetricThreshold`، `EvaluationCriteria`، ریاضی امتیاز |
| `backend/apps/ai/domain/entities/evaluationRecords.py` | ۳۲۰ | Case، Run (ماشین حالت)، Result + پل به فاز B |
| `backend/apps/ai/domain/services/evaluationEngine.py` | ۴۷۷ | `EvaluationEngine`، `EvaluationJudge`، `RunAggregator`، `compareRuns` |
| `backend/apps/ai/domain/evaluationPorts.py` | ۹۲ | چهار پورت، از جمله `AnswerProducer` |
| `backend/apps/ai/application/services/evaluationService.py` | ۸۱۲ | سرویس، `EvaluationJobHandler`، آداپتور `observationFromRagAnswer` |
| `backend/apps/ai/infrastructure/repositories/evaluationRepositories.py` | ۳۴۱ | دو store جنگو |
| `backend/apps/ai/infrastructure/migrations/0008_evaluationPlatform.py` | ۱۳۸ | سه جدول |

### ۲.۲ تست (۳ فایل، ۱۶۹۶ خط، ۱۳۲ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Evaluation.py` | ۶۳ | واژگان، ریاضی، معیار، موجودیت‌ها، هشت متریک، داور، تجمیع، رگرسیون |
| `backend/tests/application/testPhase13EvaluationUseCases.py` | ۴۱ | Case، اجرای Suite، ایزوله‌سازی خطا، رگرسیون، خواندن، نگه‌داری، کار صف، **سنجش خط لولهٔ واقعی S** |
| `backend/tests/integration/testPhase13EvaluationContract.py` | ۲۸ | قرارداد persistence سه جدول |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | سه مدل جدید |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۶ خطای جدید U |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۴ action جدید (۳۴ → ۳۸) |
| **`apps/ai/domain/valueObjects/queueTypes.py`** | **kind تازهٔ `EVALUATION` (۸ → ۹)** — الحاقیهٔ مستند به واژگان P |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های U |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export دو store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_EVALUATION_*` (۱۰ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۳۴ به ۳۸ |
| `tests/unit/testPhase13QueueWorker.py` | افزودن `EVALUATION` به تست واژگان P |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت U |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **متریک RELEVANCE دو بار اصلاح شد و هر بار تست علتش را نشان داد.**
   نسخهٔ اول پوشش توکن‌های پرسش بود؛ کلمات کوتاه («the», «was») نمره را
   پایین می‌کشیدند. نسخهٔ دوم توکن‌های ≤۳ کاراکتر را حذف کرد، ولی هنوز
   کلمهٔ پرسشی «what» یک پاسخ کاملاً درست را به WARN می‌برد. نسخهٔ نهایی
   فقط عبارت‌های **قابل‌پاسخ** (پرسش ∩ شواهد) را می‌سنجد: هیچ پاسخی به‌خاطر
   تکرارنکردن کلمهٔ پرسشی جریمه نمی‌شود. این دقیقاً همان چیزی است که تست
   باید بگیرد — یک متریک بد، نه یک آستانهٔ بد.
2. **kind تازهٔ صف به‌جای سوءاستفاده از `GENERIC`.** زیر‌فاز T از
   `GENERIC` استفاده می‌کند و دو handler روی یک kind در یک ورکر تعارض
   می‌سازد؛ افزودن `EVALUATION` با الحاقیهٔ مستند، راه درست بود.
3. **`AnswerProducer` به‌جای وابستگی مستقیم به S.** نتیجه‌اش در تست دیده
   می‌شود: همان Suite بدون یک خط تغییر، هم Producer اسکریپتی و هم خط لولهٔ
   واقعی S را می‌سنجد.
4. **امتیاز متریک‌ها داخل Result به‌صورت JSON ذخیره می‌شود، نه ردیف مجزا.**
   همیشه با هم خوانده می‌شوند و هرگز تک‌تک کوئری نمی‌شوند؛ یک insert به‌ازای
   Case به‌جای یکی به‌ازای متریک.
5. **`caseCode` روی Result تکرار شد** تا حذف یک Case طلایی، تاریخ نمره‌اش
   را پاک نکند.

## ۴. اثبات عمودی

کلاس `GradingTheRealPipelineTests` خط لولهٔ **واقعی** را می‌سنجد: ingest
سند با R → بردار با Q → پرسش با S (فیلتر مجوز واقعی K) → پاسخ →
`observationFromRagAnswer` → نمره‌دهی U. نتیجه: `GROUNDEDNESS > 0.9`،
`CITATION_COVERAGE = 1.0`، verdict = PASS. و پرسشی که هیچ شاهدی ندارد
(«سیاست سفر شرکتی») توسط همان Suite FAIL می‌گیرد.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد U | ۶۳/۶۳ ✅ |
| تست کاربردی U | ۴۱/۴۱ ✅ |
| تست یکپارچگی U | ۲۸/۲۸ ✅ |
| سوییت کامل | **۱۶۶۸ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح U | ✅ All checks passed |
| format سطح U | ✅ formatted |
| type سطح U | ✅ صفر خطا در فایل‌های U |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون drift |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۱۹ بند §۱۷ قرارداد با اجرای مستقیم تست تأیید شد. محدودیت صریح ثبت‌شده:
GROUNDEDNESS یک **کف** است (پوشش توکنی)، نه جایگزین بازبینی انسانی — که
موضوع زیر‌فاز V است.

## ۸. درخت بایگانی تحویل U

```text
backend/apps/ai/
├── domain/
│   ├── evaluationPorts.py
│   ├── valueObjects/evaluationTypes.py
│   ├── entities/evaluationRecords.py
│   └── services/evaluationEngine.py
├── application/services/evaluationService.py
└── infrastructure/{models.py,migrations/0008_evaluationPlatform.py,
    repositories/evaluationRepositories.py}
backend/tests/{unit/testPhase13Evaluation.py,
  application/testPhase13EvaluationUseCases.py,
  integration/testPhase13EvaluationContract.py}
docs/Phases/Phase13/{Phase13-U.md,Phase13-U-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

**Phase 13-V — Feedback**: بازخورد انسانی روی خروجی AI. موجودیت
`AIFeedback` و واژگان `FEEDBACK_SENTIMENTS` از فاز B و جدول `aiFeedback`
موجودند؛ V باید بازخورد را جمع کند، به Case طلایی U تبدیل کند و حلقهٔ
«بازخورد → معیار → سنجش» را ببندد.

**تحویل:** فایل `Tekarai-Phase13-U.zip` (checksum در فایل جانبی `.sha256`).
