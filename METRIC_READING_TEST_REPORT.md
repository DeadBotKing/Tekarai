# MetricReading — Test Report

تاریخ اجرا: 2026-09-29

## نتایج موفق

| بخش | فرمان/دامنه | نتیجه |
|---|---|---|
| Unit + Integration جدید بک‌اند | `tests.unit.testMetricReading` + `tests.integration.testMetricReadingApi` | **17/17 PASS** |
| Django system check | `manage.py check --settings=config.settings.testing` | **PASS** |
| Migration drift قابلیت جدید | `makemigrations analytics --check` | **PASS — No changes detected** |
| Ruff قابلیت جدید | `ruff check apps/analytics ...` | **PASS** |
| Ruff format قابلیت جدید | `ruff format --check apps/analytics ...` | **PASS** |
| Mypy قابلیت جدید | `mypy apps/analytics` | **PASS — 38 source files** |
| Opening-register architecture tests | `testNoBusinessDomains` + `testPhase3DomainArchitecture` | **20/20 PASS** |
| TypeScript | `npm run typecheck` | **PASS** |
| Frontend tests کامل | `npm run test -- --run` | **104/104 PASS (20 files)** |
| Frontend production build | `npm run build` | **PASS** |

## سناریوهای تست‌شدهٔ MetricReading

- ساخت، مشاهده و به‌روزرسانی MetricDefinition
- ثبت Reading با `metricCode` و بازیابی جزئیات
- Decimal precision و کیفیت داده
- فیلتر، pagination و Tenant scoping
- احراز هویت اجباری
- پنهان‌سازی Reading متعلق به Tenant دیگر با 404
- حداقل/حداکثر MetricDefinition و Definition غیرفعال
- idempotency پایدار، replay و conflict برای payload متفاوت
- Batch اتمیک و rollback کامل در صورت یک آیتم نامعتبر
- Summary شامل count/min/max/average/sum/first/last
- append-only بودن در سطح Domain، Model، QuerySet و REST
- جلوگیری از dimensions تو‌در‌تو/بزرگ/حساس
- رویداد `metricReadingRecorded`
- کلاینت TypeScript برای single، batch، list و summary

## وضعیت suite معماری قدیمی مخزن

کل suite معماری ۱۶۴ تست دارد. پس از ثبت رسمی context جدید Analytics در opening
register، **۱۵۹ تست پاس** و ۵ تست قدیمی نامرتبط با MetricReading همچنان fail
هستند. این موارد از قبل در کد تحویلی مخزن وجود داشتند:

1. دسترسی مستقیم Procurement Presentation به Maintenance Infrastructure؛
2. نبود پوشهٔ `domain/` در context قدیمی Procurement؛
3. نام فایل‌های تست قدیمی Maintenance با snake_case؛
4. کلاس قدیمی `_DocumentUseCaseBase` با نام ناسازگار؛
5. hook قدیمی DRF با نام `validate_quantity`.

هیچ‌یک از این پنج مورد در فایل‌های Analytics یا جریان MetricReading نیست. برای
جلوگیری از تغییر دامنه‌های نامرتبط، در این تحویل دست‌کاری نشده‌اند.
