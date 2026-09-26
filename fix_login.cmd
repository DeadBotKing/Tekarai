@echo off
chcp 65001 >nul
rem ============================================================================
rem  Tekarai - رفع خطای ورود «Unexpected server error»
rem
rem  این فایل .cmd است، نه .ps1 — پس سیاست اجرای اسکریپت ویندوز
rem  (Execution Policy) جلوی آن را نمی‌گیرد. کافی است روی آن دوبار کلیک کنید
rem  یا در PowerShell بنویسید:   .\fix_login.cmd
rem
rem  کاری که می‌کند: محیط مجازی را پیدا (یا می‌سازد)، وابستگی‌ها را نصب می‌کند،
rem  جدول‌های پایگاه داده را می‌سازد، کاربر مدیر را ایجاد می‌کند و در پایان
rem  یک درخواست ورود واقعی می‌زند تا مطمئن شویم مشکل حل شده است.
rem ============================================================================
setlocal
cd /d "%~dp0"

echo.
echo == Tekarai: عیب‌یابی و رفع خطای ورود ==
echo.

set "PYEXE="
if exist "backend\venv\Scripts\python.exe"  (set "PYEXE=backend\venv\Scripts\python.exe"  & goto :havePython)
if exist "backend\.venv\Scripts\python.exe" (set "PYEXE=backend\.venv\Scripts\python.exe" & goto :havePython)
if exist "venv\Scripts\python.exe"          (set "PYEXE=venv\Scripts\python.exe"          & goto :havePython)
if exist ".venv\Scripts\python.exe"         (set "PYEXE=.venv\Scripts\python.exe"         & goto :havePython)

echo [1/3] محیط مجازی پیدا نشد؛ ساخت backend\.venv ...
python -m venv backend\.venv
if errorlevel 1 goto :noPython
set "PYEXE=backend\.venv\Scripts\python.exe"
"%PYEXE%" -m pip install --upgrade pip

:havePython
echo [1/3] Python: %PYEXE%
"%PYEXE%" --version

echo.
echo [2/3] بررسی نصب بودن جنگو ...
"%PYEXE%" -c "import django" 2>nul
if errorlevel 1 (
  echo       نصب وابستگی‌های بک‌اند - این مرحله چند دقیقه طول می‌کشد ...
  "%PYEXE%" -m pip install -r backend\requirements\development.txt
)

echo.
echo [3/3] اجرای عیب‌یاب ...
echo.
set "PLATFORM_ADMIN_PASSWORD=Tekarai-Demo-2026!"
set "dbEngine=sqlite"
"%PYEXE%" backend\scripts\doctorLogin.py --fix --sqlite
set "RESULT=%ERRORLEVEL%"

echo.
if "%RESULT%"=="0" (
  echo ============================================================
  echo  ورود سالم است. حالا برنامه را با این دستور بالا بیاورید:
  echo      run_dev.cmd -UseSqlite
  echo  و با این اطلاعات وارد شوید:
  echo      Tenant code : platform
  echo      Username    : platform-admin
  echo      Password    : Tekarai-Demo-2026!
  echo ============================================================
) else (
  echo ============================================================
  echo  هنوز مشکل باقی است - کد خروج %RESULT%
  echo    2 = وابستگی‌های پایتون نصب نشد
  echo    3 = پایگاه داده در دسترس نیست
  echo    4 = جدول‌ها ساخته نشدند
  echo    5 = ورود شکست خورد - متن استثنای واقعی بالا چاپ شده است
  echo  متن بالا را برای بررسی بفرستید.
  echo ============================================================
)
goto :end

:noPython
echo.
echo خطا: پایتون روی سیستم پیدا نشد. ابتدا Python 3.12+ را نصب کنید
echo و هنگام نصب گزینهٔ "Add python.exe to PATH" را تیک بزنید.
set "RESULT=1"

:end
echo.
pause
exit /b %RESULT%
