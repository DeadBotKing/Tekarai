# Tekarai — راهنمای اجرای یک‌دستوره

## اجرا (ویندوز + SQL Express)

فقط یک دستور در PowerShell (از پوشهٔ ریشهٔ پروژه):

```powershell
.\run_dev.ps1
```

این اسکریپت خودش همه‌چیز را انجام می‌دهد:
1. ساخت `backend\.venv` و نصب وابستگی‌ها (شامل `mssql-django` + `pyodbc`)
2. نصب `frontend-web\node_modules`
3. تشخیص خودکار درایور ODBC (18 ← 17 ← SQL Server)
4. ساخت دیتابیس اگر وجود نداشته باشد
5. نوشتن `frontend-web\.env` (ورود واقعی، نه دمو)
6. اجرای migrate و ساخت خودکار ادمین
7. اجرای **همزمان** بک‌اند (پورت 8000) و فرانت‌اند (پورت 4173)

بعد از بالا آمدن، در مرورگر باز کن: **http://localhost:4173**

## اطلاعات ورود (پیش‌فرض)

| فیلد | مقدار |
|---|---|
| **Tenant code** | `platform` |
| **Email or username** | `platform-admin` |
| **Password** | `Tekarai-Demo-2026!` |

> گذرواژهٔ ادمین را می‌توانی عوض کنی: `.\run_dev.ps1 -AdminPassword "گذرواژه‌ی جدید"`

## حالت‌های اتصال به SQL Server

**پیش‌فرض:** نمونهٔ نام‌دار SQL Express (`localhost\SQLEXPRESS`) با احراز هویت Windows.

اگر SQL Express تو با SQL Login (مثلاً `sa`) تنظیم شده:

```powershell
.\run_dev.ps1 -DbUser sa -DbPassword "رمز تو"
```

اگر TCP/IP را روی پورت 1433 فعال کرده‌ای (نمونهٔ پیش‌فرض):

```powershell
.\run_dev.ps1 -DbServer "localhost" -DbPort 1433
```

اگر فعلاً دیتابیس نمی‌خواهی (حالت آفلاین SQLite):

```powershell
.\run_dev.ps1 -UseSqlite
```

## پیش‌نیازها

- Python 3.12+
- Node.js (نسخهٔ 20 به بالا)
- SQL Server (Express) نصب و در حال اجرا
- **ODBC Driver 18 for SQL Server** — اگر نصب نیست: https://aka.ms/downloadmsodbcsql

> نکته: اگر درایور 18 نصب نیست و فقط درایور 17 (یا درایور قدیمی «SQL Server») داری،
> اسکریپت خودش آن را پیدا می‌کند.

## تست سلامت جریان‌ها (اختیاری)

وقتی پلتفرم بالا آمد، می‌توانی جریان‌های آمادهٔ بک‌اند را یک‌جا تمرین کنی
(ساخت کاربر/نقش، اعلان broadcast، گفتگو/چت، اجرای ایجنت AI):

```powershell
.\exercise_flows.ps1
```

برای هر مرحله `[PASS]`/`[FAIL]` چاپ می‌کند و در صورت شکست با کد ۱ خارج می‌شود.
اگر بک‌اند روی پورت دیگری است: `.\exercise_flows.ps1 -BaseUrl "http://127.0.0.1:8000"`.

## توقف

در پنجرهٔ PowerShell کلید **Ctrl+C** را بزن — هر دو سرویس با هم بسته می‌شوند.

## عیب‌یابی

اسکریپت خروجی بک‌اند را در `logs\backend.log` و `logs\backend.err.log` ذخیره می‌کند
و اگر بک‌اند بالا نیاید، خودش آخرین خطوط لاگ را چاپ می‌کند.

اگر در فرانت‌اند خطای `ECONNREFUSED 127.0.0.1:8000` دیدی یعنی **بک‌اند بالا نیامده**.
دلایل رایج و راه‌حل:

| خطا | راه‌حل |
|---|---|
| `'mssql' isn't an available database backend` | درایورها نصب نشده‌اند؛ خروجی pip را ببین. یا از `-UseSqlite` استفاده کن. |
| خطای `daphne / asyncio / twisted` | `.\run_dev.ps1 -UseWaitress` |
| خطای `ODBC / pyodbc / login failed` | `.\run_dev.ps1 -DbServer "localhost" -DbPort 1433` یا `-DbUser sa -DbPassword "رمز"` |
| پورت 8000 اشغال است | اسکریپت خودش پروسهٔ اضافی python/node را می‌بندد |

برای دیدن خطای بک‌اند به‌صورت مستقیم (در پنجرهٔ فعلی):

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\backend
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

(بدون متغیر محیطی، با SQLite شروع می‌شود — فقط برای تست اینکه بک‌اند اصلاً بالا می‌آید یا نه.)

## حالت دمو (بدون بک‌اند)

```powershell
.\run_dev.ps1 -DemoMode
```

در این حالت ورود آفلاین است و هر مقداری در فرم ورود کار می‌کند.
