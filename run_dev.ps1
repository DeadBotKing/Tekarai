# =============================================================================
# Tekarai - run the WHOLE platform (backend + frontend) with ONE command.
# Windows PowerShell + SQL Server (SQL Express).
#
#   .\run_dev.ps1
#
# Logs are written to .\logs\  (backend.log, backend.err.log, ensureDatabase.log)
# so if anything fails you see the real error instead of a window that flashes
# and closes.
#
#   Open http://localhost:4173  -  Ctrl+C stops both.
#
# Common overrides:
#   .\run_dev.ps1 -DbServer "localhost" -DbPort 1433          # default instance over TCP
#   .\run_dev.ps1 -DbUser sa -DbPassword "YourSapassword123"  # SQL authentication
#   .\run_dev.ps1 -AdminPassword "MyStrongPassw0rd!"          # your own admin password
#   .\run_dev.ps1 -UseWaitress                                # plain WSGI server (no daphne/asyncio)
#   .\run_dev.ps1 -UseSqlite                                  # fallback: offline SQLite
#   .\run_dev.ps1 -DemoMode                                   # offline demo login (no backend)
# =============================================================================
param(
  [string]$DbServer = "localhost\SQLEXPRESS",
  [string]$DbPort = "",
  [string]$DbName = "Tekarai",
  [string]$DbUser = "",
  [string]$DbPassword = "",
  [string]$AdminUsername = "platform-admin",
  [string]$AdminPassword = "Tekarai-Demo-2026!",
  [string]$TenantCode = "platform",
  [switch]$UseSqlite,
  [switch]$DemoMode,
  [switch]$UseWaitress
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$backendPort  = if ($env:BACKEND_PORT)  { $env:BACKEND_PORT }  else { "8000" }
$frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "4173" }
$venvPython = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
$logDir     = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "== Tekarai: starting backend + frontend together ==" -ForegroundColor Cyan

# --- helpers -------------------------------------------------------------------
function Clear-PortIfOurs([int]$Port, [string]$Label) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
      foreach ($c in $conns) {
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        $procName = if ($p) { $p.ProcessName } else { "unknown" }
        if ($p -and $procName -match '^(python|pythonw|python3|node)') {
          Write-Host ">> port ${Port}: stopping leftover '$procName' process (PID $($c.OwningProcess)) ..." -ForegroundColor Yellow
          Stop-Process -Id $c.OwningProcess -Force
        } else {
          Write-Host ">> port ${Port} is already in use by '$procName' (PID $($c.OwningProcess)). Close it and re-run." -ForegroundColor Red
          exit 1
        }
      }
    }
  } catch {
    # Get-NetTCPConnection unavailable on this OS - skip the check.
  }
}

# --- 1. backend virtualenv ------------------------------------------------------
if (-not (Test-Path $venvPython)) {
  Write-Host ">> creating backend\.venv (one time) ..."
  python -m venv backend\.venv
  if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: could not create the virtual environment. Is Python installed and on PATH?" -ForegroundColor Red
    exit 1
  }
  & $venvPython -m pip install --upgrade pip
}
Write-Host ">> Python: $(& $venvPython --version 2>&1)"
Write-Host ">> installing backend dependencies ..."
& $venvPython -m pip install -r backend\requirements\development.txt
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed. See output above." -ForegroundColor Red; exit 1 }

if (-not $UseSqlite) {
  Write-Host ">> installing SQL Server drivers (mssql-django + pyodbc) ..."
  & $venvPython -m pip install "mssql-django==1.8.0" "pyodbc==5.3.0"
  if ($LASTEXITCODE -ne 0) {
    Write-Host ">> pinned versions failed (often the Python version is newer than the pin)."
    Write-Host ">> retrying with latest compatible versions ..."
    & $venvPython -m pip install "mssql-django" "pyodbc"
    if ($LASTEXITCODE -ne 0) { Write-Host "mssql-django/pyodbc install failed. See output above." -ForegroundColor Red; exit 1 }
  }
}
if ($UseWaitress) {
  Write-Host ">> installing waitress (WSGI server) ..."
  & $venvPython -m pip install "waitress==3.0.2"
  if ($LASTEXITCODE -ne 0) { Write-Host "waitress install failed. See output above." -ForegroundColor Red; exit 1 }
}

