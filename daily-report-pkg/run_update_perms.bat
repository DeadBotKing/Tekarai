@echo off
chcp 65001 >nul
echo Updating perms for daily report...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0backend\update_perms_phase2.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE
pause
