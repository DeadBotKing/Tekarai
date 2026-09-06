# Phase 13-W — Observability و Monitoring

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** W از A تا Z
**وضعیت:** COMPLETED — Observability Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§26، §27، §28، §34، §38، §42، §43، §46، §47)
**قراردادهای قبلی:** [N](Phase13-N.md) (مصرف، هزینه، تأخیر)، [O](Phase13-O.md) (حسابرسی)،
[P](Phase13-P.md) (صف)، [S](Phase13-S.md) (بازیابی)، [U](Phase13-U.md) (سنجش)،
[V](Phase13-V.md) (بازخورد)
**گزارش اجرا:** [`Phase13-W-ExecutionReport.md`](Phase13-W-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

§34 می‌گوید پلتفرم باید Metrics تولید کند و آن‌ها را به Monitoring Platform
وصل کند. همهٔ دادهٔ لازم از قبل ثبت می‌شود — N مصرف و تأخیر، P صف، S
بازیابی، U سنجش، V بازخورد. کاری که W می‌کند ساختن داده نیست، **معنا دادن
به داده** است.

سؤال معماری W:

> **چطور از «همه‌چیز ثبت می‌شود» به «وقتی چیزی خراب شد، می‌فهمیم» برسیم،
> بدون اینکه خودِ مانیتورینگ به منبع سروصدا و نشتی تبدیل شود؟**

پاسخ W سه بخش دارد:

1. **W هیچ اندازه‌گیری از خودش ندارد.** هر عدد از یک `MetricContributor`
   می‌آید. افزودن منبع تازه یعنی ثبت یک contributor دیگر، نه ویرایش
   collector.
2. **مانیتورینگ نباید دقیقاً وقتی خراب می‌شود که سیستم خراب است.**
   contributor که استثنا بدهد به‌عنوان «منبع ناموفق» ثبت می‌شود و بقیهٔ
   پنجره سالم تحویل می‌شود.
3. **برچسب‌ها allow-list هستند.** متریک از مرز Tenant خارج می‌شود؛ برچسب
   آزاد یعنی نشتی داده در انتظار وقوع (§47).

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. رجیستری بستهٔ متریک با نوع، واحد و توضیح — شامل هر ده متریک §34؛
2. `MetricSample` با برچسب‌های پاک‌سازی‌شده؛
3. ریاضی: میانگین، صدک نزدیک‌ترین‌رتبه، نسبت امن؛
4. خروجی متن Prometheus بدون هیچ وابستگی؛
5. دو موجودیت: Snapshot منجمد و Alert رویدادی با چرخهٔ حیات؛
6. `MetricCollector` با ادغام، رد تکراری و متریک‌های مشتق؛
7. `AlertEvaluator` با **حذف تکرار** و resolve خودکار؛
8. `HealthEvaluator` با پنج مؤلفه و حکم کلی؛
9. سرویس اپلیکیشن + چهار contributor واقعی روی N، P، U و V؛
10. دو جدول و مهاجرت `0010`؛
11. پیکربندی `AI_OBSERVABILITY_*`/`AI_ALERT_*` و handler صف روی kind تازهٔ
    `MONITORING`؛
12. سه سطح تست، شامل متریک‌های واقعی از U و V.

### 2.2 خارج از Scope

- **داشبورد و UI** — فاز ۱۸؛
- **ارسال هشدار به کانال (ایمیل، اسلک)** — فاز ۱۲ (Notification) از طریق
  رویداد؛ W فقط رویداد و رکورد می‌سازد؛
- **Trace توزیع‌شده (OpenTelemetry)** — ADR جدا لازم دارد (Open Question ۱)؛
- **Log aggregation** — زیرساخت عملیاتی، نه دامنهٔ AI؛
- **API عمومی `/metrics`** — زیر‌فاز Z.

---

## 3. جایگاه معماری

```text
Application (ObservabilityApplicationService، contributors، JobHandler)
   │  ├─ MetricContributor × N  → N، P، U، V (و هر منبع آینده)
   │  ├─ MetricSnapshotStore    → aiMetricSnapshots
   │  ├─ AlertEventStore        → aiAlertEvents
   │  └─ ObservabilityAuditLogger → Phase 13-O
   ↓
Domain (MetricCollector، AlertEvaluator، HealthEvaluator، SnapshotBuilder)
   ← خالص، بدون جنگو، بدون I/O
```

---

## 4. قرارداد رجیستری متریک

| متریک §34 | نوع | واحد |
|---|---|---|
| `aiRequestsTotal` | COUNTER | COUNT |
| `aiRequestsFailed` | COUNTER | COUNT |
| `aiTokensTotal` | COUNTER | TOKENS |
| `aiCostTotal` | COUNTER | CURRENCY |
| `aiLatencyAverage` | GAUGE | MILLISECONDS |
| `aiLatencyP95` | GAUGE | MILLISECONDS |
| `aiProviderFailures` | COUNTER | COUNT |
| `aiModelFailures` | COUNTER | COUNT |
| `aiFallbackCount` | COUNTER | COUNT |
| `aiFeedbackScore` | GAUGE | SCORE |

به‌علاوهٔ متریک‌های پلتفرمی که زیر‌فازهای بعد ممکن کردند: `aiQueueDepth`،
`aiJobsFailed`، `aiRetrievalDenied`، `aiEvaluationScore`،
`aiEvaluationFailures`، `aiErrorRatio`.

نام متریک خارج از رجیستری **رد** می‌شود؛ داشبورد نباید حدس بزند یک عدد
شمارنده است یا مقدار لحظه‌ای.

---

## 5. قرارداد برچسب (§47)

فقط این کلیدها مجازند: `tenant`، `provider`، `model`، `capability`،
`suite`، `kind`، `status`، `reason`. هر کلید دیگر حذف می‌شود، مقدارها به
۶۴ کاراکتر بریده و کاراکترهای ناامن جایگزین می‌شوند. متن آزاد (پرسش
کاربر، ایمیل، محتوای پاسخ) هرگز وارد متریک نمی‌شود.

---

## 6. قرارداد جمع‌آوری

- پنجرهٔ **نیم‌باز** `[start, end)`؛ جمع‌آوری بعد از رویدادها اجرا می‌شود؛
- سقف عرض پنجره پیکربندی‌شده است؛
- دو contributor که یک سری یکسان (نام + برچسب) منتشر کنند ⇒ خطا، چون
  شمارنده بی‌صدا دو برابر می‌شد؛
- متریک‌های مشتق (`aiErrorRatio`، `aiLatencyAverage`، `aiLatencyP95`) فقط
  وقتی محاسبه می‌شوند که خودشان گزارش نشده باشند؛
- Snapshot فقط سری‌های **بدون برچسب** را منجمد می‌کند: snapshot یک
  roll-up سطح Tenant است، نه پایگاه دادهٔ سری‌زمانی.

---

## 7. قرارداد هشدار

قواعد پیش‌فرض (آستانه‌ها پیکربندی‌پذیر):

| کد | متریک | شرط | شدت |
|---|---|---|---|
| `AI_ERROR_RATIO_HIGH` | `aiErrorRatio` | > 0.1 (حداقل ۱۰ نمونه) | CRITICAL |
| `AI_LATENCY_P95_HIGH` | `aiLatencyP95` | > 15000ms | WARNING |
| `AI_QUEUE_BACKLOG` | `aiQueueDepth` | > 100 | WARNING |
| `AI_FEEDBACK_LOW` | `aiFeedbackScore` | < 0.5 | WARNING |
| `AI_EVALUATION_LOW` | `aiEvaluationScore` | < 0.6 | CRITICAL |

`minimumSamples` عمدی است: نسبت خطای ۱۰۰٪ روی یک درخواست، هشدار نیست.

---

## 8. قرارداد چرخهٔ هشدار

Alert **رویداد** است، نه پرچم: `FIRING → ACKNOWLEDGED → RESOLVED`.

- نقض پایدار **هشدار دوم نمی‌سازد** (بدون این، یک قطعی به‌ازای هر tick
  یک هشدار می‌داد)؛
- بازگشت متریک به محدوده، هشدار باز را resolve می‌کند؛
- نقض دوباره پس از resolve، رویداد تازه‌ای می‌سازد — پس «چند بار خراب
  شد؟» قابل پاسخ است.

---

## 9. قرارداد سلامت

پنج مؤلفه: PROVIDER، QUEUE، RETRIEVAL، EVALUATION، FEEDBACK. حکم کلی
**بدترین مؤلفه** است، و یک هشدار CRITICAL فعال به‌تنهایی پلتفرم را
UNHEALTHY می‌کند. نبود داده `UNKNOWN` است، نه HEALTHY — سکوت سلامت نیست.

---

## 10. قرارداد پیکربندی (§42)

`aiObservabilityEnabled`, `aiObservabilityWindowMinutes`,
`aiObservabilityMaxWindowHours`, `aiObservabilitySnapshotRetentionDays`,
`aiObservabilityAlertRetentionDays`, `aiAlertingEnabled`,
`aiAlertErrorRatio`, `aiAlertLatencyP95Ms`, `aiAlertQueueDepth`,
`aiAlertFeedbackScore`, `aiAlertEvaluationScore`.

---

## 11. قرارداد نگه‌داری (§46)

Snapshotها بر اساس پایان پنجره حذف می‌شوند؛ هشدارها **فقط وقتی
RESOLVED باشند**. قطعی‌ای که هنوز جریان دارد هرگز از کنسول غیب نمی‌شود.

---

## 12. اصلاحیهٔ واژگان صف

kind تازهٔ `MONITORING` (۱۰ → ۱۱). یادداشت ثبت‌شده: زیر‌فاز T از
`GENERIC` استفاده می‌کند و چون هر ورکر فقط یک handler به‌ازای kind
می‌پذیرد، بهتر است T هم در آینده kind اختصاصی بگیرد — خارج از Scope W.

---

## 13. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIMetricInvalid` | `AI_METRIC_INVALID` | 422 |
| `AIAlertRuleInvalid` | `AI_ALERT_RULE_INVALID` | 422 |
| `AIAlertNotFound` | `AI_ALERT_NOT_FOUND` | 404 |
| `AIObservabilityWindowInvalid` | `AI_OBSERVABILITY_WINDOW_INVALID` | 422 |

---

## 14. تصمیم‌های ثبت‌شده

- **W-D1 — بدون کتابخانهٔ Prometheus.** فرمت exposition یک قرارداد متنی
  کوچک و پایدار است؛ افزودن وابستگی برای چند خط قالب‌بندی، قاعدهٔ
  «بدون وابستگی جدید» را می‌شکست.
- **W-D2 — صدک نزدیک‌ترین‌رتبه، نه درون‌یابی.** p95 گزارش‌شده همیشه
  مقداری است که واقعاً رخ داده، پس می‌توان رفت و همان درخواست را دید.
- **W-D3 — contributor خراب، پنجره را از بین نمی‌برد.**
- **W-D4 — سری تکراری خطاست، نه جمع.**
- **W-D5 — Alert رویداد است، نه پرچم** (بند §8).
- **W-D6 — نبود داده `UNKNOWN` است.**
- **W-D7 — برچسب‌ها allow-list هستند** (§47).
- **W-D8 — Snapshot فقط سری بدون برچسب را منجمد می‌کند** تا جدول به
  پایگاه سری‌زمانی تبدیل نشود.

---

## 15. Open Questions برای زیر‌فازهای بعدی

1. Trace توزیع‌شده و انتخاب استاندارد (OpenTelemetry؟) — نیازمند ADR؛
2. ارسال هشدار به کانال‌های فاز ۱۲ از طریق رویداد §36؛
3. قواعد هشدار به‌ازای Tenant (اکنون سراسری‌اند)؛
4. نگهداشت طولانی‌مدت با down-sampling؛
5. انتقال handler نگه‌داری T از `GENERIC` به kind اختصاصی.

---

## 16. Acceptance Criteria

- [x] هر ده متریک §34 در رجیستری با نوع و واحد؛
- [x] برچسب‌های allow-list با برش و پاک‌سازی؛
- [x] ریاضی صدک/میانگین/نسبت با تست مرزی؛
- [x] خروجی Prometheus با HELP/TYPE و ترتیب قطعی؛
- [x] دو موجودیت با Invariant و چرخهٔ حیات کامل؛
- [x] ادغام contributorها و رد سری تکراری؛
- [x] متریک‌های مشتق فقط در نبودشان؛
- [x] contributor خراب ⇒ پنجرهٔ تخریب‌شده، نه از دست رفته؛
- [x] هشدار با حذف تکرار، resolve و رویداد تازه پس از بازگشت نقض؛
- [x] `minimumSamples` برای قواعد پرنویز؛
- [x] acknowledge و ماندن در حالت فعال تا resolve؛
- [x] سلامت پنج‌مؤلفه‌ای با «بدترین مؤلفه» و UNKNOWN؛
- [x] چهار contributor واقعی روی N/P/U/V؛
- [x] ایزولاسیون Tenant در Snapshot، Alert و exposition؛
- [x] سوئیچ fail-closed؛
- [x] سه action حسابرسی و زنجیرهٔ سالم؛
- [x] نگه‌داری: Snapshot بر اساس پنجره، Alert فقط RESOLVED؛
- [x] دو جدول + مهاجرت `0010_observabilityPlatform` بدون drift؛
- [x] handler صف روی kind تازهٔ `MONITORING`؛
- [x] ۱۲۴ تست جدید سبز؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های W تمیز؛
- [x] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `GREEN — Phase 13-X may begin.`
