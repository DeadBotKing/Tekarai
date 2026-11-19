@echo off
chcp 65001 >nul
echo Purging TekaraiLive (real site)...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0purge_TekaraiLive.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE.
pause
