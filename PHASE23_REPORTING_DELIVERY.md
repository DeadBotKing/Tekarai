# فاز ۲۳ — گزارش‌گیری و خروجی (Reporting & Export)

گزارش تاریخچه‌ی نگهداری هر دستگاه، همراه با خلاصه‌ی آماری و خروجی
**Excel (.xlsx) / CSV / چاپ (PDF مرورگر)** — کاملاً فارسی و هم‌راستا با معماری DDD.

## قابلیت‌های تحویل‌شده

1. **گزارش تاریخچه‌ی نگهداری دستگاه** — یک صفحه‌ی اختصاصی برای هر دستگاه شامل:
   - کارت مشخصات دستگاه (کد، نام، محل، واحد، وضعیت، PM بعدی)
   - **خلاصه‌ی آماری**: کل درخواست‌ها، باز، تکمیل‌شده، دارای تأخیر، MTTR
     (میانگین زمان تعمیر بر حسب ساعت)، و نمودار **نرخ تکمیل**
   - جدول کامل همه‌ی درخواست‌های کار دستگاه (عنوان/نوع/اولویت/وضعیت/تکنسین/تاریخ/تأخیر)
2. **فیلتر بازه‌ی زمانی** — فیلتر «از تاریخ / تا تاریخ» روی تاریخ ثبت درخواست‌ها.
3. **خروجی Excel (.xlsx)** — فایل واقعی اکسل با openpyxl: راست‌به‌چپ، هدرهای
   فارسی استایل‌دار، بلوک مشخصات + خلاصه + جدول درخواست‌ها، عرض ستون‌های تنظیم‌شده.
4. **خروجی CSV** — UTF-8 با BOM (تا اکسل فارسی را درست باز کند)، هدرها و برچسب‌های فارسی.
5. **چاپ / PDF** — دکمه‌ی چاپ مرورگر با چیدمان چاپ اختصاصی (سربرگ گزارش، مخفی‌شدن
   نوار ابزار/سایدبار، جدول تمیز). کاربر «چاپ → ذخیره به‌صورت PDF» می‌زند —
   فارسی بی‌نقص و بدون هیچ وابستگی جدید سمت سرور.

## نقطه‌ی ورود در UI
صفحه‌ی **دستگاه‌ها** → هر ردیف → دکمه‌ی **«گزارش»** → مسیر
`/app/maintenance/devices/{id}/report`.

## Endpoint جدید بک‌اند

| متد | مسیر | توضیح |
|-----|------|-------|
| GET | `/api/v1/maintenance/devices/{id}/report` | JSON گزارش (پیش‌فرض) |
| GET | `.../report?export=csv` | دانلود CSV فارسی |
| GET | `.../report?export=xlsx` | دانلود Excel فارسی |
| GET | `.../report?fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD` | فیلتر بازه |

> دسترسی لازم: `maintenance.workorder.view`.
> **نکته‌ی فنی:** پارامتر انتخاب فرمت عمداً `export` نام‌گذاری شد (نه `format`)
> چون DRF نام `format` را برای content-negotiation رزرو کرده و باعث ۴۰۴ می‌شد.

## معماری (لایه‌های DDD)
- **Query:** `DeviceMaintenanceReportQuery` (deviceId + fromDate/toDate)
- **DTO:** `DeviceMaintenanceReportDto` + `DeviceReportSummaryDto`
- **UseCase:** `DeviceMaintenanceReportUseCase` (جمع‌آوری همه‌ی WOها با صفحه‌بندی
  داخلی + محاسبه‌ی خلاصه/MTTR) — دسترسی `maintenance.workorder.view`
- **Filter:** `WorkOrderFilters` فیلدهای `createdFrom/createdTo` گرفت
- **Exporters:** `reportExporters.py` (CSV + XLSX) و `reportLabels.py` (برچسب‌های فارسی)
- **View/Route:** `DeviceMaintenanceReportView` + مسیر `devices/{id}/report`

## وابستگی جدید
- `openpyxl==3.1.5` به `requirements/base.txt` اضافه شد (تولید فایل واقعی .xlsx).

## تست‌ها — همه سبز
- **بک‌اند: ۲۳۲۵ تست OK** (+۸ تست جدید در `testPhase23MaintenanceReport.py`):
  احراز هویت، ساختار JSON + خلاصه، دستگاه خالی، فیلتر بازه، ۴۰۴ دستگاه ناموجود،
  CSV (BOM + هدر فارسی)، XLSX (workbook معتبر + RTL + محتوای فارسی)، رد فرمت نامعتبر.
- **فرانت‌اند:** `typecheck` سبز، `npm run test` (۱۵ تست) سبز، `npm run build` موفق.

## اجرای محلی (ویندوز / PowerShell)
```powershell
cd C:\Users\Mitra\Desktop\Tekarai
powershell.exe -ExecutionPolicy Bypass -File .\run_dev.ps1 -UseSqlite
```
سپس در مرورگر: صفحه‌ی دستگاه‌ها → دکمه‌ی «گزارش» روی هر دستگاه.
