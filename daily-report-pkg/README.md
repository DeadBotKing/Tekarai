# Daily Report Feature - Tekarai

## محتویات
- `frontend-web/src/pages/DailyReportPage.tsx` - صفحه گزارش روزانه (9 واحد، فرم ساده، تایید سرپرست/رییس)
- `frontend-web/src/app/configuration/navigation.ts` - منوی اصلاح‌شده: مخفی‌سازی تولید/داشبورد/مدیریت برای کارشناس، افزودن "گزارش روزانه"
- `frontend-web/src/app/router/AppRouter.patch.txt` - دستور افزودن route جدید
- `backend/update_perms_phase2.sql` - اصلاح دسترسی‌ها (لیست تجهیزات برای کارشناس، تولید فقط برای مدیر)

## نصب
1. کپی فایل‌ها:
   ```
   copy frontend-web\src\pages\DailyReportPage.tsx C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\pages\
   copy frontend-web\src\app\configuration\navigation.ts C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\app\configuration\navigation.ts
   ```
2. ویرایش `frontend-web\src\app\router\AppRouter.tsx`:
   - اضافه کردن import: `const DailyReportPage = named(() => import("../../pages/DailyReportPage"), "DailyReportPage");`
   - اضافه کردن route: `<Route path="daily-report" element={<DailyReportPage />} />` داخل Route /app
3. اعمال SQL:
   ```
   sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i backend\update_perms_phase2.sql
   ```
4. build:
   ```
   cd frontend-web; npm run build
   ```
5. Deploy via `Deploy-Menu-IIS.ps1`

## رفتار
- همه (کارشناس، پرسنل، سرپرست) می‌توانند برای واحد خود گزارش ثبت کنند.
- تایید نهایی فقط سرپرست و رییس همان واحد (مدیر فنی همه را می‌بیند).
- تولید/داشبورد/مدیریت برای کارشناس/پرسنل مخفی، لیست تجهیزات فقط واحد خودش (فقط نمایش).
