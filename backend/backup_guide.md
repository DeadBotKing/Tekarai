# راهنمای بک‌آپ کامل قبل از حذف دیتای دمو — TekaraiLive

> این بک‌آپ شامل همه چیز است: برنامه‌ریزی، تجهیزات، ساختمان، جانمایی، کاربران/نقش‌ها، درخواست‌ها. بعدا با یک کلیک می‌توانی برگردانی.

---

## روش ۱ — با SSMS (پیشنهادی، گرافیکی)

### مرحله ۱: SSMS را باز کن
1. روی سرور `C:\Users\Mitra\Desktop\Tekarai\backend` مطمئن باش SQL Server در حال اجراست (سیستم‌تری → SQL Server (SQLEXPRESS) در حال Run)
2. برنامه **SQL Server Management Studio (SSMS)** را باز کن
3. در پنجره Connect:
   - Server type: `Database Engine`
   - Server name: `localhost\SQLEXPRESS`
   - Authentication: `Windows Authentication`
   - بزن `Connect`

### مرحله ۲: پوشه بک‌آپ بساز
1. در ویندوز برو `C:\` یک پوشه بساز به نام `TekaraiBackup` → مسیر نهایی: `C:\TekaraiBackup`
2. روی پوشه راست‌کلیک → Properties → Security → مطمئن شو `SERVICE` و `Users` دسترسی Write دارند (معمولا دارند)

### مرحله ۳: بک‌آپ بگیر
1. در سمت چپ SSMS درختی: `Databases` را باز کن
2. روی دیتابیس `TekaraiLive` راست‌کلیک → `Tasks` → `Back Up...`
3. در پنجره Back Up:
   - Backup type: `Full`
   - Database: `TekaraiLive`
   - پایین بخش Destination: اگر آدرسی هست حذف کن (Remove)
   - بزن `Add...` → `...` → برو `C:\TekaraiBackup` → نام فایل: `TekaraiLive_20261123_1530.bak` (تاریخ امروز + ساعت)
   - بزن `OK`
4. برگردی به پنجره اصلی، تیک `Compression` اگر هست فعال بذار (حجم کمتر)
5. بزن `OK` → باید پیغام `The backup of database 'TekaraiLive' completed successfully.` بیاید

### مرحله ۴: تایید بک‌آپ
1. برو `C:\TekaraiBackup` باید فایل `.bak` با حجم مثلا ۵۰-۳۰۰ MB ببینی
2. (اختیاری) در SSMS یک Query جدید باز کن و بزن:
```sql
RESTORE VERIFYONLY FROM DISK = 'C:\TekaraiBackup\TekaraiLive_20261123_1530.bak';
```
باید بنویسد `The backup set on file 1 is valid.`

---

## روش ۲ — با دستور (سریع، بدون SSMS)

اگر SSMS نداری، همین فایل bat را اجرا کن:

1. فایل `backup_now.bat` را که کنار همین راهنما گذاشتم، بذار تو `C:\Users\Mitra\Desktop\Tekarai\backend`
2. روی آن دوبار کلیک کن (یا PowerShell: `.\backup_now.bat`)
3. خودکار فایل می‌سازد: `C:\TekaraiBackup\TekaraiLive_YYYYMMDD_HHMM.bak`

دستور داخلش:
```bat
sqlcmd -S localhost\SQLEXPRESS -E -Q "BACKUP DATABASE [TekaraiLive] TO DISK='C:\TekaraiBackup\TekaraiLive_%date%.bak' WITH INIT, COMPRESSION, STATS=10"
```

---

## بعد از بک‌آپ چی؟

1. یک کپی از فایل `.bak` روی هارد اکسترنال/گوگل درایو هم بگذار
2. شماره نسخه فعلی را یادداشت کن: `C:\ProgramData\Tekarai\Deployment\Previous-*.json` و `C:\inetpub\TekaraiReleases\...`
3. به من بگو `بک‌آپ گرفتم` تا فایل‌های حذف مرحله‌ای را بدهم:
   - مرحله ۱: درخواست کار/کالا
   - مرحله ۲: برنامه‌ریزی دمو (خطوط)
   - مرحله ۳: تجهیزات، ساختمان، جانمایی
   - مرحله ۴: پاکسازی نهایی و iisreset

## برگرداندن در صورت مشکل (Restore)

اگر چیزی اشتباه پاک شد:
1. SSMS → روی `Databases` راست‌کلیک → `Restore Database...`
2. Device → `...` → Add → فایل `C:\TekaraiBackup\TekaraiLive_....bak` را انتخاب کن
3. OK → همه چیز برمی‌گردد به لحظه قبل.

---