# --- 2. frontend dependencies ---------------------------------------------------
# node_modules may exist but be stale after package.json/package-lock changes.
# `npm ls` catches missing direct dependencies (for example bundled fonts) and
# triggers a clean, reproducible install only when needed.
$frontendNeedsInstall = -not (Test-Path "frontend-web\node_modules")
if (-not $frontendNeedsInstall) {
  Push-Location frontend-web
  npm ls --depth=0 --silent *> $null
  $frontendNeedsInstall = $LASTEXITCODE -ne 0
  Pop-Location
}
if ($frontendNeedsInstall) {
  Write-Host ">> installing/updating frontend dependencies ..."
  Push-Location frontend-web
  npm ci
  $npmExitCode = $LASTEXITCODE
  Pop-Location
  if ($npmExitCode -ne 0) { Write-Host "npm ci failed. See output above." -ForegroundColor Red; exit 1 }
}

# --- 3. database configuration --------------------------------------------------
if ($UseSqlite) {
  $env:dbEngine = "sqlite"
  Write-Host ">> using SQLite (offline mode)" -ForegroundColor Yellow
} else {
  $env:dbEngine   = "mssql"
  $env:dbName     = $DbName
  $env:dbUser     = $DbUser
  $env:dbPassword = $DbPassword
  $env:dbServer   = $DbServer
  $env:dbHost     = $DbServer
  if ($DbPort) {
    $env:dbPort = $DbPort
  } else {
    # Windows removes env vars set to "" anyway; be explicit so the backend
    # connects to the named instance WITHOUT a port.
    Remove-Item Env:dbPort -ErrorAction SilentlyContinue
  }
  $env:dbEncrypt  = "false"
  $env:dbExtraParams = "TrustServerCertificate=yes;Encrypt=no"
  $env:dbConnTimeout = "30"
  $env:dbConnMaxAge  = "0"
  if ($DbUser) {
    Write-Host ">> SQL Server: $DbServer (SQL login '$DbUser', db '$DbName')"
  } else {
    Write-Host ">> SQL Server: $DbServer (Windows integrated auth, db '$DbName')"
  }
}

# --- 4. ensure the database exists + detect ODBC driver --------------------------
if (-not $UseSqlite) {
  Write-Host ">> ensuring database '$DbName' exists ..."
  Push-Location backend
  & $venvPython "scripts\ensureDatabase.py" *> (Join-Path $logDir "ensureDatabase.log")
  $dbExit = $LASTEXITCODE
  Pop-Location
  Get-Content (Join-Path $logDir "ensureDatabase.log") | ForEach-Object { Write-Host $_ }
  if ($dbExit -ne 0) {
    Write-Host ""
    Write-Host "Database setup failed. Common fixes:" -ForegroundColor Red
    Write-Host "  * Install 'ODBC Driver 18 for SQL Server': https://aka.ms/downloadmsodbcsql"
    Write-Host "  * Wrong instance name? Try: .\run_dev.ps1 -DbServer 'localhost' -DbPort 1433"
    Write-Host "  * SQL auth?        Try: .\run_dev.ps1 -DbUser sa -DbPassword 'YourPassword'"
    Write-Host "  * Offline fallback:     .\run_dev.ps1 -UseSqlite"
    exit 1
  }
  $driverMatch = Select-String -Path (Join-Path $logDir "ensureDatabase.log") -Pattern '^DRIVER=' | Select-Object -Last 1
  if ($driverMatch) { $env:odbcDriver = $driverMatch.Line.Substring(7) }
}

# --- 5. frontend runtime config ---------------------------------------------------
$demoFlag = if ($DemoMode) { "true" } else { "false" }
@"
VITE_API_BASE_URL=
VITE_API_VERSION=v1
VITE_DEMO_MODE=$demoFlag
VITE_APP_NAME=Tekarai
VITE_REALTIME_ENABLED=false
"@ | Set-Content -Path "frontend-web\.env" -Encoding ASCII
Write-Host ">> frontend-web\.env written (demoMode=$demoFlag)"

# --- 6. migrate + seed platform admin ---------------------------------------------
$env:PLATFORM_TENANT_CODE    = $TenantCode
$env:PLATFORM_ADMIN_USERNAME = $AdminUsername
$env:PLATFORM_ADMIN_PASSWORD = $AdminPassword
$env:PLATFORM_ADMIN_EMAIL    = "$AdminUsername@tekarai.local"

# Offline deterministic AI provider - lets "AI agent" flows run end-to-end on a
# dev machine without any external model/API key. This is a development-only
# switch; the backend NEVER enables it in production settings.
$env:aiAgentAllowDeterministicProvider = "true"

