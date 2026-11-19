@echo off
chcp 65001 >nul
echo Purging production DB (simple)...
sqlcmd -S localhost\SQLEXPRESS -E -d Tekarai -i "%~dp0purge_production_simple.sql"
if %errorlevel% NEQ 0 echo ERROR & pause & exit /b 1
echo DONE. Refresh site.
pause
