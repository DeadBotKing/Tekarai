# اجرای Tekarai روی ویندوز (PowerShell)

پیش‌نیاز: **Python 3.12 یا بالاتر** و **Node.js 20 یا بالاتر**.

```powershell
python --version
node --version
```

اگر `python` چیزی برنگرداند یا Microsoft Store باز شد، از `py -3.12` به‌جای `python` در تمام
دستورهای زیر استفاده کنید.

> زیپ تحویلی شامل `backend\.env`، `frontend-web\.env` و دیتابیس سیدشدهٔ
> `backend\devdb.sqlite3` است. پس نیازی به `migrate` و seed نیست — مستقیم بالا می‌آید.

---

## ۱. آماده‌سازی (فقط یک‌بار)

زیپ را از حالت فشرده خارج کنید و وارد پوشه شوید:

```powershell
cd C:\path\to\Tekarai
```

### بک‌اند

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements\development.txt
```

اگر فعال‌سازی venv با خطای **"running scripts is disabled on this system"** رد شد، یک‌بار
این را اجرا کنید و دوباره `Activate.ps1` را صدا بزنید:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

(راه جایگزین بدون تغییر سیاست اجرا: به‌جای فعال‌سازی، مستقیم
`.\.venv\Scripts\python.exe manage.py ...` را صدا بزنید.)

### فرانت‌اند

در یک پنجرهٔ PowerShell **دوم**:

```powershell
cd C:\path\to\Tekarai\frontend-web
npm ci
```

---

## ۲. اجرا (هر بار)

**پنجرهٔ اول — بک‌اند روی پورت 8000:**

```powershell
cd C:\path\to\Tekarai\backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000 --settings=config.settings.development
```

**پنجرهٔ دوم — فرانت‌اند روی پورت 4173:**

```powershell
cd C:\path\to\Tekarai\frontend-web
npm run dev
```

سپس در مرورگر: **<http://localhost:4173>**

Vite خودش `/api` و `/ws` را به `127.0.0.1:8000` پراکسی می‌کند، پس نیازی به تنظیم آدرس
API نیست.

### ورود

| مورد | مقدار |
|---|---|
| کد مستأجر (tenant) | `platform` |
| نام کاربری | `platform-admin` |
| رمز عبور | `Tekarai-Demo-2026!` |

---

## ۳. ساخت دوبارهٔ دیتابیس (اختیاری)

اگر دیتابیس را خراب کردید یا می‌خواهید از صفر شروع کنید:

```powershell
cd C:\path\to\Tekarai\backend
.\.venv\Scripts\Activate.ps1
Remove-Item devdb.sqlite3 -ErrorAction SilentlyContinue
python manage.py migrate       --settings=config.settings.development
python manage.py seedWorkspace --settings=config.settings.development
python manage.py seedDemo      --settings=config.settings.development
```

خروجی مورد انتظار seed آخر:

```
Demo seed done for tenant «platform» → locations=9, personnel=6, spareParts=6, devices=12, pmPlans=7, workOrders=10
```

---

## ۴. اجرای تست‌ها

```powershell
# بک‌اند (۲۹۵۴ تست)
cd C:\path\to\Tekarai\backend
.\.venv\Scripts\Activate.ps1
python manage.py test --settings=config.settings.testing
ruff check .
ruff format --check .
mypy config apps tests

# فرانت‌اند (۲۴۴ تست)
cd C:\path\to\Tekarai\frontend-web
$env:VITE_DEMO_MODE = "true"; npm test
npm run typecheck
npm run build
```

نکته: در PowerShell نحوهٔ ست‌کردن متغیر محیطی `$env:NAME = "value"` است، نه
`VITE_DEMO_MODE=true npm test` که شکل لینوکسی است و در PowerShell خطا می‌دهد.

---

## ۵. حالت دمو بدون بک‌اند

اگر فقط می‌خواهید رابط کاربری را ببینید و اصلاً پایتون اجرا نکنید، در
`frontend-web\.env` مقدار زیر را عوض کنید:

```
VITE_DEMO_MODE=true
```

و فقط `npm run dev` را اجرا کنید؛ داده‌ها از ماک داخلی می‌آیند.

---

## مشکلات رایج

| نشانه | علت و راه‌حل |
|---|---|
| `Activate.ps1 cannot be loaded` | سیاست اجرای اسکریپت — دستور `Set-ExecutionPolicy` بالا را بزنید. |
| `'python' is not recognized` | از `py -3.12` استفاده کنید یا پایتون را با گزینهٔ «Add to PATH» نصب کنید. |
| صفحه بالا می‌آید ولی لاگین خطای شبکه می‌دهد | بک‌اند در پنجرهٔ اول اجرا نیست یا پورت 8000 اشغال است. |
| `Port 4173 is in use` | نمونهٔ قبلی Vite هنوز باز است؛ پنجره را ببندید یا `npm run dev -- --port 4174`. |
| `DisallowedHost` | دارید با نام میزبانی غیر از `localhost`/`127.0.0.1` وصل می‌شوید؛ آن نام را به `ALLOWED_HOSTS` در `backend\.env` اضافه کنید. |
| لاگین با `username` کار نمی‌کند | پارامتر API اسمش `identifier` است، نه `username` (فقط اگر مستقیم با API کار می‌کنید). |
