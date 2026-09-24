# تحویل — اعلان و یادآوری PM (نگهداری پیشگیرانه)

وقتی سررسید PM یک دستگاه نزدیک باشد (یا گذشته باشد)، به **تکنسین نگهداری** و
**مدیر نگهداری** اعلان داده می‌شود. پیاده‌سازی دقیقاً روی زیرساخت موجود سوار
شده است: رویداد دامنه → دیسپچر مشترک (§36) → مصرف‌کننده‌ی اعلان (§30) →
فن‌اوت بر اساس نقش (§9) → موتور اعلان با کلید idempotency (§29).

## چه چیزی اضافه شد

### ۱) سمت Maintenance — اسکن سررسید و انتشار رویداد
- `SendPmRemindersCommand(tenantId, leadDays=3)` — فرمان جدید.
- `SendPmRemindersUseCase` در `deviceUseCases.py` — همه‌ی دستگاه‌های دارای
  برنامه‌ی PM را می‌خواند و بر اساس `nextDueDate`:
  - سررسید در بازه‌ی `leadDays` روز آینده → رویداد **`devicePmDueSoon`**
  - سررسید گذشته → رویداد **`devicePmOverdue`**
- **ایدمپوتنت در هر چرخه‌ی PM**: هر رویداد یک `eventId` قطعی دارد
  (`نام رویداد:deviceId:dueDate`). اجرای مکرر اسکن در همان چرخه، اعلان تکراری
  نمی‌سازد؛ با ثبت PM جدید، چرخه جلو می‌رود و `eventId` تازه ساخته می‌شود.
- DTO خروجی: `PmReminderRunDto` (تعداد اسکن‌شده / dueSoon / overdue + آیتم‌ها).

### ۲) سمت Notifications — پیکربندی مسیر (§8: بدون تغییر موتور)
- دو ردیف جدید در `DEFAULT_EVENT_ROUTES` (فایل `eventConsumer.py`):
  - `devicePmDueSoon` → نوع `maintenance.pmDueSoon`، دسته `MAINTENANCE`،
    اولویت `HIGH`
  - `devicePmOverdue` → نوع `maintenance.pmOverdue`، اولویت `URGENT`
  - گیرندگان هر دو: `ROLE = [maintenanceTechnician, maintenanceManager]`
- قالب‌های دو‌زبانه (fa-IR / en-US) در `seedNotifications`:
  `maintenance.pmDueSoon` و `maintenance.pmOverdue` با جای‌گیرهای
  `{deviceName}`, `{deviceCode}`, `{dueDate}`, `{daysLeft}`.
- سیاست جدید `maintenance.reminders` (دسته MAINTENANCE، cooldown=0) تا اگر
  چند دستگاه هم‌زمان سررسید شوند، ضدطوفان §28 اعلان‌های بعدی را تضعیف نکند.

### ۳) اجراکننده‌ها (Trigger)
- **فرمان مدیریتی** — برای زمان‌بندی (کرون/سرویس):
  ```bash
  # یک اسکن برای همه‌ی تنانت‌ها (پیش‌فرض ۳ روز پیش‌آگهی)
  python manage.py sendPmReminders

  # با گزینه‌ها
  python manage.py sendPmReminders --tenant <uuid> --lead-days 5
  python manage.py sendPmReminders --loop --interval 3600   # حالت توسعه
  ```
  در تولید همین اسکن را به هر زمان‌بند (cron، Celery beat، K8s CronJob)
  بدهید؛ روزی یک اجرا معمولاً کافی است.
- **API دستی** — `POST /api/v1/maintenance/devices/pm-reminders`
  (بدنه‌ی اختیاری: `{"leadDays": 3}`) برای اجرای دستی از UI؛ خروجی شامل
  متادیتای `dueSoonCount / overdueCount / scannedCount`.

## فایل‌های تغییر‌یافته / جدید

| فایل | تغییر |
|---|---|
| `backend/apps/maintenance/application/commands/maintenanceCommands.py` | + `SendPmRemindersCommand` |
| `backend/apps/maintenance/application/dto/maintenanceDtos.py` | + `PmReminderItemDto`, `PmReminderRunDto` |
| `backend/apps/maintenance/application/useCases/deviceUseCases.py` | + `SendPmRemindersUseCase` |
| `backend/apps/maintenance/infrastructure/container.py` | + `sendPmRemindersUseCase()` |
| `backend/apps/maintenance/management/commands/sendPmReminders.py` | **جدید** — زمان‌بند اسکن |
| `backend/apps/maintenance/presentation/api/views/deviceViews.py` | + `DevicePmRemindersView` |
| `backend/apps/maintenance/presentation/api/urls/maintenanceRoutes.py` | + مسیر `devices/pm-reminders` |
| `backend/apps/notifications/infrastructure/eventConsumer.py` | + دو مسیر رویداد PM |
| `backend/apps/notifications/management/commands/seedNotifications.py` | + قالب‌ها و سیاست MAINTENANCE |
| `backend/tests/integration/testPmReminderNotifications.py` | **جدید** — ۵ تست یکپارچگی |

## تست‌ها

`testPmReminderNotifications.py` — سناریوهای پوشش‌داده‌شده:
1. یادآوری «نزدیک سررسید» به هر دو نقش تکنسین و مدیر می‌رسد.
2. اعلان «سررسید گذشته» با اولویت `URGENT` ساخته می‌شود.
3. اجرای مکرر اسکن در همان چرخه‌ی PM اعلان تکراری نمی‌سازد (§29).
4. دستگاهی که هنوز به بازه‌ی پیش‌آگهی نرسیده، اعلانی تولید نمی‌کند.
5. فرمان مدیریتی `sendPmReminders` تنانت‌ها را اسکن می‌کند.

نتیجه‌ی کل سوییت: **Ran 2338 tests — OK** (شامل تست‌های معماری نام‌گذاری/لایه‌بندی).
