#!/usr/bin/env bash
# =============================================================================
# Tekarai — run the WHOLE platform (backend + frontend) with ONE command.
# Linux / macOS. (Windows users: use run_dev.ps1)
#
#   ./run_dev.sh
#
# Defaults to SQLite (offline). To use SQL Server, set env vars before running:
#   export dbEngine=mssql dbName=Tekarai dbHost=localhost dbPort=1433 \
#          dbUser=sa dbPassword='...'
# The script creates the database if missing, seeds the platform admin and
# starts both servers. Open http://localhost:4173
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-4173}"
PY="${PYTHON:-python3}"
ADMIN_PASSWORD="${PLATFORM_ADMIN_PASSWORD:-Tekarai-Demo-2026!}"
TENANT_CODE="${PLATFORM_TENANT_CODE:-platform}"

echo "== Tekarai: starting backend + frontend together =="

# --- backend virtualenv (one time) -------------------------------------------
if [ ! -x backend/.venv/bin/python ]; then
  echo ">> creating backend/.venv (one time) ..."
  "$PY" -m venv backend/.venv
  backend/.venv/bin/python -m pip install -q --upgrade pip
fi
backend/.venv/bin/python -m pip install -q -r backend/requirements/development.txt

ENGINE="${dbEngine:-sqlite}"
if [ "$ENGINE" = "mssql" ]; then
  backend/.venv/bin/python -m pip install -q "mssql-django==1.8.0" "pyodbc==5.3.0"
  export dbEngine=mssql
  export dbName="${dbName:-Tekarai}"
  export dbUser="${dbUser:-}"
  export dbPassword="${dbPassword:-}"
  export dbServer="${dbServer:-${dbHost:-localhost}}"
  export dbHost="$dbServer"
  export dbPort="${dbPort:-}"
  export dbEncrypt="${dbEncrypt:-false}"
  export dbExtraParams="${dbExtraParams:-TrustServerCertificate=yes;Encrypt=no}"
  echo ">> ensuring database '$dbName' exists ..."
  (cd backend && ./.venv/bin/python scripts/ensureDatabase.py)
fi

# --- frontend dependencies (one time) ----------------------------------------
if [ ! -d frontend-web/node_modules ]; then
  echo ">> installing frontend dependencies (one time) ..."
  (cd frontend-web && npm ci)
fi

# --- frontend runtime config --------------------------------------------------
DEMO_FLAG="${VITE_DEMO_MODE:-false}"
cat > frontend-web/.env <<EOF
VITE_API_BASE_URL=
VITE_API_VERSION=v1
VITE_DEMO_MODE=$DEMO_FLAG
VITE_APP_NAME=Tekarai
VITE_REALTIME_ENABLED=false
EOF
echo ">> frontend-web/.env written (demoMode=$DEMO_FLAG)"

# --- migrate + seed -----------------------------------------------------------
export PLATFORM_TENANT_CODE="$TENANT_CODE"
export PLATFORM_ADMIN_USERNAME="${PLATFORM_ADMIN_USERNAME:-platform-admin}"
export PLATFORM_ADMIN_PASSWORD="$ADMIN_PASSWORD"
export PLATFORM_ADMIN_EMAIL="${PLATFORM_ADMIN_EMAIL:-platform-admin@tekarai.local}"

echo ">> applying database migrations ..."
(cd backend && ./.venv/bin/python manage.py migrate --noinput --settings=config.settings.development)
echo ">> seeding platform admin (idempotent) ..."
(cd backend && ./.venv/bin/python manage.py bootstrapPlatform --settings=config.settings.development)

# --- cleanup ------------------------------------------------------------------
cleanup() {
  echo ">> stopping Tekarai ..."
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- start both ----------------------------------------------------------------
echo ">> backend  -> http://127.0.0.1:${BACKEND_PORT} (reached through the frontend proxy)"
(cd backend && ./.venv/bin/python manage.py runserver "127.0.0.1:${BACKEND_PORT}" --settings=config.settings.development) &
BACKEND_PID=$!

echo ">> frontend -> http://localhost:${FRONTEND_PORT}  (single entry point)"
(cd frontend-web && npm run dev) &
FRONTEND_PID=$!

echo ">> Tekarai is up."
echo "   Open:  http://localhost:${FRONTEND_PORT}"
echo "   Tenant code: ${TENANT_CODE}   Username: ${PLATFORM_ADMIN_USERNAME:-platform-admin}   Password: ${ADMIN_PASSWORD}"
echo ">> Press Ctrl+C to stop everything."

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
echo ">> one of the services stopped; shutting the other down."
cleanup
