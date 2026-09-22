# سیستم نگهداری و تعمیرات دستگاه‌ها (CMMS) — راهنمای فارسی

این قابلیت یک سامانه‌ی کامل «نگهداری و تعمیرات» (CMMS) است که به معماری DDD بقیه‌ی
پروژه اضافه شده: بک‌اند واقعی + رابط فارسی + تست کامل. هر کاربر می‌تواند درخواست کار
ثبت کند، کارها پیگیری می‌شوند و نگهداری پیشگیرانه‌ی دوره‌ای (PM) دستگاه‌ها پوشش دارد.

## چه چیزی ساخته شد

### دو Aggregate اصلی
- **Device (دستگاه):** کد یکتا در هر Tenant، نام، محل، وضعیت، **واحد مسئول (Department)**،
  بازه‌ی PM (روز)، تاریخ آخرین PM. تاریخ PM بعدی و «سررسید بودن» به‌صورت مشتق محاسبه می‌شود.
- **WorkOrder (درخواست کار):** عنوان، شرح، نوع (اصلاحی/پیشگیرانه/بازرسی)، اولویت، وضعیت،
  **واحد (Department)**، درخواست‌دهنده، تکنسین، یادداشت رفع عیب.

### واحدها (Departments) — فهرست ثابت
پنج واحد تعریف‌شده‌اند: **عمومی** (`general`)، **برق** (`electrical`)، **مکانیک**
(`mechanical`)، **تأسیسات** (`facilities`)، **ابزار دقیق** (`instrumentation`).
هر دستگاه یک «واحد پیش‌فرض» دارد و درخواست کار جدید همان واحد دستگاه را به ارث می‌برد
(مگر اینکه هنگام ثبت واحد دیگری انتخاب شود).

### چرخه‌ی حیات درخواست کار (State Machine) — ارجاع دومرحله‌ای
```
ثبت‌شده → ارجاع به واحد (routed) → سپرده‌شده به تکنسین (assigned) → در حال انجام → تکمیل‌شده
```
- **مرحله ۱ (ارجاع به واحد):** مدیر درخواست را به واحد تخصصی مربوطه ارجاع می‌دهد؛ مثلاً
  «درخواست کار برق» را به **واحد برق**. (endpoint: `work-orders/{id}/route`)
- **مرحله ۲ (سپردن به تکنسین):** سرپرست همان واحد آن را به یک تکنسین می‌سپارد.
  (endpoint: `work-orders/{id}/assign`)
- می‌توان مستقیماً از «ثبت‌شده» به «سپرده‌شده» هم رفت (ارجاع به واحد اختیاری است).
- هر مرحله می‌تواند لغو یا معلق شود؛ تکمیل/لغو حالت پایانی است.
گذارهای نامعتبر (مثلاً «ثبت‌شده → تکمیل‌شده») توسط دامنه رد می‌شوند (خطای ۴۰۹).

### PM خودکار (ساخت خودکار درخواست پیشگیرانه)
با فراخوانی `POST work-orders/generate-pm` (دکمه‌ی «ساخت خودکار PM» در صفحه‌ی درخواست‌های
کار)، برای هر دستگاهی که موعد PM آن رسیده و درخواست پیشگیرانه‌ی بازِ دیگری ندارد، یک
درخواست کار از نوع **preventive** ساخته و به‌صورت خودکار به **واحد پیش‌فرض همان دستگاه**
ارجاع (routed) می‌شود. این عملیات idempotent است — اجرای دوباره درخواست تکراری نمی‌سازد.

### سه نقش (طبق درخواست)
| نقش | کد | دسترسی |
|-----|-----|--------|
| درخواست‌دهنده | `maintenanceRequester` | دیدن دستگاه‌ها، ثبت و دیدن درخواست کار |
| تکنسین | `maintenanceTechnician` | + مدیریت دستگاه/PM، به‌روزرسانی درخواست کار |
| مدیر | `maintenanceManager` | + ارجاع به واحد (route) و سپردن به تکنسین (assign) |

این سه نقش هنگام `bootstrapPlatform` به‌صورت خودکار seed می‌شوند. علاوه بر این،
دسترسی‌های maintenance به نقش‌های موجود (`platformAdmin`، `tenantAdmin`، `member`) هم
اضافه شده تا ورود پیش‌فرض بلافاصله کار کند.

## آدرس‌های API (زیر `/api/v1/maintenance/`)
- `GET/POST devices` — فهرست/ثبت دستگاه
- `GET/PATCH devices/{id}` — جزئیات/ویرایش
- `POST devices/{id}/status` — تغییر وضعیت
- `POST devices/{id}/pm` — ثبت نگهداری پیشگیرانه
- `GET devices/due-pm` — دستگاه‌های سررسیدشده‌ی PM
- `GET/POST work-orders` — فهرست/ثبت درخواست کار (فیلتر `?department=electrical` پشتیبانی می‌شود)
- `POST work-orders/generate-pm` — ساخت خودکار درخواست‌های PM سررسیدشده
- `GET/PATCH work-orders/{id}` — جزئیات/ویرایش
- `POST work-orders/{id}/route` — **ارجاع به واحد** (مرحله ۱)
- `POST work-orders/{id}/assign` — سپردن به تکنسین (مرحله ۲)
- `POST work-orders/{id}/status` — تغییر وضعیت

## رابط کاربری (فقط فارسی و RTL)
دو صفحه‌ی جدید در منوی «نگهداری و تعمیرات»:
- **دستگاه‌ها و PM** (`/app/maintenance/devices`) — جدول دستگاه‌ها با ستون **واحد**،
  فیلتر واحد، کارت‌های آماری، ثبت/ویرایش دستگاه (شامل انتخاب واحد)، تغییر وضعیت، ثبت PM و
  برجسته‌سازی PMهای سررسیدشده.
- **درخواست‌های کار** (`/app/maintenance/work-orders`) — نمای فهرست و برد (Kanban) با ستون/فیلتر
  **واحد**، ثبت درخواست (با انتخاب واحد)، **ارجاع به واحد**، سپردن به تکنسین، دکمه‌ی
  **ساخت خودکار PM**، و پیشبرد وضعیت طبق state machine.

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
- **بک‌اند:** ۲۳۰۸ تست سبز (۲۰ تست maintenance شامل ۶ تست جدید واحد/ارجاع/PM خودکار +
  تست‌های معماری/نام‌گذاری/seed).
  ```
  cd backend
  .venv\Scripts\python manage.py test tests --settings=config.settings.testing
  ```
- **فرانت:** `npm run typecheck` + `npm run test` (۱۵ سبز) + `npm run build` — همه سبز.

> توجه: چون یک migration جدید (`0002`) افزوده شده، اگر پایگاه‌داده‌ی محلی از قبل ساخته
> شده باشد، `run_dev.ps1` آن را خودکار اعمال می‌کند؛ در غیر این صورت یک‌بار
> `python manage.py migrate maintenance` را اجرا کنید. اگر دسترسی «ارجاع به واحد» را
> نداشتید، `python manage.py bootstrapPlatform` را برای هم‌گام‌سازی دسترسی جدید اجرا کنید.

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
