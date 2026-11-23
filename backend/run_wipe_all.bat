@echo off
chcp 65001 >nul
echo ============================================
echo  WIPE ALL DEMO DATA - DESTRUCTIVE!
echo  This deletes: Planning demo, Equipment, Buildings, Placements, WorkOrders, Procurement
echo  Keeps: Users/Roles/Departments
echo  Backup was: C:\TekaraiBackup\TekaraiLive_20261123_171103.bak
echo ============================================
set /p ok="Type YES to continue: "
if /I not "%ok%"=="YES" echo Cancelled & pause & exit /b 1
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0wipe_all_demo_complete.sql"
if %errorlevel% NEQ 0 echo FAILED & pause & exit /b 1
echo DONE
echo Next: iisreset
pause
