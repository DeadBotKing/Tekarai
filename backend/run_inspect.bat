@echo off
chcp 65001 >nul
cd /d C:\Users\Mitra\Desktop\Tekarai\backend
.venv\Scripts\python.exe "%~dp0inspect_TekaraiLive.py"
pause
