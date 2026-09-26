@echo off
chcp 65001 >nul
rem ============================================================================
rem  Tekarai - اجرای کل برنامه (بک‌اند + فرانت) بدون درگیری با Execution Policy
rem
rem      run_dev.cmd                 -> مثل run_dev.ps1 (SQL Server / SQL Express)
rem      run_dev.cmd -UseSqlite      -> بدون SQL Server، روی SQLite محلی
rem      run_dev.cmd -DemoMode       -> فقط رابط کاربری، بدون بک‌اند
rem
rem  این فایل ابتدا قفل «فایل دانلود شده از اینترنت» را از اسکریپت‌های .ps1
rem  برمی‌دارد و بعد run_dev.ps1 را با دور زدن Execution Policy اجرا می‌کند.
rem ============================================================================
setlocal
cd /d "%~dp0"

echo == آزادسازی اسکریپت‌های PowerShell (یک‌بار) ==
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Filter *.ps1 -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"

echo == اجرای run_dev.ps1 ==
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_dev.ps1" %*
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
  echo.
  echo اجرا با کد %RESULT% پایان یافت. اگر خطای پایگاه داده بود، اول این را اجرا کنید:
  echo     fix_login.cmd
  echo.
  pause
)
exit /b %RESULT%
