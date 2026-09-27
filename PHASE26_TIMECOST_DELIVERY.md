# فاز ۲۶ — ثبت زمان و هزینه (Time & Cost Tracking)

**ساعت‌کارِ تکنسین + هزینه‌ی قطعات روی هر درخواست** — برای گزارش هزینه‌ی
نگهداری. کاملاً هم‌راستا با معماری DDD موجود (مانند فازهای ۲۱ تا ۲۵).

## قابلیت‌های تحویل‌شده

1. **ثبت ساعت‌کار تکنسین روی هر درخواست** — هر ثبت شامل نام تکنسین، تعداد
   ساعت (تا ۲ رقم اعشار)، نرخ ساعتی، تاریخ انجام و یادداشت. نرخ ساعتی لحظه‌ی
   ثبت ذخیره می‌شود تا تغییر بعدی نرخ، هزینه‌ی تاریخی را بازنویسی نکند.
2. **هزینه‌ی قطعات روی هر درخواست** — هر قطعه‌ی یدکی فیلد **قیمت واحد**
   (`unitCost`) گرفت؛ هنگام مصرف قطعه روی درخواست، قیمت همان لحظه روی سطر
   مصرف **snapshot** می‌شود. بنابراین افزایش قیمت فردا، هزینه‌ی دیروز را عوض نمی‌کند.
3. **Roll-up خودکار روی درخواست** — با هر ثبت/حذف ساعت‌کار یا مصرف قطعه،
   ستون‌های `labourHours` / `labourCost` / `partsCost` درخواست‌کار در همان
   تراکنش به‌روز می‌شوند (خواندن گزارش = خواندن یک ردیف، سند = سطرهای جزئیات).
4. **خلاصه‌ی هزینه‌ی هر درخواست** — ساعت‌کار کل، هزینه‌ی نیروی انسانی، هزینه‌ی
   قطعات و هزینه‌ی کل + سطرهای شواهد (لیست ثبت‌های ساعت و مصرف قطعات).
5. **گزارش هزینه‌ی نگهداری** — مجموع کل سازمان با سه تفکیک: **به تفکیک
   دستگاه**، **به تفکیک واحد** و **ساعت‌کار به تفکیک تکنسین** + جدول
   درخواست‌ها (گران‌ترین اول). خروجی **JSON / CSV / XLSX** فارسی مثل فاز ۲۳.

## Endpointهای جدید

| متد | مسیر | توضیح | دسترسی |
|-----|------|-------|--------|
| POST | `/api/v1/maintenance/work-orders/{id}/labour` | ثبت ساعت‌کار تکنسین | `maintenance.workorder.logTime` |
| GET | `/api/v1/maintenance/work-orders/{id}/labour` | لیست ثبت‌ها + مجموع ساعت/هزینه | `maintenance.workorder.view` |
| DELETE | `/api/v1/maintenance/labour-entries/{entryId}` | حذف ثبت اشتباه (Roll-up اصلاح می‌شود) | `maintenance.workorder.logTime` |
| GET | `/api/v1/maintenance/work-orders/{id}/cost-summary` | خلاصه‌ی هزینه‌ی یک درخواست | `maintenance.costs.view` |
| GET | `/api/v1/maintenance/reports/maintenance-costs` | گزارش هزینه‌ی نگهداری (JSON) | `maintenance.costs.view` |
| GET | `.../maintenance-costs?export=csv` / `?export=xlsx` | دانلود فارسی | `maintenance.costs.view` |
| GET | `.../maintenance-costs?fromDate=&toDate=&deviceId=&department=` | فیلتر بازه/دستگاه/واحد | `maintenance.costs.view` |

به‌علاوه `POST /api/v1/maintenance/spare-parts` و `PATCH .../spare-parts/{id}`
فیلد اختیاری `unitCost` گرفتند (پیش‌فرض `0` — سازگار با کلاینت‌های قبلی).

### مثال

```jsonc
// POST /work-orders/{id}/labour
{ "technicianName": "حسین کریمی", "hours": "3.5", "hourlyRate": "480000", "note": "تعویض یاتاقان" }
// 201 → { "hours": "3.50", "hourlyRate": "480000.00", "totalCost": "1680000.00", ... }

// GET /work-orders/{id}/cost-summary
{ "labourHours": "5.00", "labourCost": "2355000.00",
  "partsCost": "1700000.00", "totalCost": "4055000.00",
  "labourEntries": [...], "partUsages": [...] }
```

