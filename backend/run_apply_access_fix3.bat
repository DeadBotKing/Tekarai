@echo off
chcp 65001 >nul
echo Applying RBAC fix3...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0apply_access_fix3.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE
pause
