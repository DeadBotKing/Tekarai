@echo off
chcp 65001 >nul
echo Checking Amene Sadeghi (09365614779)...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0fix_amene.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE
pause
