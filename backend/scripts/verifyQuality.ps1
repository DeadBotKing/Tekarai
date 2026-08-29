# ============================================================================
# Tekarai Backend — Quality Gate (Windows PowerShell, Phase 01 §11/§22)
# Green gate = Definition of Done requirement.
# ============================================================================
$ErrorActionPreference = "Stop"
if (-not (Test-Path "manage.py")) {
    Write-Error "Run this script from the backend/ directory."
    exit 1
}
.\venv\Scripts\Activate.ps1

Write-Host "== manage.py check =="
python manage.py check --settings=config.settings.testing

Write-Host "== makemigrations --check =="
python manage.py makemigrations --check --settings=config.settings.testing

Write-Host "== tests =="
python manage.py test --settings=config.settings.testing

Write-Host "== ruff check =="
ruff check .

Write-Host "== ruff format --check =="
ruff format --check .

Write-Host "== mypy =="
mypy config apps tests

Write-Host "QUALITY GATE: GREEN"
