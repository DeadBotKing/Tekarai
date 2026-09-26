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

## اگر ویندوز گفت «file is not digitally signed»

این خطای خود ویندوز است (سیاست اجرای اسکریپت)، نه خطای پروژه. سه راه، از ساده به پیشرفته:

**۱) از فایل‌های `.cmd` استفاده کنید — هیچ محدودیتی ندارند (پیشنهادی):**

```powershell
.\fix_login.cmd        # عیب‌یابی و رفع خودکار
.\run_dev.cmd -UseSqlite   # اجرای کل برنامه
```
(می‌توانید در File Explorer هم روی همین دو فایل دوبار کلیک کنید.)

**۲) اجرای یک‌بارهٔ اسکریپت PowerShell با دور زدن سیاست:**

```powershell
powershell -ExecutionPolicy Bypass -File .\fix_login.ps1 -Sqlite
powershell -ExecutionPolicy Bypass -File .\run_dev.ps1 -UseSqlite
```

**۳) اجازهٔ دائمی برای کاربر خودتان (فایل‌ها هم باید از حالت «دانلودشده» خارج شوند):**

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
Get-ChildItem -Recurse -Filter *.ps1 | Unblock-File
```

**۴) بدون هیچ اسکریپتی، مستقیم با پایتون:**

```powershell
cd C:\Users\Mitra\Desktop\Tekarai
backend\venv\Scripts\python.exe backend\scripts\doctorLogin.py --fix --sqlite
```
(اگر محیط مجازی شما `.venv` نام دارد، همان را جایگزین کنید.)

## راه‌حل ۰ — عیب‌یاب خودکار (سریع‌ترین راه، تازه اضافه شد)

در ریشهٔ پروژه (`C:\Users\Mitra\Desktop\Tekarai`):

```powershell
.\fix_login.ps1 -Sqlite      # اگر SQL Server ندارید یا بالا نیست
.\fix_login.ps1              # اگر SQL Server/SQL Express دارید
.\fix_login.ps1 -CheckOnly   # فقط تشخیص، بدون تغییر در پایگاه داده
```

این اسکریپت پنج گام را بررسی و در صورت نیاز رفع می‌کند:

۱. بارگذاری تنظیمات جنگو (اگر پکیج‌ها نصب نباشند، نصب می‌کند)
۲. اتصال به پایگاه داده — موتور، نام و میزبان را چاپ می‌کند
۳. وجود جدول‌ها — اگر نباشند `migrate` می‌زند
۴. وجود Tenant و کاربر مدیر — اگر نباشند `bootstrapPlatform` را اجرا می‌کند
۵. **اجرای واقعی درخواست ورود** و چاپ کد وضعیت

اگر باز هم شکست بخورد، **متن کامل استثنای واقعی** (نه پیام عمومی) چاپ می‌شود؛
همان متن را بفرستید تا دقیقاً همان مشکل رفع شود.

خروجی موفق چنین است:

```
      کد وضعیت: HTTP 200
[ سالم ] ورود موفق بود. کلیدهای پاسخ: accessToken, expiresAt, ... , user

اطلاعات ورود از طریق مرورگر:
      Tenant code : platform
      Username    : platform-admin
      Password    : Tekarai-Demo-2026!
```

کدهای خروج: `0` سالم · `2` پکیج نصب نیست · `3` پایگاه داده در دسترس نیست ·
`4` جدول‌ها ساخته نشده‌اند · `5` ورود شکست خورد (متن استثنا چاپ می‌شود).

سه سناریو در محیط توسعه آزموده شد: پایگاه دادهٔ خالی (کد ۴)، `--fix` روی پایگاه دادهٔ
خالی (کد ۰ با ورود HTTP 200) و گذرواژهٔ اشتباه (کد ۵ با خطای `AUTH_CREDENTIALS_INVALID`).

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
