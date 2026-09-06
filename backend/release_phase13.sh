#!/usr/bin/env bash
# Phase 13-Z reproducible release gate. Run from backend/.
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-python}"
SETTINGS="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

"$PYTHON_BIN" manage.py check --deploy --settings="$SETTINGS"
"$PYTHON_BIN" manage.py migrate --plan --settings="$SETTINGS"
"$PYTHON_BIN" manage.py makemigrations --check --settings="$SETTINGS"
"$PYTHON_BIN" manage.py checkPhase13Release --settings="$SETTINGS"
"$PYTHON_BIN" manage.py test tests.unit tests.application tests.integration --settings=config.settings.testing
ruff check apps/ai tests config
ruff format --check apps/ai tests config
mypy apps/ai config

echo "GATE_Z=GREEN"