## معماری (لایه‌های DDD)

- **Domain** — موجودیت جدید `LabourEntry` (با `totalCost = hours × rate`)؛
  `SparePart.unitCost` و `WorkOrderPartUsage.unitCost/totalCost`؛ سرویس خالص
  `maintenanceCosting.py` (تجمیع کل/گروه‌بندی — بدون Django، تست‌پذیر)؛
  قراردادهای `LabourEntryRepository` و `MaintenanceCostRepository`.
- **Application** — یوزکیس‌های `LogLabourEntry` / `ListLabourEntries` /
  `DeleteLabourEntry` / `GetWorkOrderCostSummary` / `GetMaintenanceCostReport`
  در `timeCostUseCases.py` + کامندها در `timeCostCommands.py`.
- **Infrastructure** — مدل `WorkOrderLabourEntryModel` + فیلدهای `unitCost`؛
  migration `0009_time_cost_tracking`؛ repositoryهای
  `labourEntryRepositoryImpl` (Roll-up تراکنشی) و `costReportRepositoryImpl`؛
  Roll-up `partsCost` در `sparePartRepositoryImpl`.
- **Presentation** — `timeCostViews.py`، سریالایزرها، exporter فارسی
  `costReportExporters.py` (CSV با BOM + XLSX راست‌به‌چپ)، ثبت مسیرها و OpenAPI.

## دسترسی‌ها

دو عملیات جدید به کاتالوگ اضافه شد (به‌صورت خودکار در پرست‌های نقش
**تکنسین** و **مدیر نگهداری** آمده‌اند):

- `maintenance.workorder.logTime` — ثبت و حذف ساعت‌کار تکنسین
- `maintenance.costs.view` — مشاهده‌ی خلاصه‌ی هزینه و گزارش هزینه‌ی نگهداری

## قواعد و طراحی

- ساعت > ۰ و نرخ ≥ ۰ با حداکثر ۲ رقم اعشار (هم validation هم CheckConstraint دیتابیس).
- Roll-upها **از سطرها مشتق** می‌شوند، نه شمارنده‌ی دستی — حذف یک ثبت دقیقاً
  سهم همان ثبت را کم می‌کند (فلسفه‌ی `maintenanceAnalytics` فاز ۲۶).
- مسیر قبلی «جزئیات بستن درخواست» (closure) همچنان می‌تواند این سه ستون را برای
  درخواست‌های **بدون** سطر ثبت‌شده دستی بنویسد — آخرین نگارش همان می‌ماند.
- گزارش بر مبنای **تاریخ ثبت درخواست** فیلتر می‌شود (هم‌راستا با گزارش فاز ۲۳).

## تست‌ها — همه سبز

- **بک‌اند: ۲۴۰۲ تست OK** (+۹ تست جدید در `tests/integration/testPhase26TimeCostApi.py`):
  احراز هویت، ثبت/لیست/حذف ساعت‌کار با بررسی Roll-up، اعتبارسنجی ساعت/نام/درخواست
  ناموجود، snapshot قیمت بعد از تغییر قیمت قطعه، خلاصه‌ی هزینه‌ی ترکیبی،
  تفکیک‌ها و فیلتر دستگاه در گزارش، خروجی CSV (BOM) و XLSX (workbook معتبر).
- **گیت‌های کیفیت:** `manage.py check` سبز، `makemigrations --check` بدون تغییر
  (migration دست‌ساز دقیقاً با مدل‌ها یکی است)، ruff سبز روی فایل‌های جدید،
  mypy: **صفر خطای جدید** نسبت به baseline (۳ خطای قدیمی هم رفع شد).

## اجرای محلی (ویندوز / PowerShell)

```powershell
cd C:\\Users\\Mitra\\Desktop\\Tekarai
powershell.exe -ExecutionPolicy Bypass -File .\\run_dev.ps1 -UseSqlite
```

`migrate` به‌صورت خودکار جدول `WorkOrderLabourEntry` و ستون‌های `unitCost` را
می‌سازد؛ نیازی به داده‌ی اولیه نیست.
