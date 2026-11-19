@echo off
chcp 65001 >nul
echo Purging production DB v2...
sqlcmd -S localhost\SQLEXPRESS -E -d Tekarai -i "%~dp0purge_production_simple2.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE. Refresh site.
pause
