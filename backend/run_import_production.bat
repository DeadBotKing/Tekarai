@echo off
chcp 65001 >nul
echo Import 44 to PRODUCTION SQL Server
cd /d C:\Users\Mitra\Desktop\Tekarai\backend
.venv\Scripts\python.exe "%~dp0import_production_44.py" %*
if %errorlevel% NEQ 0 pause
