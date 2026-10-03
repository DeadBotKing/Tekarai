@echo off
chcp 65001 >nul
rem ============================================================================
rem  Tekarai - بررسی قابلیت «ثبت قرائت دستی و سنسوری» بدون درگیری با Execution Policy
rem
rem      verify_meterReadings.cmd              -> تست‌های بک‌اند همین قابلیت (۹۱ تست)
rem      verify_meterReadings.cmd -Frontend    -> typecheck و تست و build فرانت‌اند
rem      verify_meterReadings.cmd -Full        -> کل مجموعه تست بک‌اند
rem      verify_meterReadings.cmd -Smoke       -> تست زندهٔ API (بک‌اند باید بالا باشد)
rem      verify_meterReadings.cmd -All         -> همهٔ موارد بالا
rem ============================================================================
setlocal
cd /d "%~dp0"

echo == آزادسازی اسکریپت‌های PowerShell (یک‌بار) ==
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Filter *.ps1 -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"

echo == اجرای verify_meterReadings.ps1 ==
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_meterReadings.ps1" %*
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
  echo.
  echo بررسی با کد %RESULT% پایان یافت. متن قرمزِ بالا علت را نشان می‌دهد.
  echo.
  pause
)
exit /b %RESULT%
