# Tekarai Step 5 smoke test: profile, sessions, API keys and audit stream.
# Run after .\run_dev.ps1:
#   powershell.exe -ExecutionPolicy Bypass -File .\exercise_step5.ps1
param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$TenantCode = "platform",
  [string]$AdminUsername = "platform-admin",
  [string]$AdminPassword = "Tekarai-Demo-2026!"
)
$ErrorActionPreference = "Stop"
$api = "$($BaseUrl.TrimEnd('/'))/api/v1"
$script:token = ""
$script:pass = 0
$script:fail = 0
function Report([bool]$ok, [string]$label) { if ($ok) { $script:pass++; Write-Host "  [PASS] $label" -ForegroundColor Green } else { $script:fail++; Write-Host "  [FAIL] $label" -ForegroundColor Red } }
function Call-Json {
  param([string]$Method, [string]$Path, $Body = $null)
  try {
    $headers = @{}
    if ($script:token) { $headers["Authorization"] = "Bearer $($script:token)" }
    if ($Method -eq "Get" -or $Method -eq "Head") {
      return Invoke-RestMethod -Method $Method -Uri "$api$Path" -Headers $headers
    }
    $params = @{ Method = $Method; Uri = "$api$Path"; Headers = $headers }
    if ($null -ne $Body -and $Body -ne "") { $params["Body"] = $Body; $params["ContentType"] = "application/json" }
    return Invoke-RestMethod @params
  } catch { return $null }
}
function Json([hashtable]$value) { return ($value | ConvertTo-Json -Depth 10 -Compress) }
Write-Host ""
Write-Host "== Tekarai Step 5: infrastructure flows ==" -ForegroundColor Cyan
Write-Host "   base url : $BaseUrl"
Write-Host "   tenant   : $TenantCode"
Write-Host "   user     : $AdminUsername"
Write-Host ""
Write-Host "-- 0. Login" -ForegroundColor Yellow
$login = Call-Json -Method "Post" -Path "/auth/login" -Body (Json @{ tenantCode = $TenantCode; identifier = $AdminUsername; password = $AdminPassword })
Report ($null -ne $login -and $null -ne $login.data.accessToken) "POST /auth/login"
if (-not $login -or -not $login.data.accessToken) { exit 1 }
$script:token = $login.data.accessToken
$user = Call-Json -Method "Get" -Path "/me"
$tenantId = [string]$user.data.user.tenantId
$userId = [string]$user.data.user.id
Report ($null -ne $user -and $user.data.user.username -eq $AdminUsername) "GET /me returns the real profile"
$sessions = Call-Json -Method "Get" -Path "/me/sessions"
Report ($null -ne $sessions -and $sessions.success -eq $true -and $sessions.data.Count -ge 1) "GET /me/sessions returns an active session"
Write-Host "-- 1. API keys" -ForegroundColor Yellow
$keyName = "step5-" + (Get-Date -Format "MMdd-HHmmss")
$created = Call-Json -Method "Post" -Path "/api-keys" -Body (Json @{ tenantId = $tenantId; name = $keyName; ownerType = "user"; ownerId = $userId; scopes = @() })
$keyId = if ($created) { [string]$created.data.apiKey.id } else { "" }
Report ($null -ne $created -and $created.success -eq $true -and $created.data.rawKey -like "tek_*") "POST /api-keys returns a one-time raw secret"
$keys = Call-Json -Method "Get" -Path "/api-keys?ownerType=user&ownerId=$userId"
Report ($null -ne $keys -and ($keys.data | Where-Object { $_.id -eq $keyId })) "GET /api-keys lists the created key"
$revoked = Call-Json -Method "Delete" -Path "/api-keys/$keyId"
Report ($null -ne $revoked -and $revoked.data.revoked -eq $true) "DELETE /api-keys/{id} revokes the key"
Write-Host "-- 2. Audit stream" -ForegroundColor Yellow
$audit = Call-Json -Method "Get" -Path "/platform/audit-events?pageSize=50"
Report ($null -ne $audit -and $audit.success -eq $true -and $null -ne $audit.meta.pagination) "GET /platform/audit-events returns cursor pagination"
Report ($null -ne $audit -and $audit.data.Count -ge 1) "audit stream contains infrastructure activity"
Write-Host ""
Write-Host "== Summary ==" -ForegroundColor Cyan
Write-Host "   PASS: $($script:pass)"
Write-Host "   FAIL: $($script:fail)"
if ($script:fail -gt 0) { exit 1 }
Write-Host "Step 5 infrastructure flows passed (MFA setup/confirmation is intentionally tested through the existing TOTP contract suite)." -ForegroundColor Green
exit 0
