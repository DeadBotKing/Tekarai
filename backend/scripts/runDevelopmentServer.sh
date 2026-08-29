#!/usr/bin/env bash
# Start the development server (Linux/macOS, Phase 01 §21)
set -euo pipefail
if [ ! -f "manage.py" ]; then echo "Run from backend/." >&2; exit 1; fi
# shellcheck disable=SC1091
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000
