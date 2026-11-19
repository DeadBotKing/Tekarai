@echo off
chcp 65001 >nul
echo ============================================
echo  Import 44 Engineering Staff - Tekarai
echo ============================================
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo [ERROR] Right-click - Run as administrator!
    pause
    exit /b 1
)
set "PROJECT=%USERPROFILE%\Desktop\Tekarai"
set "BACKEND=%PROJECT%\backend"
if not exist "%BACKEND%\manage.py" (
    echo [ERROR] Backend not found
    pause
    exit /b 1
)
cd /d "%BACKEND%"
echo [1/2] Preview...
.venv\Scripts\python.exe "%~dp0bulk_import_engineering.py"
echo.
echo --------------------------------------------
echo If preview is OK, run:
echo   .venv\Scripts\python.exe bulk_import_engineering.py --execute
echo --------------------------------------------
pause
