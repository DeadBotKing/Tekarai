# Phase 9 Runbook — Notification Platform

Persian step-by-step operational guide. Repo root: `C:\Users\Mitra\Desktop\Tekarai`,
backend venv inside `backend\.venv` (adjust if different). One command per block.

## 0. بعد از باز کردن ZIP فاز ۹

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\backend
```

اگر سرور قبلاً باز بوده، پنجره‌اش را ببندید (Ctrl+C) و بعد از مهاجرت دوباره باز کنید.

## 1. مهاجرت دیتابیس (۱۲ جدول جدید)

```powershell
.\.venv\Scripts\python.exe manage.py migrate notifications
```

خروجی مورد انتظار: ردیف‌های `Applying notifications.0001_phase9_notifications... OK`.

## 2. seed اولیه (قالب‌های fa-IR/en-US + ۷ سیاست پیش‌فرض)

```powershell
.\.venv\Scripts\python.exe manage.py seedNotifications
```

خروجی: `Notification seed: +20 templates (0 re-versioned), +7 new policies...`
اجرای دوباره idempotent است (+0).

## 3. اجرای تست‌ها (۴۵۷ تست)

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.testing"
.\.venv\Scripts\python.exe manage.py test tests --parallel 1
Remove-Item Env:DJANGO_SETTINGS_MODULE
```

⚠️ بعد از تست حتماً `Remove-Item Env:DJANGO_SETTINGS_MODULE` را بزنید وگرنه
سرور با دیتابیس تست (in-memory) بالا می‌آید.

## 4. اجرای سرور (HTTP + WebSocket در یک پروسه)

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

## 5. worker اعلان‌ها (اختیاری در توسعه — پنجره دوم)

```powershell
.\.venv\Scripts\python.exe manage.py runNotificationWorker
```

worker هر ۵ ثانیه: dispatch → retry → scheduleها → digestها → انقضا.
بدون worker هم ارسال فوری از مسیر inline انجام می‌شود؛ worker برای
بازیابی کرش، زمان‌بندی‌ها و digestهاست.

## 6. دمو با curl (پنجره سوم)

```powershell
$base="http://127.0.0.1:8000/api/v1"
```

ورود ادمین پلتفرم:

```powershell
Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body '{"tenantCode":"platform","identifier":"platform-admin","password":"<رمز شما>"}'
```

توکن را جایگزین کنید:

```powershell
$h=@{Authorization="Bearer <accessToken>"}
```

ارسال اعلان (بعد از bootstrap دوباره، platform-admin این مجوز را دارد):

```powershell
Invoke-RestMethod -Method Post -Uri "$base/notifications/admin/send" -Headers $h -ContentType "application/json" -Body '{"recipientType":"USER","recipientValue":["<userId>"],"notificationType":"test.ping","category":"SYSTEM","priority":"HIGH","title":"سلام از فاز ۹"}'
```

دریافت صندوق کاربر (با توکن خود همان کاربر):

```powershell
Invoke-RestMethod -Uri "$base/notifications/" -Headers $h
```

شمارنده خوانده‌نشده، علامت‌گذاری خوانده‌شده، سناریوی idempotency (ارسال
دوباره همان eventId → همان notificationId و `duplicates:1`) و متریک‌ها:

```powershell
Invoke-RestMethod -Uri "$base/notifications/unread-count" -Headers $h
Invoke-RestMethod -Method Post -Uri "$base/notifications/<id>/read" -Headers $h
Invoke-RestMethod -Uri "$base/notifications/admin/metrics" -Headers $h
```

## 7. WebSocket (برای تست دستی)

هر کلاینت WS با `wss://…/ws/notifications/?token=<accessToken>`؛ فریم‌ها:
`notification.ready` بعد از اتصال، سپس `notification.event` برای هر اعلان.
اگر کلاینت آفلاین باشد چیزی از دست نمی‌رود — بعد از اتصال، `GET /notifications/` را بگیرید.

## 8. نکات عملیاتی

- قالب‌ها: `POST /api/v1/notifications/admin/templates` — ذخیره روی کلید
  موجود = نسخه بعدی (§19)؛ نسخه‌ها در جدول immutable می‌مانند.
- سیاست‌ها: `POST …/admin/policies` با `matchType=TYPE|CATEGORY`؛ هر چیزی
  بدون سیاست، به سیاست ضمنی «فقط IN_APP» می‌رسد.
- قوانین مستأجر: `…/admin/tenant-rules` با `FORCED|DENIED`؛ غیرفعال‌کردن
  IN_APP برای SECURITY قابل قبول نیست (422).
- تعویض providerها (SMTP واقعی/FCM/…): تنظیمات `NOTIFICATION_EMAIL_PROVIDERS`
  و مشابه آن — بدون تغییر کد (ADR-024).
- ثبت رویداد جدید برای مصرف Outbox: کلید جدید در `NOTIFICATION_EVENT_ROUTES`
  (پیش‌فرض در `eventConsumer.py`).
- لاگ‌ها هیچ‌وقت محتوای اعلان یا توکن device را ثبت نمی‌کنند (§33/§45).
