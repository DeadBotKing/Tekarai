@echo off
chcp 65001 >nul
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0fix_roles_names.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE - role names fixed
pause
