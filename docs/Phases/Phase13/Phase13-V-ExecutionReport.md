# گزارش اجرا — Phase 13-V: Feedback

**تاریخ:** 2026-09-05 · **وضعیت:** Feedback Gate GREEN
**قرارداد:** [`Phase13-V.md`](Phase13-V.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل U (سوییت ۱۶۶۸ تست)

---

## ۱. خلاصهٔ تحویل

حلقه بسته شد. زنجیرهٔ کاملی که از Q شروع شد حالا به نقطهٔ آغازش برمی‌گردد:
**دانش (R) → بردار (Q) → بازیابی (S) → پاسخ → شکایت انسان (V) → Case طلایی
(U) → سنجش هر اجرای بعدی**. تست `ClosingTheLoopTests` این را نه با mock که
با سرویس واقعی U ثابت می‌کند: یک شکایت ثبت می‌شود، ارتقا می‌یابد، و
`evaluation.listCases()` همان Case را با پرسش و `expectedTerms` گرفته‌شده
از اصلاحیهٔ انسان برمی‌گرداند — و اجرای بعدی سنجش روی آن verdict می‌دهد.

سه تضمین معماری V: **یک انسان یک رأی** (اثر انگشت یکتا در دیتابیس)،
**هر سیگنال جایی تمام می‌شود** (ارتقا یا رد دلیل‌دار، هر دو حسابرسی‌شده)، و
**ارتقا نیازمند بازتولیدپذیری است** (پرسش + دلیل + اصلاحیه + تکرار).

**۱۲۱ تست جدید سبز** (۵۵ واحد + ۴۲ کاربردی + ۲۴ یکپارچگی). کل سوییت از
۱۶۶۸ به **۱۷۹۰ تست** رسید با **همان ۶ شکست پیشین**. هر سه گیت کیفیت روی
فایل‌های V تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۸۳ mypy).

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۱۹۳۳ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/feedbackTypes.py` | ۳۰۱ | واژگان، نگاشت دلیل→متریک، اثر انگشت، `FeedbackPolicy`، ریاضی تجمیع |
| `backend/apps/ai/domain/entities/feedbackRecords.py` | ۲۸۹ | `AIFeedbackEntry` با provenance §33، چرخهٔ triage، پروجکشن Case، پل به فاز B |
| `backend/apps/ai/domain/services/feedbackEngine.py` | ۳۲۴ | `FeedbackAggregator`، `TrendComparer`، `PromotionPlanner` |
| `backend/apps/ai/domain/feedbackPorts.py` | ۷۴ | سه پورت، از جمله `GoldenCasePublisher` به U |
| `backend/apps/ai/application/services/feedbackService.py` | ۶۹۴ | سرویس کامل + `FeedbackPromotionJobHandler` |
| `backend/apps/ai/infrastructure/repositories/feedbackRepositories.py` | ۱۸۵ | `DjangoFeedbackStore` |
| `backend/apps/ai/infrastructure/migrations/0009_feedbackPlatform.py` | ۶۶ | جدول `aiFeedbackEntries` |

### ۲.۲ تست (۳ فایل، ۱۳۳۹ خط، ۱۲۱ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Feedback.py` | ۵۵ | واژگان، امتیاز/sentiment، اثر انگشت، ریاضی، سیاست، موجودیت، تجمیع، روند، برنامه‌ریز |
| `backend/tests/application/testPhase13FeedbackUseCases.py` | ۴۲ | ثبت idempotent، triage، ارتقا و جاروب، خلاصه و روند، ایزولاسیون، نگه‌داری، کار صف، **بستن واقعی حلقه با U** |
| `backend/tests/integration/testPhase13FeedbackContract.py` | ۲۴ | قرارداد persistence، یکتایی اثر انگشت، پنجره‌های زمانی، نگه‌داری |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | مدل `AIFeedbackEntryModel` (جدول تازه؛ `aiFeedback` فاز B دست‌نخورده) |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۴ خطای جدید V |
| `apps/ai/domain/valueObjects/auditTypes.py` | **فقط ۲** action جدید (۳۸ → ۴۰) — ثبت از `FEEDBACK_RECEIVED` موجود استفاده می‌کند |
| `apps/ai/domain/valueObjects/queueTypes.py` | kind تازهٔ `FEEDBACK` (۹ → ۱۰) |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های V |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_FEEDBACK_*` (۱۱ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۳۸ به ۴۰ |
| `tests/unit/testPhase13QueueWorker.py` | افزودن `FEEDBACK` به تست واژگان P |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت V |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **ماشین حالت اصلاح شد و تستش هم با آن.** پیاده‌سازی اول فقط
   `ACCEPTED → PROMOTED` را مجاز می‌دانست، ولی جاروب خودکار باید بتواند یک
   شکایت واجد شرایط را مستقیم ارتقا دهد. قاعده به «ارتقا متضمن پذیرش است»
   تغییر کرد (چون سیاست ارتقا از triage دستی سخت‌گیرانه‌تر است) و تست قدیمی
   با دو تست تازه جایگزین شد: یکی که ارتقای مستقیم را تثبیت می‌کند و یکی
   که ثابت می‌کند سیگنال terminal هرگز زنده نمی‌شود.
2. **ساعت دامنه بر `auto_now_add` مقدم شد.** ستون‌های `createdAt` جنگو
   مقدار دامنه را نادیده می‌گیرند، ولی پنجره‌های روند دقیقاً روی همین ستون
   ساخته می‌شوند؛ مخزن بعد از insert مقدار محاسبه‌شده را صریحاً بازمی‌نویسد.
   بدون این، ویژگی روند فقط با زمان واقعی سیستم کار می‌کرد و تست‌پذیر نبود.
3. **بدون action حسابرسی تازه برای «ثبت».** `FEEDBACK_RECEIVED` از فهرست
   §36 در واژگان O موجود بود؛ ساختن `FEEDBACK_SUBMITTED` یک مفهوم را بین
   دو نام دوپاره می‌کرد.
4. **گروه‌بندی بر اساس (پرسش، دلیل).** سه شکایت دربارهٔ یک پرسش با یک
   دلیل ⇒ یک Case با `occurrences=3`؛ همان پرسش با دلیل دیگر ⇒ Case دوم.
5. **`skipped` هر رد شدن را با دلیل برمی‌گرداند** تا «چرا این شکایت Case
   نشد؟» بدون خواندن کد قابل پاسخ باشد.

## ۴. اثبات عمودی

`ClosingTheLoopTests` با سرویس واقعی U:

- شکایت (امتیاز ۲، دلیل `UNGROUNDED`، اصلاحیه) → `promoteFeedback` →
  `evaluation.listCases("FEEDBACK_GOLDEN")` یک Case با همان پرسش و
  `expectedTerms=("Line one reached ninety two percent.",)`؛
- اجرای سنجش روی آن Case: verdict = **PASS** با `COMPLETENESS = 1.0`؛
- همان Case با پاسخ بد («Output data is unavailable»): verdict = **FAIL**
  با `COMPLETENESS = 0.0` — یعنی شکایتِ دیروز، گیتِ امروز است؛
- جاروب دو شکایت مختلف را در یک پاس به دو Case تبدیل می‌کند و اجرای بعدی
  هر دو را می‌سنجد.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد V | ۵۵/۵۵ ✅ |
| تست کاربردی V | ۴۲/۴۲ ✅ |
| تست یکپارچگی V | ۲۴/۲۴ ✅ |
| سوییت کامل | **۱۷۹۰ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح V | ✅ All checks passed |
| format سطح V | ✅ formatted |
| type سطح V | ✅ صفر خطا در فایل‌های V |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون drift |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۲۰ بند §۱۶ قرارداد با اجرای مستقیم تست تأیید شد.

## ۸. درخت بایگانی تحویل V

```text
backend/apps/ai/
├── domain/
│   ├── feedbackPorts.py
│   ├── valueObjects/feedbackTypes.py
│   ├── entities/feedbackRecords.py
│   └── services/feedbackEngine.py
├── application/services/feedbackService.py
└── infrastructure/{models.py,migrations/0009_feedbackPlatform.py,
    repositories/feedbackRepositories.py}
backend/tests/{unit/testPhase13Feedback.py,
  application/testPhase13FeedbackUseCases.py,
  integration/testPhase13FeedbackContract.py}
docs/Phases/Phase13/{Phase13-V.md,Phase13-V-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

**Phase 13-W — Observability و Monitoring**: §34 متریک‌های
`requestsTotal`، `requestsFailed`، `tokensTotal`، `costTotal` و رصد
سلامت. همهٔ داده‌اش از قبل تولید می‌شود (N مصرف، O حسابرسی، P صف،
S بازیابی، U سنجش، V بازخورد)؛ W باید آن را به متریک، آستانه و هشدار
تبدیل کند.

**تحویل:** فایل `Tekarai-Phase13-V.zip` (checksum در فایل جانبی `.sha256`).
