@echo off
chcp 65001 >nul
echo Restoring AppRouter...
copy /Y "%~dp0AppRouter_fixed_for_zip.tsx" "C:\Users\Mitra\Desktop\Tekarai\frontend-web\src\app\router\AppRouter.tsx"
if %errorlevel% NEQ 0 echo FAIL & pause & exit /b 1
echo DONE - now rebuild
pause
