# =============================================================================
# Tekarai — رفع خطای ورود «Unexpected server error»
#
#   .\fix_login.ps1              → تشخیص + رفع خودکار (migrate + ساخت ادمین)
#   .\fix_login.ps1 -Sqlite      → همان، ولی روی SQLite محلی (بدون نیاز به SQL Server)
#   .\fix_login.ps1 -CheckOnly   → فقط تشخیص، بدون تغییر در پایگاه داده
#
# این اسکریپت همان درخواست ورود را از داخل جنگو اجرا می‌کند و اگر شکست بخورد،
# متن واقعی استثنا را چاپ می‌کند — نه پیام عمومی «Unexpected server error».
# =============================================================================
param(
  [switch]$Sqlite,
  [switch]$CheckOnly,
  [string]$AdminPassword = "Tekarai-Demo-2026!"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- پیدا کردن پایتونِ محیط مجازی (هر دو نام رایج پشتیبانی می‌شود) -----------
$candidates = @(
  (Join-Path $PSScriptRoot "backend\venv\Scripts\python.exe"),
  (Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"),
  (Join-Path $PSScriptRoot "venv\Scripts\python.exe"),
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
)
$python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
  Write-Host ">> محیط مجازی پیدا نشد؛ در حال ساخت backend\.venv ..." -ForegroundColor Yellow
  python -m venv backend\.venv
  $python = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
  if (-not (Test-Path $python)) {
    Write-Host "ساخت محیط مجازی ناموفق بود. آیا Python نصب است؟  python --version" -ForegroundColor Red
    exit 1
  }
  & $python -m pip install --upgrade pip | Out-Null
}

Write-Host ">> Python: $(& $python --version 2>&1)" -ForegroundColor Cyan

# --- اطمینان از نصب بودن جنگو ------------------------------------------------
& $python -c "import django" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host ">> نصب وابستگی‌های بک‌اند (یک‌بار) ..." -ForegroundColor Yellow
  & $python -m pip install -r backend\requirements\development.txt
}

$env:PLATFORM_ADMIN_PASSWORD = $AdminPassword
if ($Sqlite) { $env:dbEngine = "sqlite" }

$doctorArgs = @("backend\scripts\doctorLogin.py")
if (-not $CheckOnly) { $doctorArgs += "--fix" }
if ($Sqlite)         { $doctorArgs += "--sqlite" }

& $python @doctorArgs
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
  Write-Host "== ورود سالم است. حالا برنامه را بالا بیاورید: ==" -ForegroundColor Green
  if ($Sqlite) { Write-Host "   .\run_dev.ps1 -UseSqlite" } else { Write-Host "   .\run_dev.ps1" }
} else {
  Write-Host "== هنوز مشکل باقی است (کد خروج $code) ==" -ForegroundColor Red
  switch ($code) {
    2 { Write-Host "   وابستگی‌های پایتون نصب نیست: pip install -r backend\requirements\development.txt" }
    3 { Write-Host "   پایگاه داده در دسترس نیست. با SQLite امتحان کنید:  .\fix_login.ps1 -Sqlite" }
    4 { Write-Host "   جدول‌ها ساخته نشده‌اند. بدون سوئیچ -CheckOnly اجرا کنید:  .\fix_login.ps1 -Sqlite" }
    5 { Write-Host "   متن استثنای واقعی بالا چاپ شد؛ همان را برای بررسی بفرستید." }
  }
}
exit $code
