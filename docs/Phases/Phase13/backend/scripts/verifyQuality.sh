#!/usr/bin/env bash
# ============================================================================
# Tekarai Backend — Quality Gate (Linux/macOS, Phase 01 §11/§22)
# Green gate = Definition of Done requirement.
# ============================================================================
set -euo pipefail

if [ ! -f "manage.py" ]; then
    echo "Run this script from the backend/ directory." >&2
    exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "== manage.py check =="
python manage.py check --settings=config.settings.testing

echo "== makemigrations --check =="
python manage.py makemigrations --check --settings=config.settings.testing

echo "== tests =="
python manage.py test --settings=config.settings.testing

echo "== ruff check =="
ruff check .

echo "== ruff format --check =="
ruff format --check .

echo "== mypy =="
mypy config apps tests

echo "QUALITY GATE: GREEN"
