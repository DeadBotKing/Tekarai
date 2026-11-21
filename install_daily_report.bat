@echo off
chcp 65001 >nul
set SRC=%~dp0daily-report-pkg
set DST=C:\Users\Mitra\Desktop\Tekarai
echo Copying DailyReportPage...
copy /Y "%SRC%\frontend-web\src\pages\DailyReportPage.tsx" "%DST%\frontend-web\src\pages\DailyReportPage.tsx"
if %errorlevel% NEQ 0 echo FAIL copy page & pause & exit /b 1
echo Copying navigation...
copy /Y "%SRC%\frontend-web\src\app\configuration\navigation.ts" "%DST%\frontend-web\src\app\configuration\navigation.ts"
if %errorlevel% NEQ 0 echo FAIL copy nav & pause & exit /b 1
echo Patching AppRouter...
powershell -Command "(Get-Content '%DST%\frontend-web\src\app\router\AppRouter.tsx') -replace 'const ProductionPlanningDashboardPage = named', 'const DailyReportPage = named(() => import(\"../../pages/DailyReportPage\"), \"DailyReportPage\");`nconst ProductionPlanningDashboardPage = named' | Set-Content '%DST%\frontend-web\src\app\router\AppRouter.tsx'"
powershell -Command "(Get-Content '%DST%\frontend-web\src\app\router\AppRouter.tsx') -replace '        <Route path=\"production/planning\" element={<ProductionPlanningDashboardPage />} />', '        <Route path=\"daily-report\" element={<DailyReportPage />} />`n        <Route path=\"production/planning\" element={<ProductionPlanningDashboardPage />} />' | Set-Content '%DST%\frontend-web\src\app\router\AppRouter.tsx'"
echo DONE - files copied, router patched
echo Now run: cd /d "%DST%\frontend-web" && npm run build
pause
