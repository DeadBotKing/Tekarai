# =============================================================================
# Tekarai — بررسی قابلیت «ثبت قرائت دستی و سنسوری» در ویندوز / PowerShell
#
#   .\verify_meterReadings.ps1            # تست‌های بک‌اندِ همین قابلیت (۹۱ تست)
#   .\verify_meterReadings.ps1 -Frontend  # + typecheck و تست و build فرانت‌اند
#   .\verify_meterReadings.ps1 -Full      # + کل مجموعه تست بک‌اند (۲۵۳۲ تست)
#   .\verify_meterReadings.ps1 -Smoke     # تست زندهٔ API روی سروری که بالاست
#   .\verify_meterReadings.ps1 -All       # همهٔ موارد بالا
#
# نکته: اگر ویندوز اجازهٔ اجرای .ps1 را نداد، یا از لانچر
#       .\verify_meterReadings.cmd استفاده کنید، یا فقط برای همین پنجره:
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

# بدون هیچ سوییچی: فقط تست‌های بک‌اندِ همین قابلیت. با سوییچ: دقیقاً همان‌ها.
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
  # اگر کسی همین اسکریپت را در PowerShell روی لینوکس/مک اجرا کند:
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
  Invoke-DjangoTest "تست‌های دامنه و REST قرائت کنتور (۹۱ تست)" `
    @("tests.unit.testMeterReading", "tests.integration.testMeterReadingApi")

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
  $fullLog = Join-Path $logDir "verify_fullSuite.log"
  Push-Location backend
  & $venvPython manage.py test tests --settings=config.settings.testing *>&1 |
    Tee-Object -FilePath $fullLog
  Pop-Location

  # روی شاخهٔ main هم ۵ تستِ «قواعد معماری» قرمزند (نام فایل/کلاس و یک import
  # بین‌حوزه‌ای در procurement). آن‌ها به این قابلیت ربطی ندارند و نادیده
  # گرفته می‌شوند؛ هر شکستِ دیگری واقعی است.
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
  $deviceCode = "SMOKE-$suffix"
  $sensorKey = "Smoke/Line1/Pump$suffix.Hours"

  $device = Try-Api -Method Post -Path "/maintenance/devices" -Body @{
    code = $deviceCode; name = "پمپ تست دود"; location = "سالن تست"
    department = "mechanical"; pmIntervalDays = 30
  }
  Report $device.ok "ساخت تجهیز $deviceCode"
  if (-not $device.ok) { Write-Host "  $($device.error)" -ForegroundColor Red; exit 1 }
  $deviceId = $device.data.data.id

  $point = Try-Api -Method Post -Path "/maintenance/devices/$deviceId/meter-points" -Body @{
    code = "RUNNING_HOURS"; name = "ساعت کارکرد"; unit = "ساعت"; kind = "cumulative"
    sensorKey = $sensorKey; drivesRunningHours = $true; rolloverMaximum = "999999"
  }
  Report $point.ok "تعریف کنتور ساعت کارکرد"
  if (-not $point.ok) { Write-Host "  $($point.error)" -ForegroundColor Red; exit 1 }

  # باگ ۲: پیش از این اصلاح، ساخت هر برنامهٔ PM خطای HTTP 500 می‌داد.
  $plan = Try-Api -Method Post -Path "/maintenance/devices/$deviceId/pm-plans" -Body @{
    title = "تعویض روغن هر ۵۰۰ ساعت"; discipline = "mechanical"
    frequencyEvery = 500; frequencyUnit = "runningHour"
    metricType = "RUNNING_HOURS"; metricUnit = "ساعت"; warningValue = "50"
  }
  Report ($plan.ok -and $plan.data.data.triggerType -eq "meter") `
    "ساخت برنامهٔ PM ساعت‌کارکردی (triggerType=meter)"

  $first = Try-Api -Method Post -Path "/maintenance/devices/$deviceId/meter-readings" -Body @{
    meterCode = "RUNNING_HOURS"; value = "8000"; note = "قرائت مبنا"
  }
  Report ($first.ok -and $first.data.data.delta -eq "") `
    "ثبت قرائت دستی (اولین قرائت delta ندارد)"

  $status = Try-Api -Method Get -Path "/maintenance/meter-pm-status?deviceId=$deviceId"
  $row = if ($status.ok) { @($status.data.data)[0] } else { $null }
  Report ($null -ne $row -and $row.status -eq "ok" -and $row.dueAtValue -eq "8500.0000") `
    "برنامه هنوز سررسید نشده و سررسیدش ۸۵۰۰ است"

  $second = Try-Api -Method Post -Path "/maintenance/devices/$deviceId/meter-readings" -Body @{
    meterCode = "RUNNING_HOURS"; value = "8505"
  }
  Report ($second.ok -and $second.data.data.delta -eq "505.0000") "محاسبهٔ مصرف بین دو قرائت"

  $status2 = Try-Api -Method Get -Path "/maintenance/meter-pm-status?deviceId=$deviceId"
  $row2 = if ($status2.ok) { @($status2.data.data)[0] } else { $null }
  # باگ ۱: پیش از این اصلاح، این برنامه هرگز سررسید نمی‌شد.
  Report ($null -ne $row2 -and $row2.status -eq "due") "برنامهٔ PM با رسیدن ساعت کارکرد سررسید شد"

  $sample = @{
    readings = @(@{ sensorKey = $sensorKey; value = "8510"; ingestionKey = "smoke-$suffix-1" })
  }
  $ingest1 = Try-Api -Method Post -Path "/maintenance/meter-readings/ingest" -Body $sample
  $ingest2 = Try-Api -Method Post -Path "/maintenance/meter-readings/ingest" -Body $sample
  Report ($ingest1.ok -and @($ingest1.data.data)[0].status -eq "accepted") "دریافت نمونهٔ سنسوری"
  Report ($ingest2.ok -and @($ingest2.data.data)[0].status -eq "duplicate") `
    "ارسال دوبارهٔ همان نمونه دوباره‌شمارش نمی‌شود (idempotent)"

  $readingId = $second.data.data.id
  $correction = Try-Api -Method Post -Path "/maintenance/meter-readings/$readingId/correct" -Body @{
    value = "8506"; note = "اصلاح خطای تایپ"
  }
  Report ($correction.ok -and $correction.data.data.correctsReadingId -eq $readingId) `
    "ثبت اصلاحیه (رکورد اصلی حذف نمی‌شود)"

  # باگ ۳: ساعت کارکرد دیگر از فرم پلاک قابل بازنویسی نیست.
  $null = Try-Api -Method Patch -Path "/maintenance/devices/$deviceId/nameplate" -Body @{
    runningHours = "5"; manufacturer = "ABB"
  }
  $profile = Try-Api -Method Get -Path "/maintenance/devices/$deviceId/profile"
  $derived = $false
  if ($profile.ok) { $derived = [bool]$profile.data.data.nameplate.runningHoursDerived }
  Report $derived "ساعت کارکرد مشتق‌شده است و فرم پلاک آن را بازنویسی نمی‌کند"

  $sensorOnly = Try-Api -Method Get -Path "/maintenance/meter-readings?deviceId=$deviceId&captureMode=sensor"
  Report ($sensorOnly.ok -and @($sensorOnly.data.data).Count -ge 1) "فیلتر قرائت‌های سنسوری"
}

# --- خلاصه ------------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " موفق: $($script:passes)   ناموفق: $($script:failures)"
Write-Host "=============================================" -ForegroundColor Cyan
if ($script:failures -gt 0) { exit 1 }
Write-Host "همه‌چیز سبز است." -ForegroundColor Green
exit 0
