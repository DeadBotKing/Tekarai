# Run from the extracted package in elevated Windows PowerShell.
$ErrorActionPreference = 'Stop'
$oldLocation = Get-Location
$oldDemo = $env:VITE_DEMO_MODE
$oldAllowDemo = $env:VITE_ALLOW_DEMO_IN_PRODUCTION
$oldRealtime = $env:VITE_REALTIME_ENABLED
try {
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Open PowerShell with Run as administrator.'
    }
    $project = 'C:\Users\Mitra\Desktop\Tekarai'
    $frontend = Join-Path $project 'frontend-web'
    $target = Join-Path $frontend 'src\app\configuration\navigation.ts'
    $incoming = Join-Path $PSScriptRoot 'navigation.ts'
    $deploy = Join-Path $PSScriptRoot 'Deploy-Menu-IIS.ps1'
    foreach ($path in @($target, $incoming, $deploy)) {
        if (-not (Test-Path $path)) { throw "Required file missing: $path" }
    }
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/readyz/' -Headers @{'X-Forwarded-Proto'='https'} -UseBasicParsing -TimeoutSec 20
    if ($health.StatusCode -ne 200) { throw 'Backend is not ready. Do not start run_dev.ps1; report the error.' }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "C:\ProgramData\Tekarai\MenuBackups\$stamp"
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item $target "$backup\navigation.ts" -ErrorAction Stop
    Copy-Item $incoming $target -Force -ErrorAction Stop

    Set-Location $frontend
    $env:VITE_DEMO_MODE = 'false'
    $env:VITE_ALLOW_DEMO_IN_PRODUCTION = 'false'
    $env:VITE_REALTIME_ENABLED = 'false'
    & $npm run build
    if ($LASTEXITCODE -ne 0) {
        Copy-Item "$backup\navigation.ts" $target -Force -ErrorAction Stop
        throw 'Build failed. Previous navigation source restored; active IIS release was not switched.'
    }
    & "$env:windir\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File $deploy
    if ($LASTEXITCODE -ne 0) { throw 'IIS deployment failed. Stop and report. Do not rerun blindly.' }
    Write-Host 'MENU_UPDATE_COMPLETED'
    Write-Host "SOURCE_BACKUP: $backup\navigation.ts"
    Write-Host 'Open https://tekarai and refresh with Ctrl+Shift+R.'
    Write-Host 'No database migrations, data seeding, backend restarts, or WSL changes were performed.'
} catch {
    Write-Host 'MENU_UPDATE_NOT_CONFIRMED. Stop and report this error:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    Set-Location $oldLocation
    $env:VITE_DEMO_MODE = $oldDemo
    $env:VITE_ALLOW_DEMO_IN_PRODUCTION = $oldAllowDemo
    $env:VITE_REALTIME_ENABLED = $oldRealtime
}
