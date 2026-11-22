@echo off
chcp 65001 >nul
echo Fixing all role Persian names...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -f 65001 -i "%~dp0fix_all_roles.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE
pause
