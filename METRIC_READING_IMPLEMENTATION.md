# تحویل کامل MetricReading

## خلاصه

قابلیت `MetricReading` به‌صورت یک Vertical Slice کامل در bounded context جدید
`analytics` پیاده‌سازی شده است. این پیاده‌سازی فقط یک جدول ساده نیست و همهٔ
لایه‌های Domain، Application، Infrastructure و Presentation را پوشش می‌دهد.

## مدل دامنه

### MetricDefinition

هر Reading باید به یک تعریف معتبر و متعلق به همان Tenant وصل باشد:

- `code`: شناسهٔ یکتای Tenant-scoped با طول حداکثر ۶۴ نویسه
- `name`, `description`, `formula`, `unit`
- `aggregation`: یکی از `LAST | SUM | AVERAGE | MIN | MAX | COUNT`
- `minimumValue` و `maximumValue`: محدودهٔ اختیاری قابل‌قبول
- `isActive`: غیرفعال‌کردن تعریف بدون حذف تاریخچه

### MetricReading

هر رکورد شامل موارد زیر است:

- شناسهٔ UUID و `tenantId`
- FK محافظت‌شده به `MetricDefinition`
- مقدار دقیق `decimal(18,6)`؛ NaN و Infinity یا گردکردن پنهان مجاز نیست
- بازهٔ UTC با `periodStart` و `periodEnd`
- `dimensions`: شیء JSON تخت، مرتب و محدودشده
- کیفیت: `GOOD | SUSPECT | BAD | UNKNOWN`
- منبع اختیاری به‌شکل جفت `sourceType` و `sourceId`
- `ingestionKey` برای idempotency پایدار در دیتابیس
- `recordedAt`, `recordedById`, `correlationId`

## قواعد یکپارچگی و امنیت

1. Reading کاملاً append-only است:
   - Domain entity و map داخلی dimensions غیرقابل‌تغییرند.
   - `save()` مجدد و `delete()` روی ORM رد می‌شوند.
   - `QuerySet.update()` و `QuerySet.delete()` نیز مسدود هستند.
   - API هیچ مسیر PATCH/DELETE برای Reading ندارد.
2. همهٔ Queryها Tenant-scoped هستند و رکورد Tenant دیگر با 404 پنهان می‌شود.
3. MetricDefinition باید متعلق به همان Tenant باشد و حذف نشده باشد.
4. Definition غیرفعال Reading جدید قبول نمی‌کند.
5. حداقل/حداکثر تعریف روی هر Reading اعمال می‌شود.
6. `periodEnd >= periodStart` و زمان بیش از پنج دقیقه در آینده رد می‌شود.
7. Dimensions:
   - حداکثر ۳۲ کلید و ۴۰۹۶ بایت UTF-8
   - فقط مقدار scalar
   - کلیدهای حساس مانند password/token/secret/credential رد می‌شوند.
8. `ingestionKey` در محدودهٔ Tenant یکتا است:
   - ارسال مجدد payload یکسان همان رکورد را با `replayed=true` برمی‌گرداند.
   - استفادهٔ مجدد از کلید برای payload متفاوت با
     `ANALYTICS_INGESTION_CONFLICT` و HTTP 409 رد می‌شود.
9. Batch حداکثر ۵۰۰ آیتم و all-or-nothing است.
10. مقادیر Decimal در API به‌شکل string برمی‌گردند تا precision در JavaScript
    از بین نرود.

## مجوزها

- `analytics.metricDefinition.view`
- `analytics.metricDefinition.manage`
- `analytics.metricReading.view`
- `analytics.metricReading.record`

مجوزها به Permission Catalog و presetهای Platform Admin، Tenant Admin، Member و
نقش‌های نگهداری افزوده شده‌اند. احراز هویت و authorization هم در API و هم در
Use Case بررسی می‌شوند.

## API

تمام مسیرها زیر `/api/v1/analytics/` هستند:

| Method | Path | کاربرد |
|---|---|---|
| GET | `metric-definitions` | فهرست و جست‌وجوی تعریف‌ها |
| POST | `metric-definitions` | ساخت تعریف |
| GET | `metric-definitions/{id}` | جزئیات تعریف |
| PATCH | `metric-definitions/{id}` | ویرایش/فعال‌سازی/غیرفعال‌سازی |
| GET | `metric-readings` | فهرست، فیلتر، sort و pagination |
| POST | `metric-readings` | ثبت یک Reading |
| POST | `metric-readings/batch` | ثبت اتمیک تا ۵۰۰ Reading |
| GET | `metric-readings/summary` | count/min/max/avg/sum/first/last |
| GET | `metric-readings/{id}` | جزئیات Reading |

### نمونهٔ ساخت Definition

