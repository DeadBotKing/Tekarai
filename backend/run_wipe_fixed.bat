@echo off
chcp 65001 >nul
echo ============================================
echo  WIPE ALL DEMO DATA - FIXED QUOTED_IDENTIFIER
echo ============================================
set /p ok="Type YES to continue: "
if /I not "%ok%"=="YES" echo Cancelled & pause & exit /b 1
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i "%~dp0wipe_all_demo_complete_fixed.sql"
if %errorlevel% NEQ 0 echo FAILED & pause & exit /b 1
echo DONE
pause
