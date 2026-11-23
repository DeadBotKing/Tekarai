# داشبورد تولید — تفکیک دارو (فیلد آزاد)

هر خط حالا می‌تواند چند دارو داشته باشد. آمنه با "ویرایش برنامه" می‌تواند:
- نام هر دارو را آزاد تایپ کند
- برنامه و تولید هر دارو را جدا بزند
- با دکمه "+ خط ..." دارو جدید به هر خط اضافه کند
- داروی اضافی را حذف کند (حداقل ۱ دارو باید بماند)
- جدول و دونات‌ها بر اساس اسم دارو جمع می‌زنند (نه فقط خط)

## نصب
```
copy frontend-web\src\pages\ProductionPlanningDashboardPage.tsx frontend-web\src\pages\ProductionPlanningDashboardPage.tsx
npm run build
powershell -ExecutionPolicy Bypass -File Deploy-Menu-IIS.ps1
```
بعد با اکانت آمنه (productionPlanner) وارد شوید → داشبورد برنامه‌ریزی تولید → ویرایش برنامه
