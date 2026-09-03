# ============================================================================
# Tekarai Backend — Environment Setup (Windows PowerShell, Phase 01 §21)
# Usage:  .\scripts\setupEnvironment.ps1     (from the backend/ directory)
# ============================================================================
$ErrorActionPreference = "Stop"

if (-not (Test-Path "manage.py")) {
    Write-Error "Run this script from the backend/ directory."
    exit 1
}

# 1. Virtual environment (Python 3.12 baseline)
if (-not (Test-Path "venv")) {
    py -3.12 -m venv venv
}

# 2. Activate + upgrade packaging tools
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# 3. Install categorized dependencies (dev set includes testing + quality tools)
python -m pip install -r requirements\development.txt

# 4. Local environment file (never committed)
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from template. Fill in local values."
}

# 5. Verify the Python executable comes from the virtual environment
python --version
python -m pip --version
Write-Host "Setup complete. Verify with: .\scripts\verifyQuality.ps1"
