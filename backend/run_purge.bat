@echo off
chcp 65001 >nul
echo ============================================
echo  Purge Test Data - Tekarai / Ronak
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
    echo [ERROR] Backend not found at %BACKEND%
    set /p PROJECT="Drag Tekarai folder path: "
)
echo.
echo [1/3] Making DB backup...
set "BACKUP=C:\ProgramData\Tekarai\Backups"
if not exist "%BACKUP%" mkdir "%BACKUP%" >nul 2>&1
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
set stamp=%dt:~0,8%-%dt:~8,6%
echo   Backup folder: %BACKUP%
echo   Please backup your SQL Server DB manually (SSMS) before continue!
echo   Press any key after backup is done...
pause >nul

echo.
echo [2/3] Dry-run preview...
cd /d "%BACKEND%"
.venv\Scripts\python.exe "%~dp0purge_test_data.py"
echo.
echo --------------------------------------------
echo If preview looks OK, run the REAL purge:
echo   .venv\Scripts\python.exe purge_test_data.py --execute
echo --------------------------------------------
pause
