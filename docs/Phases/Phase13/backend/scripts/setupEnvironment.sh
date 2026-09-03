#!/usr/bin/env bash
# ============================================================================
# Tekarai Backend — Environment Setup (Linux/macOS, Phase 01 §21)
# Usage:  bash scripts/setupEnvironment.sh     (from the backend/ directory)
# ============================================================================
set -euo pipefail

if [ ! -f "manage.py" ]; then
    echo "Run this script from the backend/ directory." >&2
    exit 1
fi

# 1. Virtual environment (Python 3.12 baseline)
if [ ! -d "venv" ]; then
    python3.12 -m venv venv 2>/dev/null || python3 -m venv venv
fi

# 2. Activate + upgrade packaging tools
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip

# 3. Install categorized dependencies
python -m pip install -r requirements/development.txt

# 4. Local environment file (never committed)
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from template. Fill in local values."
fi

# 5. Verify the Python executable comes from the virtual environment
python --version
python -m pip --version
echo "Setup complete. Verify with: bash scripts/verifyQuality.sh"