```http
POST /api/v1/analytics/metric-definitions
Authorization: Bearer <token>
Idempotency-Key: metric-definition-device-temperature-v1
Content-Type: application/json

{
  "code": "DEVICE.TEMPERATURE",
  "name": "دمای تجهیز",
  "unit": "°C",
  "aggregation": "AVERAGE",
  "minimumValue": "-50",
  "maximumValue": "250"
}
```

### نمونهٔ ثبت Reading لحظه‌ای

`occurredAt` میان‌بری برای حالتی است که `periodStart == periodEnd` باشد:

```http
POST /api/v1/analytics/metric-readings
Authorization: Bearer <token>
Content-Type: application/json

{
  "metricCode": "DEVICE.TEMPERATURE",
  "value": "72.125",
  "occurredAt": "2026-09-29T11:30:00Z",
  "dimensions": {
    "deviceId": "PUMP-01",
    "location": "LINE-A"
  },
  "quality": "GOOD",
  "sourceType": "device",
  "sourceId": "PUMP-01",
  "ingestionKey": "gateway-1:sequence-100"
}
```

به‌جای `metricCode` می‌توان دقیقاً یکی از `metricId` یا `metricCode` را فرستاد.
برای بازه نیز می‌توان `periodStart` و `periodEnd` را صریح ارسال کرد.

### فیلتر فهرست

```text
GET /api/v1/analytics/metric-readings
  ?metricCode=DEVICE.TEMPERATURE
  &quality=GOOD
  &sourceType=device
  &sourceId=PUMP-01
  &from=2026-09-01T00:00:00Z
  &to=2026-09-30T23:59:59Z
  &ordering=-periodStart
  &page=1
  &pageSize=100
```

بازه با semantics هم‌پوشانی اعمال می‌شود؛ Readingی که بخشی از بازه‌اش داخل
پنجره باشد حذف نمی‌شود.

### Batch

```json
{
  "readings": [
    {
      "metricCode": "DEVICE.TEMPERATURE",
      "value": "71.50",
      "occurredAt": "2026-09-29T11:30:00Z",
      "ingestionKey": "gateway-1:101"
    },
    {
      "metricCode": "DEVICE.TEMPERATURE",
      "value": "72.00",
      "occurredAt": "2026-09-29T11:31:00Z",
      "ingestionKey": "gateway-1:102"
    }
  ]
}
```

اگر حتی یک آیتم نامعتبر باشد هیچ‌یک از آیتم‌های batch ذخیره نمی‌شود.

### Summary

Summary حتماً باید دقیقاً یک `metricId` یا `metricCode` داشته باشد تا واحدهای
متفاوت با هم جمع نشوند:

```text
GET /api/v1/analytics/metric-readings/summary?metricCode=DEVICE.TEMPERATURE
```

خروجی شامل `count`, `minimum`, `maximum`, `average`, `total`, `first`, `last`
است.

## دیتابیس و کارایی

Migration: `backend/apps/analytics/infrastructure/migrations/0001_initial.py`

ایندکس‌ها:

- `(tenantId, metricId, periodStart)` برای سری زمانی Metric
- `(tenantId, sourceType, sourceId, periodStart)` برای نمودار منبع/تجهیز
- `(tenantId, recordedAt)` برای عملیات ingestion
- unique filtered index روی `(tenantId, ingestionKey)`
- unique filtered index روی `(tenantId, code)` برای Definition فعال/حذف‌نشده

Constraintهای دیتابیس کیفیت، ترتیب بازه، range تعریف و یکتایی‌ها را نیز مستقل
از API تضمین می‌کنند. FK با `PROTECT` مانع orphan شدن Readingها است.

## Frontend client

فایل `frontend-web/src/features/analytics/metricReadingService.ts` شامل typeها و
کلاینت کامل Definition، single/batch ingestion، query و summary است. همهٔ URLها
نیز در `core/api/endpoints.ts` متمرکز شده‌اند.

## تست و کیفیت

پوشش جدید:

- ۸ تست Unit دامنه
- ۹ تست Integration API/DB
- احراز هویت، Tenant isolation، bounds، inactive definition
- idempotency/replay/conflict
- batch transaction rollback
- summary و pagination/filtering
- append-only بودن در API، Model و QuerySet

فرمان‌های اصلی:

```bash
cd backend
.venv/bin/python manage.py test \
  tests.unit.testMetricReading \
  tests.integration.testMetricReadingApi \
  --settings=config.settings.testing
.venv/bin/python manage.py check --settings=config.settings.testing
.venv/bin/python manage.py makemigrations analytics --check \
  --settings=config.settings.testing
.venv/bin/ruff check apps/analytics
.venv/bin/mypy apps/analytics

cd ../frontend-web
npm run typecheck
npm run test -- --run
npm run build
```
