# وضعیت خط + حذف فعال

- در حالت ویرایش، ستون وضعیت تبدیل به dropdown می‌شود: در حال تولید / متوقف / تعویض محصول / تعمیرات — انتخاب همان لحظه روی خط اعمال می‌شود و فیلتر هم عوض می‌شود
- دکمه حذف کنار هر دارو فعال شد (حتی اگر ۱ دارو مانده باشد) — با زدن، آن برنامه دارو حذف می‌شود؛ اگر همه داروهای یک خط را حذف کنی، خط با برنامه ۰ می‌ماند
- نصب:
  copy frontend-web\src\pages\ProductionPlanningDashboardPage.tsx frontend-web\src\pages\ProductionPlanningDashboardPage.tsx
  npm run build && powershell -ExecutionPolicy Bypass -File ..\Deploy-Menu-IIS.ps1   (از داخل frontend-web)
  یا: cd frontend-web && npm run build && cd .. && powershell -ExecutionPolicy Bypass -File Deploy-Menu-IIS.ps1
