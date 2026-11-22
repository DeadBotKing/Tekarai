# Add Role Button Feature

دکمه "افزودن نقش جدید" به صفحه مدیریت > نقش‌ها اضافه شد.

## نصب
1. کپی فایل:
   copy frontend-web\src\pages\AdministrationPage.tsx C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\pages\AdministrationPage.tsx

2. بیلد:
   cd C:\Users\Mitra\Desktop\Tekarai\frontend-web
   npm run build

3. دیپلوی:
   powershell -ExecutionPolicy Bypass -File C:\Users\Mitra\Desktop\Tekarai\Deploy-Menu-IIS.ps1

## استفاده
- مدیریت > نقش‌ها > دکمه "افزودن نقش جدید" بالا سمت چپ
- کد نقش: انگلیسی بدون فاصله (مثلاً production_planner)
- نام فارسی: مثلاً "برنامه‌ریز تولید"
- تیک مجوزها رو بزن و "ساخت نقش" بزن - همون لحظه به لیست اضافه میشه
- بعد می‌تونی از سوپرادمین > کاربران > افزودن دسترسی، نقش رو به فرد بدی
