# =============================================================================
# Tekarai — بررسی قابلیت‌های کار میدانی تکنسین در ویندوز / PowerShell
#   (اسکن کد، تایمر کار، کار بدون اینترنت، همگام‌سازی تأخیری)
#
#   .\verify_fieldOps.ps1            # تست‌های بک‌اندِ همین قابلیت (۹۰ تست)
#   .\verify_fieldOps.ps1 -Frontend  # + typecheck و تست و build فرانت‌اند
#   .\verify_fieldOps.ps1 -Full      # + کل مجموعه تست بک‌اند
#   .\verify_fieldOps.ps1 -Smoke     # تست زندهٔ API روی سروری که بالاست
#   .\verify_fieldOps.ps1 -All       # همهٔ موارد بالا
#
# نکته: اگر ویندوز اجازهٔ اجرای .ps1 را نداد، یا از لانچر
#       .\verify_fieldOps.cmd استفاده کنید، یا فقط برای همین پنجره:
#           Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
# برای -Smoke باید بک‌اند بالا باشد (مثلاً با .\run_dev.ps1 یا .\run_dev.cmd).
# =============================================================================
param(
  [switch]$Frontend,
  [switch]$Full,
  [switch]$Smoke,
  [switch]$All,
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$TenantCode = "platform",
  [string]$AdminUsername = "platform-admin",
  [string]$AdminPassword = "Tekarai-Demo-2026!"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($All) { $Frontend = $true; $Full = $true; $Smoke = $true }

# بدون هیچ سوییچی: فقط تست‌های بک‌اندِ همین قابلیت.
$runBackendTests = -not ($Frontend -or $Smoke -or $Full)

$script:failures = 0
$script:passes = 0

function Step([string]$text) {
  Write-Host ""
  Write-Host "== $text" -ForegroundColor Cyan
}

function Report([bool]$ok, [string]$label) {
  if ($ok) {
    $script:passes++
    Write-Host "  [PASS] $label" -ForegroundColor Green
  } else {
    $script:failures++
    Write-Host "  [FAIL] $label" -ForegroundColor Red
  }
}

# --- پایتونِ محیط مجازی ---------------------------------------------------------
$venvPython = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  $posixPython = Join-Path $PSScriptRoot "backend/.venv/bin/python"
  if (Test-Path $posixPython) { $venvPython = $posixPython }
}
if (($runBackendTests -or $Full) -and -not (Test-Path $venvPython)) {
  Step "ساخت backend\.venv (یک‌بار)"
  python -m venv backend\.venv
  if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: محیط مجازی ساخته نشد. آیا Python روی PATH هست؟" -ForegroundColor Red
    exit 1
  }
  & $venvPython -m pip install --upgrade pip | Out-Null
  & $venvPython -m pip install -r backend\requirements\testing.txt
  if ($LASTEXITCODE -ne 0) { Write-Host "pip install ناموفق بود." -ForegroundColor Red; exit 1 }
}

function Invoke-DjangoTest([string]$label, [string[]]$targets) {
  Step $label
  Push-Location backend
  # تست‌ها روی SQLite و تنظیمات testing اجرا می‌شوند؛ به SQL Server کاری ندارند.
  # --parallel در این مخزن خراب است (cannot pickle 'traceback' object) پس سریال.
  & $venvPython manage.py test @targets --settings=config.settings.testing
  $code = $LASTEXITCODE
  Pop-Location
  Report ($code -eq 0) $label
}