Push-Location backend
Write-Host ">> applying database migrations ..."
& $venvPython manage.py migrate --noinput --settings=config.settings.development
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  Write-Host "MIGRATE FAILED - the backend cannot start with a broken database." -ForegroundColor Red
  Write-Host "Scroll up to see the real error, or check the database settings with:" -ForegroundColor Yellow
  Write-Host "  .\run_dev.ps1 -DbServer 'localhost' -DbPort 1433    (or -UseSqlite to try offline)"
  exit 1
}
Write-Host ">> seeding platform admin (idempotent) ..."
& $venvPython manage.py bootstrapPlatform --settings=config.settings.development
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  Write-Host "BOOTSTRAP FAILED - scroll up for the error (usually database-related)." -ForegroundColor Red
  exit 1
}
Write-Host ">> seeding workspace demo data: tenants, users, projects, tasks (idempotent) ..."
& $venvPython manage.py seedWorkspace --settings=config.settings.development
if ($LASTEXITCODE -ne 0) {
  Write-Host "WORKSPACE SEED FAILED - continuing; Projects/Tasks pages will simply be empty." -ForegroundColor Yellow
}
Pop-Location

# --- 7. free the ports -------------------------------------------------------------
Clear-PortIfOurs $backendPort  "backend"
Clear-PortIfOurs $frontendPort "frontend"

# --- 8. start BOTH servers ----------------------------------------------------------
Write-Host ">> backend  -> http://127.0.0.1:$backendPort (log: logs\backend.log)"
Write-Host ">> frontend -> http://localhost:$frontendPort  (single entry point)"

$backendLog = Join-Path $logDir "backend.log"
$backendErr = Join-Path $logDir "backend.err.log"

if ($UseWaitress) {
  $waitressExe = Join-Path (Split-Path $venvPython) "waitress-serve.exe"
  $backend = Start-Process -PassThru -FilePath $waitressExe `
    -ArgumentList "--listen=127.0.0.1:$backendPort", "config.wsgi:application" `
    -WorkingDirectory (Join-Path $PSScriptRoot "backend") `
    -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr
} else {
  $backend = Start-Process -PassThru -FilePath $venvPython `
    -ArgumentList "manage.py", "runserver", "127.0.0.1:$backendPort", "--settings=config.settings.development" `
    -WorkingDirectory (Join-Path $PSScriptRoot "backend") `
    -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr
}

$frontend = Start-Process -PassThru -FilePath "npm.cmd" `
  -ArgumentList "run", "dev" `
  -WorkingDirectory (Join-Path $PSScriptRoot "frontend-web")

# --- 9. wait for the backend to actually accept requests ----------------------------
$healthy = $false
for ($i = 0; $i -lt 45; $i++) {
  try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/healthz/" -UseBasicParsing -TimeoutSec 2
    if ($resp.StatusCode -eq 200) { $healthy = $true; break }
  } catch {
    # not up yet
  }
  if (-not (Get-Process -Id $backend.Id -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Seconds 1
}

if (-not $healthy) {
  Write-Host ""
  Write-Host "BACKEND DID NOT START. Last lines of logs\backend.log:" -ForegroundColor Red
  Get-Content $backendLog -Tail 40 -ErrorAction SilentlyContinue
  Get-Content $backendErr -Tail 40 -ErrorAction SilentlyContinue
  Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
  Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
  Write-Host ""
  Write-Host "Possible fixes:" -ForegroundColor Yellow
  Write-Host "  * If the error mentions daphne / asyncio / twisted -> try:  .\run_dev.ps1 -UseWaitress"
  Write-Host "  * If the error mentions mssql / pyodbc / ODBC        -> fix the SQL Server settings above"
  Write-Host "  * Offline fallback (no database):                         .\run_dev.ps1 -UseSqlite"
  exit 1
}

Write-Host ""
Write-Host ">> Tekarai is up." -ForegroundColor Green
Write-Host "   Open:  http://localhost:$frontendPort"
Write-Host "   Tenant code: $TenantCode"
Write-Host "   Username:    $AdminUsername"
Write-Host "   Password:    $AdminPassword"
Write-Host ">> Press Ctrl+C in THIS window to stop both servers."
Write-Host ""

try {
  while ($true) {
    if (-not (Get-Process -Id $backend.Id -ErrorAction SilentlyContinue)) { break }
    if (-not (Get-Process -Id $frontend.Id -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 1
  }
} finally {
  Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
  Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
  Write-Host ">> stopped."
}
