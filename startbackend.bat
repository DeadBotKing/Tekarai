@echo off
setlocal
set "ROOT=%USERPROFILE%\Desktop\Tekarai"
if not exist "%ROOT%\backend\manage.py" (
  echo Tekarai backend not found at "%ROOT%\backend".
  echo Extract Tekarai to your Desktop or edit ROOT in this file.
  pause
  exit /b 1
)
cd /d "%ROOT%\backend"
set dbEngine=mssql
set dbName=TekaraiLive
set dbHost=localhost\SQLEXPRESS
set dbServer=localhost\SQLEXPRESS
set dbEncrypt=false
set "dbExtraParams=TrustServerCertificate=yes;Encrypt=no"
set dbConnTimeout=30
set dbConnMaxAge=0
set ALLOWED_HOSTS=*
set CORS_ALLOWED_ORIGINS=http://localhost:4173,https://tekarai
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --settings=config.settings.development
pause
