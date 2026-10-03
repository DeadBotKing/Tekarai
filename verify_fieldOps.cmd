@echo off
chcp 65001 >nul
rem ============================================================================
rem  Tekarai - بررسی قابلیت‌های کار میدانی بدون درگیری با Execution Policy
rem
rem      verify_fieldOps.cmd              -> تست‌های بک‌اند همین قابلیت (۹۰ تست)
rem      verify_fieldOps.cmd -Frontend    -> typecheck و تست و build فرانت‌اند
rem      verify_fieldOps.cmd -Full        -> کل مجموعه تست بک‌اند
rem      verify_fieldOps.cmd -Smoke       -> تست زندهٔ API (بک‌اند باید بالا باشد)
rem      verify_fieldOps.cmd -All         -> همهٔ موارد بالا
rem ============================================================================
setlocal
cd /d "%~dp0"

echo == آزادسازی اسکریپت‌های PowerShell (یک‌بار) ==
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Filter *.ps1 -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"

echo == اجرای verify_fieldOps.ps1 ==
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_fieldOps.ps1" %*
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
  echo.
  echo بررسی با کد %RESULT% پایان یافت. متن قرمزِ بالا علت را نشان می‌دهد.
  echo.
  pause
)
exit /b %RESULT%
