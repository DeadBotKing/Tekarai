# Tekarai — گزارش اجرا و تست کامل

**تاریخ:** ۲۰۲۶-۰۹-۲۲
**محیط تست:** Python 3.13 · Django 6.1 · SQLite (حالت آفلاین) · Node/Vite · Provider هوش مصنوعی deterministic
**وضعیت کلی:** ✅ **همه سبز**

---

## استپ‌هایی که رفتیم (هر استپ + تستش)

### ✅ استپ ۰ — راه‌اندازی پلتفرم (`run_dev.ps1`)
تمام مراحل اسکریپت تأیید شد: نصب وابستگی‌ها → migrate (۳۰ migration) → seed ادمین و workspace → اجرای سرور.
- `GET /healthz/` → **HTTP 200**
- لاگین `platform-admin` → **موفق** (توکن JWT، ۵۷ مجوز)

### ✅ استپ ۱ — تست جریان‌های اصلی کسب‌وکار (`exercise_flows.ps1`)
روی سیستم کاربر اجرا شد: **۲۵/۲۵ PASS**
- لاگین + مجوزها · کاربران و نقش‌ها · اعلان broadcast · چت/گفتگو · اجرای AI Agent (COMPLETED)

### ✅ استپ ۲ — تست زیرساخت (`exercise_step5.ps1`)
- سشن‌های فعال ✅ · API Key (ساخت/لیست/باطل) ✅ · Audit stream با pagination ✅

### ✅ استپ ۳ — مجموعه‌ی کامل تست بک‌اند
| دسته | تعداد | نتیجه |
|---|---|---|
| Architecture | 164 | ✅ OK |
| Unit | 1059 | ✅ OK |
| Application | 606 | ✅ OK |
| Integration | 459 | ✅ OK |
| **کل (یکجا)** | **2288** | ✅ **OK** |

### ✅ استپ ۴ — فرانت‌اند
- Vitest: **۱۵/۱۵ passed** (۷ فایل)
- TypeScript typecheck: ✅ پاک
- Production build: ✅ موفق (۸۸ ماژول)

---

## 🔧 مشکلات واقعی که پیدا و رفع شد

هنگام اجرای تست‌های معماری، ۳ تخلف واقعی از قواعد خودِ پروژه کشف و اصلاح شد (از ۶ FAIL به ۰):

1. **`apps/ai/models.py`** (حذف شد) — فایل پل زائد در سطح بالای اپ؛ طبق قاعده‌ی پروژه مدل‌ها فقط باید در `infrastructure/` باشند. `apps.py` از قبل همان مدل‌ها را رجیستر می‌کند (۳۷ مدل AI پس از حذف همچنان سالم کشف می‌شوند).
2. **`apps/ai/migrations/`** (حذف شد) — پوشه‌ی migrations زائد و خالی در سطح بالا؛ migrationهای واقعی در `infrastructure/migrations/` هستند. هیچ اپ دیگری چنین پوشه‌ای نداشت.
3. **`apps/ai/tests/test_provider.py`** (حذف شد) — کپی تکراری snake_case که کنوانسیون camelCase پروژه را نقض می‌کرد؛ نسخه‌ی درست `testProvider.py` با همان محتوا موجود است.

> هیچ‌کدام از این حذف‌ها پوشش تست یا عملکرد را کاهش نداد — همگی فایل‌های زائد/تکراری بودند و پس از رفع، کل ۲۲۸۸ تست بک‌اند سبز شد.

---

## ✅ استپ ۵ — Quality Gate کامل CI (همان چیزی که موقع push اجرا می‌شود)

مطابق `.github/workflows/backendCi.yml` کل دروازه‌ی کیفیت اجرا و سبز شد:

| بررسی | نتیجه |
|---|---|
| `manage.py check` (Django system check) | ✅ no issues |
| `makemigrations --check` (migration جا نمانده) | ✅ No changes detected |
| `ruff check` (lint) | ✅ All checks passed |
| `ruff format --check` | ✅ 807 files formatted |
| `mypy config apps tests` | ✅ no issues in 759 files |
| کل تست‌ها (مجدد پس از اصلاحات) | ✅ 2288 OK |

### 🔧 مشکلات کیفیت کد که پیدا و رفع شد
هنگام اجرای Quality Gate مشخص شد CI از فاز ۱۸b قرمز بوده (اپ‌های projects/tasks بدون گذر از دروازه commit شده بودند):

4. **۸ خطای ruff lint** — import مرتب‌نشده / f-string بدون placeholder / import بلااستفاده. با `ruff check --fix` اصلاح شد.
5. **۱۲ فایل بدون فرمت** — با `ruff format` مرتب شد (فقط cosmetic).
6. **۶۰ خطای mypy در ۲ فایل** — `apps/projects/infrastructure/container.py` و `apps/tasks/infrastructure/container.py`: نوع بازگشتی `_deps()` از `dict[str, object]` به `dict` تغییر کرد (مطابق الگوی استاندارد بقیه‌ی اپ‌های سبز مثل communication). این باعث می‌شود `**_deps()` با انواع دقیق پارامترها سازگار شود.

> پس از این اصلاحات، کل ۲۲۸۸ تست دوباره اجرا شد و OK ماند — هیچ رفتاری تغییر نکرد.

**دستور PowerShell برای اعمال روی سیستم کاربر:** در بخش پایانی این گفتگو ارائه شد.

---

## ✅ استپ ۶ — تست‌های E2E فرانت‌اند (Playwright)

تست‌ها در حالت `VITE_DEMO_MODE=true` اجرا می‌شوند (بدون نیاز به بک‌اند؛ Playwright خودش build و preview را بالا می‌آورد) و رفتار واقعی کاربر در مرورگر را پوشش می‌دهند: لاگین، ناوبری کل مسیرهای محافظت‌شده، ساخت پروژه/تسک، آپلود سند، و تغییر تم/زبان (RTL فارسی).

| پروژه | نتیجه |
|---|---|
| chromium (Desktop Chrome) | ✅ 4 passed |
| mobile (Pixel 5) | ✅ 2 passed + 2 skipped (skip عمدی: ماتریس مسیرها فقط desktop) |

> نیازمند نصب یک‌باره‌ی مرورگر: `npx playwright install chromium`؛ در لینوکس علاوه بر آن `npx playwright install-deps chromium` (کتابخانه‌های سیستمی مثل libnss3/libnspr4). روی ویندوز معمولاً فقط `npx playwright install` کافی است.

---

## نکته‌ی MFA
احراز هویت دومرحله‌ای (MFA/TOTP) به‌صورت پیش‌فرض **غیرفعال** است (`mfaRequired=false` در پاسخ لاگین). برای یک استقرار لوکال داخل شبکه‌ی شرکت که از بیرون دسترسی ندارد، نیازی به فعال‌سازی آن نیست.
