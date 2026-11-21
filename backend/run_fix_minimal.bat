@echo off
chcp 65001 >nul
echo Tightening specialist/facility perms...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0fix_minimal.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE - re-login as 09120682369 to test
pause
