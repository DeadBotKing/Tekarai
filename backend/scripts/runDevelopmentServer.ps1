# Start the development server (Windows PowerShell, Phase 01 §21)
$ErrorActionPreference = "Stop"
if (-not (Test-Path "manage.py")) { Write-Error "Run from backend/."; exit 1 }
.\venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000
