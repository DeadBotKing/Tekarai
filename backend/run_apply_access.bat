@echo off
chcp 65001 >nul
echo Applying RBAC to TekaraiLive...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0apply_access.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE - check counts above
pause
