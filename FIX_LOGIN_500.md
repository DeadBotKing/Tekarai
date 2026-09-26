# خطای «Unexpected server error.» هنگام ورود — تشخیص و درمان

## این پیام از کجا می‌آید؟

از **بک‌اند جنگو**، نه از فرانت. تنها جای تولید این متن در کل پروژه:

`backend/apps/sharedKernel/presentation/api/exceptionHandler.py:54`

```python
logger.exception("Unhandled exception", ...)
return Response(errorEnvelope([errorEntry("SYS_INTERNAL_ERROR", "Unexpected server error.")]), status=500)
```

یعنی: فرانت درخواست `POST /api/v1/auth/login` را فرستاده، جنگو آن را گرفته، ولی وسط کار
استثنای مدیریت‌نشده خورده و ۵۰۰ برگردانده.

## بازتولید و اثبات علت (انجام شد)

در همین محیط، بک‌اند را با SQLite بالا آوردم و سه حالت را آزمودم:

| حالت پایگاه داده | پاسخ `POST /api/v1/auth/login` |
|---|---|
| **بدون migrate (جدول‌ها وجود ندارند)** | **HTTP 500 · `SYS_INTERNAL_ERROR` · «Unexpected server error.»** ← دقیقاً خطای شما |
| migrate شده، ولی کاربر/Tenant اشتباه | HTTP 401 · `AUTH_CREDENTIALS_INVALID` · «Invalid credentials.» |
| migrate شده + `bootstrapPlatform` اجرا شده + کاربر درست | HTTP 200 با `accessToken`, `refreshToken`, `user`, `permissions` |

**نتیجه:** ۵۰۰ یعنی بک‌اند به جدول‌های پایگاه داده نمی‌رسد — یا `migrate` اجرا نشده،
یا پایگاه دادهٔ پیکربندی‌شده (به‌طور پیش‌فرض SQL Server) اصلاً بالا نیست.
اگر نام کاربری یا گذرواژه اشتباه بود، خطا ۴۰۱ می‌شد نه ۵۰۰.

## راه‌حل ۱ — یک دستور، همه‌چیز آماده (پیشنهادی)

PowerShell را در ریشهٔ پروژه باز کنید (`C:\Users\Mitra\Desktop\Tekarai`) و:

```powershell
# اگر SQL Server / SQL Express ندارید یا بالا نیست:
.\run_dev.ps1 -UseSqlite
```

این اسکریپت خودش venv می‌سازد، پکیج‌ها را نصب می‌کند، `migrate` می‌زند،
`bootstrapPlatform` را اجرا می‌کند، داده نمونه می‌ریزد و بک‌اند + فرانت را با هم بالا می‌آورد.

اطلاعات ورود پس از اجرای این اسکریپت:

| فیلد | مقدار |
|---|---|
| Tenant code | `platform` |
| Email or username | `platform-admin` |
| Password | `Tekarai-Demo-2026!` |

با SQL Express (حالت پیش‌فرض): `.\run_dev.ps1` — و اگر نمونهٔ نام‌دار دارید:
`.\run_dev.ps1 -DbServer "localhost\SQLEXPRESS"`

## راه‌حل ۲ — بدون هیچ بک‌اندی (فقط دیدن رابط کاربری و چت)

```powershell
.\run_dev.ps1 -DemoMode
```
یا مستقیم:
```powershell
cd C:\Users\Mitra\Desktop\Tekarai\frontend-web
$env:VITE_DEMO_MODE="true"
npm run dev
```
در حالت دمو، **هر مقداری** در سه فیلد ورود بنویسید وارد می‌شوید (تابع `demoLogin` ورودی را نادیده می‌گیرد)
و همهٔ صفحه‌ها از جمله «گفت‌وگو» با دادهٔ نمونه کار می‌کنند.

⚠️ نکتهٔ مهم PowerShell: اگر قبلاً در همین پنجره `$env:VITE_DEMO_MODE="false"` زده باشید،
تا بستن پنجره همان مقدار می‌ماند. برای برگشت به دمو حتماً دوباره `"true"` بگذارید یا پنجرهٔ جدید باز کنید.

## راه‌حل ۳ — دستی، مرحله‌به‌مرحله

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\backend
.\venv\Scripts\Activate.ps1                 # یا: .\.venv\Scripts\Activate.ps1
pip install -r requirements\development.txt

# اگر SQL Server ندارید، SQLite را انتخاب کنید:
$env:dbEngine="sqlite"

python manage.py migrate
$env:PLATFORM_ADMIN_PASSWORD="Tekarai-Demo-2026!"
python manage.py bootstrapPlatform          # Tenant «platform» و کاربر «platform-admin» را می‌سازد
python manage.py runserver 0.0.0.0:8000
```

سپس در پنجرهٔ دوم:
```powershell
cd C:\Users\Mitra\Desktop\Tekarai\frontend-web
$env:VITE_DEMO_MODE="false"
npm run dev
```

## دیدن خطای واقعی (نه پیام عمومی)

جنگو متن کامل استثنا را لاگ می‌کند. بعد از اجرای `run_dev.ps1` اینجا را ببینید:

```powershell
Get-Content .\logs\backend.err.log -Tail 40
Get-Content .\logs\backend.log -Tail 40
```

اگر عبارت‌هایی مثل `no such table: identityUsers` یا `OperationalError` دیدید،
یعنی همان مشکل migrate/پایگاه داده است.

## بهبودی که در همین فاز به فرانت اضافه شد

قبلاً صفحهٔ ورود، متن خام سرور را نشان می‌داد («Unexpected server error.»).
حالا `LoginPage` خطا را دسته‌بندی می‌کند و پیام راهنما می‌دهد:

- خطای ۵۰۰ → «سرور بالا هست ولی ورود را کامل نکرد. معمولاً یعنی پایگاه داده هنوز migrate نشده است…»
- عدم دسترسی به سرور / تایم‌اوت → «سرور در دسترس نیست. بک‌اند را روی پورت ۸۰۰۰ اجرا کنید یا حالت دمو…»
- ۴۰۱ → «نام کاربری یا گذرواژه درست نیست.»

فایل‌های تغییر‌یافته: `frontend-web/src/pages/LoginPage.tsx`،
`frontend-web/src/core/localization/i18n.ts` (کلیدهای `auth.serverError`, `auth.networkError`, `auth.invalid` فارسی).
