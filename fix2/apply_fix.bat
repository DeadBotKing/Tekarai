@echo off
chcp 65001 >nul
echo Applying fixes...
copy /Y "%~dp0frontend-web\src\pages\DailyReportPage.tsx" "C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\pages\DailyReportPage.tsx"
copy /Y "%~dp0frontend-web\src\app\configuration\navigation.ts" "C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\app\configuration\navigation.ts"
copy /Y "%~dp0frontend-web\src\app\router\AppRouter.tsx" "C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\app\router\AppRouter.tsx"
echo DONE
pause
