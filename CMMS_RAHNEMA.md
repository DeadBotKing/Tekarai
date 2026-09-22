# سیستم نگهداری و تعمیرات دستگاه‌ها (CMMS) — راهنمای فارسی

این قابلیت یک سامانه‌ی کامل «نگهداری و تعمیرات» (CMMS) است که به معماری DDD بقیه‌ی
پروژه اضافه شده: بک‌اند واقعی + رابط فارسی + تست کامل. هر کاربر می‌تواند درخواست کار
ثبت کند، کارها پیگیری می‌شوند و نگهداری پیشگیرانه‌ی دوره‌ای (PM) دستگاه‌ها پوشش دارد.

## چه چیزی ساخته شد

### دو Aggregate اصلی
- **Device (دستگاه):** کد یکتا در هر Tenant، نام، محل، وضعیت، بازه‌ی PM (روز)، تاریخ آخرین
  PM. تاریخ PM بعدی و «سررسید بودن» به‌صورت مشتق محاسبه می‌شود.
- **WorkOrder (درخواست کار):** عنوان، شرح، نوع (اصلاحی/پیشگیرانه/بازرسی)، اولویت، وضعیت،
  درخواست‌دهنده، تکنسین، یادداشت رفع عیب.

### چرخه‌ی حیات درخواست کار (State Machine)
```
ثبت‌شده → ارجاع‌شده → در حال انجام → تکمیل‌شده
(هر مرحله می‌تواند لغو یا معلق شود؛ تکمیل/لغو حالت پایانی است.)
```
گذارهای نامعتبر (مثلاً «ثبت‌شده → تکمیل‌شده») توسط دامنه رد می‌شوند (خطای ۴۰۹).

### سه نقش (طبق درخواست)
| نقش | کد | دسترسی |
|-----|-----|--------|
| درخواست‌دهنده | `maintenanceRequester` | دیدن دستگاه‌ها، ثبت و دیدن درخواست کار |
| تکنسین | `maintenanceTechnician` | + مدیریت دستگاه/PM، به‌روزرسانی درخواست کار |
| مدیر | `maintenanceManager` | + ارجاع درخواست کار به تکنسین |

این سه نقش هنگام `bootstrapPlatform` به‌صورت خودکار seed می‌شوند. علاوه بر این،
دسترسی‌های maintenance به نقش‌های موجود (`platformAdmin`، `tenantAdmin`، `member`) هم
اضافه شده تا ورود پیش‌فرض بلافاصله کار کند.

## آدرس‌های API (زیر `/api/v1/maintenance/`)
- `GET/POST devices` — فهرست/ثبت دستگاه
- `GET/PATCH devices/{id}` — جزئیات/ویرایش
- `POST devices/{id}/status` — تغییر وضعیت
- `POST devices/{id}/pm` — ثبت نگهداری پیشگیرانه
- `GET devices/due-pm` — دستگاه‌های سررسیدشده‌ی PM
- `GET/POST work-orders` — فهرست/ثبت درخواست کار
- `GET/PATCH work-orders/{id}` — جزئیات/ویرایش
- `POST work-orders/{id}/assign` — ارجاع به تکنسین
- `POST work-orders/{id}/status` — تغییر وضعیت

## رابط کاربری (فقط فارسی و RTL)
دو صفحه‌ی جدید در منوی «نگهداری و تعمیرات»:
- **دستگاه‌ها و PM** (`/app/maintenance/devices`) — جدول دستگاه‌ها، کارت‌های آماری،
  ثبت/ویرایش دستگاه، تغییر وضعیت، ثبت PM و برجسته‌سازی PMهای سررسیدشده.
- **درخواست‌های کار** (`/app/maintenance/work-orders`) — نمای فهرست و برد (Kanban)،
  ثبت درخواست، ارجاع به تکنسین و پیشبرد وضعیت طبق state machine.

## اجرای محلی (ویندوز / PowerShell)
```powershell
cd C:\Users\Mitra\Desktop\Tekarai
powershell.exe -ExecutionPolicy Bypass -File .\run_dev.ps1
```
سپس مرورگر: <http://localhost:4173>
ورود: tenant=`platform`, user=`platform-admin`, pass=`Tekarai-Demo-2026!`

> اسکریپت `run_dev.ps1` به‌طور خودکار migration اپ maintenance را اجرا می‌کند و
> `seedWorkspace` چند دستگاه و درخواست کار نمونه‌ی فارسی برای هر دو Tenant می‌سازد
> (idempotent — اجرای دوباره داده‌ی تکراری نمی‌سازد).

## تست‌ها
- **بک‌اند:** ۲۳۰۲ تست سبز (۱۴ تست جدید maintenance + تست‌های معماری/نام‌گذاری/seed).
  ```
  cd backend
  .venv\Scripts\python manage.py test tests --settings=config.settings.testing
  ```
- **فرانت:** `npm run typecheck` + `npm run test` (۱۵ سبز) + `npm run build` — همه سبز.

## چیدمان فایل‌ها (بک‌اند)
```
backend/apps/maintenance/
  domain/           valueObjects, entities (Device, WorkOrder), repositories (Protocol)
  application/      commands, queries, dto, services, useCases (Device + WorkOrder)
  infrastructure/   models, repositories (Django), container, migrations
  presentation/     serializers, views (Device + WorkOrder), urls, openapi
```

## نکته درباره‌ی گیت
این تغییرات در کلون ورک‌اسپیس اعمال شده و روی ریپوی گیت‌هاب شما push نشده است.
برای انتقال، همین پوشه‌ها/فایل‌ها را در نسخه‌ی محلی خود کپی یا خودتان commit/push کنید.
