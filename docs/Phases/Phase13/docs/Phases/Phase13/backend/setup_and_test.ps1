<#
=============================================================================
 Tekarai Backend - راه‌اندازی و اجرای تست‌ها در PowerShell (ویندوز)
-----------------------------------------------------------------------------
 این اسکریپت:
   1) پایتون را پیدا می‌کند
   2) محیط مجازی .venv را می‌سازد (اگر نباشد یا خراب باشد باز می‌سازد)
   3) وابستگی‌ها را نصب می‌کند
   4) دستور check جنگو را اجرا می‌کند
   5) تست‌ها را اجرا می‌کند

 نحوهٔ اجرا:
   - PowerShell را در پوشهٔ backend باز کنید
   - برای اجازهٔ اجرای اسکریپت (فقط همان پنجره):
         Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   - سپس:
         .\setup_and_test.ps1

 اجرای فقط تست‌های فاز ۱۰:
         .\setup_and_test.ps1 -Phase10
 اجرای یک تست خاص (با نام):
         .\setup_and_test.ps1 -Label "tests.integration.testPhase10ApiContract"
=============================================================================
#>

param(
    [switch]$Phase10,
    [string]$Label = ""
)

$ErrorActionPreference = "Stop"

# رفتن به پوشهٔ همان اسکریپت (پوشهٔ backend)
Set-Location -Path $PSScriptRoot

Write-Host "==> پوشهٔ کاری: $PSScriptRoot" -ForegroundColor Cyan

# --- 1) پیدا کردن پایتون ---------------------------------------------------
function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    Write-Host "پایتون پیدا نشد. لطفاً Python 3.12 یا بالاتر نصب کنید: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
$py = Resolve-Python
Write-Host "==> پایتون: $py" -ForegroundColor Cyan
& $py --version

# --- 2) ساخت/بازسازی محیط مجازی -------------------------------------------
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$needSetup = $true
if (Test-Path $venvPython) {
    try {
        & $venvPython -c "import django, channels, daphne" 2>$null
        if ($LASTEXITCODE -eq 0) { $needSetup = $false }
    } catch { $needSetup = $true }
}

if ($needSetup) {
    Write-Host "==> ساخت/بازسازی محیط مجازی .venv ..." -ForegroundColor Yellow
    if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
    & $py -m venv .venv
    Write-Host "==> به‌روزرسانی pip ..." -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pip
    Write-Host "==> نصب وابستگی‌ها (requirements/development.txt) ..." -ForegroundColor Yellow
    & $venvPython -m pip install -r requirements/development.txt
} else {
    Write-Host "==> محیط مجازی .venv آماده است." -ForegroundColor Green
}

# --- 3) فعال‌سازی محیط (برای راحتی اجرای دستی بعدی) ------------------------
$activate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $activate) { . $activate }

# --- 4) چک سلامت جنگو ------------------------------------------------------
Write-Host "`n==> Django system check ..." -ForegroundColor Cyan
& $venvPython manage.py check --settings=config.settings.testing
if ($LASTEXITCODE -ne 0) { Write-Host "check شکست خورد." -ForegroundColor Red; exit 1 }

# --- 5) اجرای تست‌ها --------------------------------------------------------
Write-Host "`n==> اجرای تست‌ها ..." -ForegroundColor Cyan
if ($Phase10) {
    & $venvPython manage.py test tests.unit.testPhase10Domain tests.application.testPhase10UseCases tests.integration.testPhase10ApiContract --settings=config.settings.testing
}
elseif ($Label -ne "") {
    & $venvPython manage.py test $Label --settings=config.settings.testing
}
else {
    & $venvPython manage.py test --settings=config.settings.testing
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==> همهٔ تست‌ها سبز شدند ✓" -ForegroundColor Green
} else {
    Write-Host "`n==> تست‌ها خطا دادند؛ متن خطا را برای رفع بفرستید." -ForegroundColor Red
    exit 1
}
