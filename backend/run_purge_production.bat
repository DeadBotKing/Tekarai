@echo off
chcp 65001 >nul
echo ============================================
echo  PURGE PRODUCTION DB - Tekarai on SQLEXPRESS
echo ============================================
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo [ERROR] Right-click - Run as administrator!
    pause
    exit /b 1
)
echo Backups exists at: C:\ProgramData\Tekarai\Backups\Tekarai-2025-11-18.bak
echo.
echo This will DELETE all test users from the REAL site DB!
echo Only platform-admin will remain.
echo.
set /p confirm="Type YES to continue: "
if /I not "%confirm%"=="YES" (
    echo Cancelled.
    pause
    exit /b 0
)
echo.
echo Running purge on localhost\SQLEXPRESS - Tekarai ...
sqlcmd -S localhost\SQLEXPRESS -E -d Tekarai -i "%~dp0purge_production.sql"
if %errorlevel% NEQ 0 (
    echo [ERROR] Purge failed. Check messages above.
    pause
    exit /b 1
)
echo.
echo ============================================
echo DONE. Refresh https://tekarai/app/administration/users
echo Only platform-admin should remain. Press any key...
pause >nul
