# Phase 13-Z reproducible release gate. Run from backend/.
$ErrorActionPreference = "Stop"
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$Settings = if ($env:DJANGO_SETTINGS_MODULE) { $env:DJANGO_SETTINGS_MODULE } else { "config.settings.production" }

& $Python manage.py check --deploy --settings=$Settings
& $Python manage.py migrate --plan --settings=$Settings
& $Python manage.py makemigrations --check --settings=$Settings
& $Python manage.py checkPhase13Release --settings=$Settings
& $Python manage.py test tests.unit tests.application tests.integration --settings=config.settings.testing
ruff check apps/ai tests config
ruff format --check apps/ai tests config
mypy apps/ai config
Write-Output "GATE_Z=GREEN"
