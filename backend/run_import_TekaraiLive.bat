@echo off
chcp 65001 >nul
cd /d C:\Users\Mitra\Desktop\Tekarai\backend
.venv\Scripts\python.exe "%~dp0import_TekaraiLive.py" %*
if %errorlevel% NEQ 0 pause