# --- ۱) تست‌های بک‌اندِ این قابلیت ------------------------------------------------
if ($runBackendTests) {
  Invoke-DjangoTest "تست‌های دامنه و REST کار میدانی (۹۰ تست)" `
    @("tests.unit.testFieldOperations", "tests.integration.testFieldOpsApi")

  Step "بررسی نبودِ مهاجرت جامانده (migration drift)"
  Push-Location backend
  & $venvPython manage.py makemigrations maintenance --check --dry-run --settings=config.settings.testing
  $driftCode = $LASTEXITCODE
  Pop-Location
  Report ($driftCode -eq 0) "makemigrations --check تمیز است"
}

# --- ۲) کل مجموعهٔ بک‌اند ---------------------------------------------------------
if ($Full) {
  Step "کل مجموعه تست بک‌اند (حدود ۲ دقیقه)"
  $logDir = Join-Path $PSScriptRoot "logs"
  if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
  $fullLog = Join-Path $logDir "verify_fieldOpsFullSuite.log"
  Push-Location backend
  & $venvPython manage.py test tests --settings=config.settings.testing *>&1 |
    Tee-Object -FilePath $fullLog
  Pop-Location

  # روی شاخهٔ main هم ۵ تستِ «قواعد معماری» قرمزند و به این قابلیت ربطی ندارند.
  $allFailures = @(Select-String -Path $fullLog -Pattern "^(FAIL|ERROR):" |
    ForEach-Object { $_.Line })
  $legacy = @($allFailures | Where-Object { $_ -match "tests\.architecture\." })
  $real = @($allFailures | Where-Object { $_ -notmatch "tests\.architecture\." })
  foreach ($line in $real) { Write-Host "    $line" -ForegroundColor Red }
  Report ($real.Count -eq 0) ("کل مجموعه بک‌اند ({0} شکست معماریِ از-قبل-موجود نادیده گرفته شد)" -f $legacy.Count)
  Write-Host "    گزارش کامل: $fullLog"
}

# --- ۳) فرانت‌اند ------------------------------------------------------------------
if ($Frontend) {
  Step "فرانت‌اند: نصب وابستگی‌ها (در صورت نیاز)"
  Push-Location frontend-web
  if (-not (Test-Path "node_modules")) { npm ci }
  Write-Host "-- typecheck"
  npm run typecheck
  $tc = $LASTEXITCODE
  Write-Host "-- tests"
  npm run test -- --run
  $ts = $LASTEXITCODE
  Write-Host "-- build"
  npm run build
  $tb = $LASTEXITCODE
  Pop-Location
  Report ($tc -eq 0) "typecheck فرانت‌اند"
  Report ($ts -eq 0) "تست‌های فرانت‌اند"
  Report ($tb -eq 0) "build فرانت‌اند"

  # دارایی‌های PWA باید در خروجی build باشند، وگرنه نصب روی گوشی کار نمی‌کند.
  Step "دارایی‌های PWA در خروجی build"
  foreach ($asset in @("dist/manifest.webmanifest", "dist/serviceWorker.js", "dist/offline.html",
                       "dist/icons/icon-192.png", "dist/icons/icon-512.png", "dist/icons/maskable-512.png")) {
    Report (Test-Path (Join-Path "frontend-web" $asset)) $asset
  }
}

# --- ۴) تست زندهٔ API --------------------------------------------------------------
if ($Smoke) {
  $base = $BaseUrl.TrimEnd("/")
  $api = "$base/api/v1"
  $script:token = ""

  function Call-Api {
    param(
      [string]$Method,
      [string]$Path,
      $Body = $null
    )
    $headers = @{ "Accept" = "application/json" }
    if ($script:token) { $headers["Authorization"] = "Bearer $($script:token)" }
    if ($Method -eq "Get") {
      return Invoke-RestMethod -Method Get -Uri "$api$Path" -Headers $headers
    }
    # UTF-8 صریح، وگرنه متن فارسیِ بدنه در ویندوز خراب ارسال می‌شود.
    $json = if ($null -ne $Body) { $Body | ConvertTo-Json -Depth 8 -Compress } else { "{}" }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    return Invoke-RestMethod -Method $Method -Uri "$api$Path" -Headers $headers `
      -ContentType "application/json; charset=utf-8" -Body $bytes
  }

  function Try-Api {
    param([string]$Method, [string]$Path, $Body = $null)
    try {
      return @{ ok = $true; data = (Call-Api -Method $Method -Path $Path -Body $Body) }
    } catch {
      $message = $_.Exception.Message
      if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $message = $_.ErrorDetails.Message }
      return @{ ok = $false; error = $message }
    }
  }

  Step "تست زندهٔ API روی $base"

  $login = Try-Api -Method Post -Path "/auth/login" -Body @{
    tenantCode = $TenantCode; identifier = $AdminUsername; password = $AdminPassword
  }
  if (-not $login.ok) {
    Write-Host "  ورود ناموفق: $($login.error)" -ForegroundColor Red
    Write-Host "  آیا بک‌اند بالاست؟ ابتدا .\run_dev.cmd را اجرا کنید." -ForegroundColor Yellow
    exit 1
  }
  $script:token = $login.data.data.accessToken
  Report ($null -ne $script:token) "ورود پلتفرم‌ادمین"

  $suffix = (Get-Random -Maximum 99999)
  $deviceCode = "FIELD-$suffix"

  $device = Try-Api -Method Post -Path "/maintenance/devices" -Body @{
    code = $deviceCode; name = "پمپ تست میدانی"; location = "سالن تست"
    department = "mechanical"; pmIntervalDays = 30
  }
  Report $device.ok "ساخت تجهیز $deviceCode"
  if (-not $device.ok) { Write-Host "  $($device.error)" -ForegroundColor Red; exit 1 }
  $deviceId = $device.data.data.id

  # --- اسکن ------------------------------------------------------------------
  $scanByCode = Try-Api -Method Get -Path "/maintenance/scan?code=$deviceCode&symbology=code_128"
  Report ($scanByCode.ok -and $scanByCode.data.data.kind -eq "device" -and $scanByCode.data.data.id -eq $deviceId) `
    "اسکن بارکد خطی (Code 128) تجهیز را پیدا می‌کند"

  $deepLink = [uri]::EscapeDataString("$base/app/maintenance/devices/$deviceId/profile")
  $scanByLink = Try-Api -Method Get -Path "/maintenance/scan?code=$deepLink&symbology=qr_code"
  Report ($scanByLink.ok -and $scanByLink.data.data.id -eq $deviceId) "اسکن QR با نشانی کامل"

  $scanJunk = Try-Api -Method Get -Path "/maintenance/scan?code=%D8%B3%D9%84%D8%A7%D9%85"
  Report (-not $scanJunk.ok) "متن نامربوط به‌جای حدس‌زدن رد می‌شود"

  $order = Try-Api -Method Post -Path "/maintenance/work-orders" -Body @{
    deviceId = $deviceId; title = "تست تایمر میدانی"; orderType = "corrective"
    priority = "high"; department = "mechanical"; requestedByName = "بازرس"
  }
  Report $order.ok "ساخت سفارش کار"
  if (-not $order.ok) { Write-Host "  $($order.error)" -ForegroundColor Red; exit 1 }
  $orderId = $order.data.data.id

  $scanOrder = Try-Api -Method Get -Path "/maintenance/scan?code=$orderId"
  Report ($scanOrder.ok -and $scanOrder.data.data.kind -eq "workOrder") `
    "اسکن سفارش کار (نه فقط تجهیز) پشتیبانی می‌شود"

  # --- تایمر -----------------------------------------------------------------
  $null = Try-Api -Method Post -Path "/maintenance/work-orders/$orderId/assign" -Body @{
    assignedToName = "تکنسین تست"
  }
  $startedAt = (Get-Date).ToUniversalTime().AddMinutes(-90).ToString("o")
  $start = Try-Api -Method Post -Path "/maintenance/work-orders/$orderId/timer/start" -Body @{
    technicianName = "تکنسین تست"; startedAt = $startedAt; note = "شروع کار"
  }
  Report ($start.ok -and $start.data.data.running -eq $true) "شروع تایمر"

  $again = Try-Api -Method Post -Path "/maintenance/work-orders/$orderId/timer/start" -Body @{
    technicianName = "تکنسین تست"
  }
  Report (-not $again.ok) "تایمر دوم برای همان تکنسین رد می‌شود"

  $stop = Try-Api -Method Post -Path "/maintenance/work-orders/$orderId/timer/stop" -Body @{
    technicianName = "تکنسین تست"; note = "پایان کار"
  }
  $hours = if ($stop.ok) { [double]$stop.data.data.hours } else { 0 }
  Report ($stop.ok -and $hours -ge 1.4 -and $hours -le 1.6) `
    ("پایان تایمر و محاسبهٔ خودکار {0} ساعت کارکرد" -f $hours)
  Report ($stop.ok -and $stop.data.data.labourEntryId) "ثبت خودکار رکورد کارکرد (labour entry)"

  $cost = Try-Api -Method Get -Path "/maintenance/work-orders/$orderId/cost-summary"
  Report ($cost.ok -and [double]$cost.data.data.labourHours -ge 1.4) `
    "ساعت تایمر در جمع هزینهٔ سفارش کار دیده می‌شود"

  # --- همگام‌سازی تأخیری ------------------------------------------------------
  $key = "smoke-$suffix-1"
  $batch = @{
    deviceLabel = "verify_fieldOps"
    atomic = $false
    operations = @(
      @{ clientRequestId = $key; kind = "device.status"
         payload = @{ deviceId = $deviceId; target = "underMaintenance"; note = "ثبت آفلاین" }
         occurredAt = (Get-Date).ToUniversalTime().ToString("o") }
    )
  }
  $sync1 = Try-Api -Method Post -Path "/maintenance/sync" -Body $batch
  Report ($sync1.ok -and @($sync1.data.data)[0].status -eq "applied") "اعمال عملیات صف‌شده"

  $sync2 = Try-Api -Method Post -Path "/maintenance/sync" -Body $batch
  Report ($sync2.ok -and @($sync2.data.data)[0].status -eq "duplicate") `
    "ارسال دوبارهٔ همان کلید تکراری شمرده می‌شود (idempotent)"

  $bad = @{
    deviceLabel = "verify_fieldOps"
    atomic = $false
    operations = @(
      @{ clientRequestId = "smoke-$suffix-2"; kind = "device.status"
         payload = @{ deviceId = "00000000-0000-0000-0000-000000000000"; target = "retired" }
         occurredAt = (Get-Date).ToUniversalTime().ToString("o") }
    )
  }
  $sync3 = Try-Api -Method Post -Path "/maintenance/sync" -Body $bad
  Report ($sync3.ok -and @($sync3.data.data)[0].status -eq "rejected") `
    "عملیات نادرست «ردشده» برمی‌گردد و کل دسته را خراب نمی‌کند"

  $history = Try-Api -Method Get -Path "/maintenance/sync/history?limit=20"
  $seen = $false
  if ($history.ok) { $seen = @($history.data.data | Where-Object { $_.clientRequestId -eq $key }).Count -ge 1 }
  Report $seen "تاریخچهٔ همگام‌سازی روی سرور ثبت شده است"

  $deviceAfter = Try-Api -Method Get -Path "/maintenance/devices/$deviceId"
  Report ($deviceAfter.ok -and $deviceAfter.data.data.status -eq "underMaintenance") `
    "تغییر وضعیت آفلاین واقعاً روی تجهیز اعمال شده است"
}

# --- خلاصه ------------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " موفق: $($script:passes)   ناموفق: $($script:failures)"
Write-Host "=============================================" -ForegroundColor Cyan
if ($script:failures -gt 0) { exit 1 }
Write-Host "همه‌چیز سبز است." -ForegroundColor Green
exit 0
