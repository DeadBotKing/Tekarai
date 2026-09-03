# Phase 08 Runbook — Communication Platform (Windows / PowerShell)

پیش‌نیاز: فازهای ۱ تا ۷ (ریپو در `C:\Users\Mitra\Desktop\Tekarai`، venv داخل `backend\`).

## 1) نصب وابستگی‌های جدید (فقط بار اول)

پکیج‌های جدید این فاز: `channels==4.3.2`، `daphne==4.2.3`، `channels-redis==4.3.0`
(در `requirements/base.txt` پین شده‌اند):

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\backend
.\venv\Scripts\Activate.ps1
pip install -r requirements\base.txt
```

## 2) مایگریشن

```powershell
python manage.py migrate --no-input
```

۱۷ جدول جدید با پیشوند `communication` ساخته می‌شود (به‌همراه `communicationOutbox`).

## 3) اجرای سرور

```powershell
python manage.py runserver 127.0.0.1:8000
```

از این فاز، `runserver` با daphne بالا می‌آید و **هم REST و هم WebSocket** را در یک
پروسه سرو می‌کند (در لاگ ابتدای اجرا `Listening on TCP address` را می‌بینید).

> اگر پنجره‌ی سرور را ببندید، خطای `Unable to connect` طبیعی است — دوباره `runserver` بزنید.

## 4) تست‌ها (پنجره دوم)

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\backend
.\venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE="config.settings.testing"
python manage.py test tests --parallel 1
```

انتظار: **386 tests, OK** (شامل ۲۹ تست دامنه، ۳۳ تست کاربردی §38، ۸ تست REST و ۵ تست WS فاز ۸).

## 5) دود سریع (smoke)

```powershell
curl.exe -s http://127.0.0.1:8000/healthz/            # 200
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/api/v1/communication/conversations
# 401 → یعنی احراز هویت §17 برقرار است
```

اتصال WebSocket (مثال با Node/wscat):

```
wscat -c "ws://127.0.0.1:8000/ws/communication/?token=<ACCESS_TOKEN>"
> {"type": "presence", "payload": {"status": "ONLINE"}}
< {"type": "presence.ack", ...}
```

## 6) نکته‌های عملیاتی

- **Redis برای presence/چنل‌لایر** فقط در production لازم است (`REDIS_URL`)؛ در
  development بدون Redis هم همه‌چیز با fallback درون‌حافظه‌ای کار می‌کند.
- **Secret منظم**: در development بدون `SECRET_KEY`، هر پروسه کلید موقت خودش را
  می‌سازد؛ توکنی که بیرون از پروسه‌ی سرور ساخته شود معتبر نیست (همان پروسه که
  login می‌دهد، WS را هم تأیید می‌کند). برای تست‌های بیرونی، `SECRET_KEY` ثابت
  در env بگذارید.
- **Outbox**: رخدادهای یکپارچه (`Communication…V1`) بعد از commit با
  `OutboxDispatcher` منتشر می‌شوند؛ ردیف ناموفق PENDING می‌ماند و دوباره تلاش
  می‌شود (§38 سناریوی ۱۰).
- **متریک‌ها**: `GET /api/v1/communication/metrics` (§39).
