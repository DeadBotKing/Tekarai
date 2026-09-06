# گزارش اجرا — Phase 13-W: Observability و Monitoring

**تاریخ:** 2026-09-05 · **وضعیت:** Observability Gate GREEN
**قرارداد:** [`Phase13-W.md`](Phase13-W.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل V (سوییت ۱۷۹۰ تست)

---

## ۱. خلاصهٔ تحویل

هر ده متریک §34 حالا تولید می‌شوند، به متن Prometheus رندر می‌شوند، قواعد
هشدار را تغذیه می‌کنند و به یک حکم سلامت پنج‌مؤلفه‌ای می‌رسند — و همهٔ
اعداد از **حقایقی که پلتفرم قبلاً ثبت کرده** می‌آیند، نه از fixture.

مهم‌ترین تصمیم معماری این است که W هیچ اندازه‌گیری از خودش ندارد: چهار
contributor روی N، P، U و V نشسته‌اند و افزودن منبع تازه یعنی ثبت یک
contributor دیگر. دومین تصمیم مهم: **مانیتورینگ نباید دقیقاً وقتی خاموش
شود که سیستم خراب است** — contributor که استثنا بدهد به‌عنوان منبع ناموفق
ثبت می‌شود و بقیهٔ پنجره سالم تحویل می‌شود.

**۱۲۴ تست جدید سبز** (۶۰ واحد + ۴۱ کاربردی + ۲۳ یکپارچگی). کل سوییت از
۱۷۹۰ به **۱۹۱۴ تست** رسید با **همان ۶ شکست پیشین**. هر سه گیت کیفیت روی
فایل‌های W تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۸۳ mypy).

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۲۲۳۹ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/observabilityTypes.py` | ۳۹۴ | رجیستری ۱۶ متریک، `MetricSample`، `AlertRule`، پاک‌سازی برچسب، صدک/نسبت، `renderPrometheus` |
| `backend/apps/ai/domain/entities/observabilityRecords.py` | ۲۳۶ | `AIMetricSnapshot`، `AIAlertEvent` با چرخهٔ حیات، `ComponentHealth`/`HealthReport` |
| `backend/apps/ai/domain/services/observabilityEngine.py` | ۴۶۸ | `MetricWindow`، `MetricCollector`، `SnapshotBuilder`، `AlertEvaluator`، `HealthEvaluator` |
| `backend/apps/ai/domain/observabilityPorts.py` | ۸۹ | چهار پورت، از جمله `MetricContributor` (نقطهٔ توسعهٔ W) |
| `backend/apps/ai/application/services/observabilityService.py` | ۷۶۳ | سرویس + چهار contributor واقعی + `MetricsCollectionJobHandler` |
| `backend/apps/ai/infrastructure/repositories/observabilityRepositories.py` | ۲۰۴ | دو store جنگو |
| `backend/apps/ai/infrastructure/migrations/0010_observabilityPlatform.py` | ۸۵ | دو جدول |

### ۲.۲ تست (۳ فایل، ۱۴۶۵ خط، ۱۲۴ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Observability.py` | ۶۰ | رجیستری، برچسب، ریاضی، قواعد، exposition، موجودیت‌ها، collector، evaluator، health |
| `backend/tests/application/testPhase13ObservabilityUseCases.py` | ۴۱ | جمع‌آوری، تخریب، exposition، هشدار و حذف تکرار، سلامت، ایزولاسیون، نگه‌داری، کار صف، **متریک واقعی از U و V** |
| `backend/tests/integration/testPhase13ObservabilityContract.py` | ۲۳ | قرارداد persistence دو جدول و دو sweep نگه‌داری |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | دو مدل جدید |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۴ خطای جدید W |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۳ action جدید (۴۰ → ۴۳) |
| `apps/ai/domain/valueObjects/queueTypes.py` | kind تازهٔ `MONITORING` (۱۰ → ۱۱) |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های W |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export دو store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_OBSERVABILITY_*`/`AI_ALERT_*` (۱۱ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۴۰ به ۴۳ |
| `tests/unit/testPhase13QueueWorker.py` | افزودن `MONITORING` به تست واژگان P |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت W |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **بدون کتابخانهٔ Prometheus.** فرمت exposition چند خط متن با قرارداد
   پایدار است؛ تست‌ها HELP، TYPE، مقدار، برچسب نقل‌قول‌شده و ترتیب قطعی
   را تثبیت می‌کنند.
2. **صدک نزدیک‌ترین‌رتبه.** p95 همیشه مقداری است که واقعاً مشاهده شده،
   پس می‌توان همان درخواست را پیدا کرد. تست صراحتاً می‌گوید نتیجه عضو
   مجموعهٔ ورودی است.
3. **سری تکراری خطاست.** دو contributor که یک شمارنده را منتشر کنند
   بی‌صدا آن را دو برابر می‌کردند؛ collector این را یک باگ سیم‌کشی
   می‌داند. همان نام با برچسب متفاوت تکراری نیست.
4. **`minimumSamples` روی قاعدهٔ نسبت خطا.** نسبت خطای ۱۰۰٪ روی یک
   درخواست هشدار نیست؛ تست هر دو مسیر (رد کردن و آتش گرفتن) را دارد.
5. **پنجرهٔ نیم‌باز و ساعت.** تست بازخورد نشان داد جمع‌آوری باید *بعد از*
   رویدادها اجرا شود؛ به‌جای شل کردن مرز پنجره، تست الگوی واقعی (جاروب
   زمان‌بندی‌شده) را بازتاب می‌دهد.
6. **حکم `UNKNOWN`.** پلتفرم بی‌ترافیک «سالم» نیست؛ سکوت داده نیست.

## ۴. اثبات عمودی

کلاس `RealContributorTests` متریک‌ها را از سرویس‌های **واقعی** می‌گیرد:

- سه Job واقعی در صف P ⇒ `aiQueueDepth = 3`؛
- یک اجرای واقعی سنجش U ⇒ `aiEvaluationScore > 0.5` و
  `aiEvaluationFailures = 0`؛
- دو بازخورد واقعی V ⇒ `aiFeedbackScore > 0.5`؛
- سوییت شکست‌خوردهٔ واقعی ⇒ `aiEvaluationFailures = 1` و سلامت پلتفرم
  **UNHEALTHY** با دلیل «failing»؛
- همان اجرا با آستانهٔ سخت‌گیرانه‌تر ⇒ هشدار `AI_EVALUATION_LOW` روی
  نمرهٔ واقعی، نه fixture؛
- exposition نهایی: `# TYPE aiQueueDepth gauge` و `aiQueueDepth 1.0`.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد W | ۶۰/۶۰ ✅ |
| تست کاربردی W | ۴۱/۴۱ ✅ |
| تست یکپارچگی W | ۲۳/۲۳ ✅ |
| سوییت کامل | **۱۹۱۴ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح W | ✅ All checks passed |
| format سطح W | ✅ formatted |
| type سطح W | ✅ صفر خطا در فایل‌های W |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون drift |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۲۲ بند §۱۶ قرارداد با اجرای مستقیم تست تأیید شد.

## ۸. درخت بایگانی تحویل W

```text
backend/apps/ai/
├── domain/
│   ├── observabilityPorts.py
│   ├── valueObjects/observabilityTypes.py
│   ├── entities/observabilityRecords.py
│   └── services/observabilityEngine.py
├── application/services/observabilityService.py
└── infrastructure/{models.py,migrations/0010_observabilityPlatform.py,
    repositories/observabilityRepositories.py}
backend/tests/{unit/testPhase13Observability.py,
  application/testPhase13ObservabilityUseCases.py,
  integration/testPhase13ObservabilityContract.py}
docs/Phases/Phase13/{Phase13-W.md,Phase13-W-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

**Phase 13-X — Tool Registry و Tool Execution**: §30 ابزارها. موجودیت‌های
`AITool` و `AIToolExecution` و واژگان `TOOL_EXECUTION_STATUSES` از فاز B
موجودند؛ X باید Open Question شمارهٔ ۱۰ (رجیستری و گردش‌کار تأیید ابزار)
را ببندد و اجرای ابزار را زیر همان حکمرانی fail-closed زیر‌فاز O ببرد.

**تحویل:** فایل `Tekarai-Phase13-W.zip` (checksum در فایل جانبی `.sha256`).
