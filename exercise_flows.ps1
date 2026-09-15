# =============================================================================
# Tekarai - Step 3: exercise the READY backend flows through the REAL HTTP API.
#
#   .\exercise_flows.ps1
#
# Requires the backend to be running (start it with .\run_dev.ps1 first).
# It logs in with the platform admin, then exercises:
#   1. Users & roles   -> list users, create a user, list roles, assign a role
#   2. Broadcast       -> send a notification broadcast, check unread-count
#   3. Chat            -> create a group conversation, send + list messages
#   4. AI agent        -> register/submit/approve an agent and run it (SYNC)
#
# Every step prints [PASS]/[FAIL]. The script exits with code 1 if any step
# fails, so it can be used as a smoke test in CI too.
#
# Common overrides:
#   .\exercise_flows.ps1 -BaseUrl "http://localhost:8000"
#   .\exercise_flows.ps1 -AdminUsername admin -AdminPassword "OtherPass123!"
# =============================================================================
param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$TenantCode = "platform",
  [string]$AdminUsername = "platform-admin",
  [string]$AdminPassword = "Tekarai-Demo-2026!"
)

$ErrorActionPreference = "Stop"

$base = $BaseUrl.TrimEnd("/")
$api  = "$base/api/v1"

$script:pass = 0
$script:fail = 0
$script:token = ""

function Report([bool]$ok, [string]$label) {
  if ($ok) {
    $script:pass++
    Write-Host "  [PASS] $label" -ForegroundColor Green
  } else {
    $script:fail++
    Write-Host "  [FAIL] $label" -ForegroundColor Red
  }
}

function Call-Json {
  param(
    [string]$Method,
    [string]$Path,
    [string]$Body = $null,
    [string]$Label = ""
  )
  try {
    $headers = @{}
    if ($script:token) { $headers["Authorization"] = "Bearer $($script:token)" }
    $params = @{
      Method  = $Method
      Uri     = "$api$Path"
      Headers = $headers
    }
    if ($null -ne $Body) {
      $params["Body"] = $Body
      # Only set ContentType when a body is sent: Windows PowerShell 5.1
      # fails GET requests with "Cannot send a content-body with this verb-type"
      # if ContentType is present without a body.
      $params["ContentType"] = "application/json"
    }
    $resp = Invoke-RestMethod @params
    if ($Label) { Report $true $Label }
    return $resp
  } catch {
    $msg = $_.Exception.Message
    try {
      $errBody = $_.ErrorDetails.Message
      if ($errBody) { $msg = "$msg | $errBody" }
    } catch { }
    if ($Label) { Report $false "$Label -> $msg" }
    return $null
  }
}

function Json-Body([hashtable]$obj) {
  return ($obj | ConvertTo-Json -Depth 12 -Compress)
}

Write-Host ""
Write-Host "== Tekarai Step 3: exercising backend flows ==" -ForegroundColor Cyan
Write-Host "   base url : $base"
Write-Host "   tenant   : $TenantCode"
Write-Host "   user     : $AdminUsername"
Write-Host ""

# ---------------------------------------------------------------------------
# 0. login (real backend, non-demo)
# ---------------------------------------------------------------------------
Write-Host "-- 0. Login" -ForegroundColor Yellow
$login = Call-Json -Method "Post" -Path "/auth/login" -Body (Json-Body @{
  tenantCode = $TenantCode
  identifier = $AdminUsername
  password   = $AdminPassword
}) -Label "POST /auth/login"

if (-not $login -or -not $login.data.accessToken) {
  Write-Host ""
  Write-Host "LOGIN FAILED - is the backend running? Start it with: .\run_dev.ps1" -ForegroundColor Red
  exit 1
}
$script:token = $login.data.accessToken
Report ($login.data.permissions -is [System.Array] -and $login.data.permissions.Count -gt 0) `
  "login payload carries effective permissions ($($login.data.permissions.Count))"

# ---------------------------------------------------------------------------
# 1. users & roles
# ---------------------------------------------------------------------------
Write-Host "-- 1. Users & roles" -ForegroundColor Yellow

$me = Call-Json -Method "Get" -Path "/me" -Label "GET /me"
if (-not $me) {
  Write-Host "Cannot continue without /me (needed for the admin user id)." -ForegroundColor Red
  exit 1
}
$adminId = $me.data.user.id

$users = Call-Json -Method "Get" -Path "/users" -Label "GET /users (list)"
Report ($users.meta.pagination.totalCount -ge 1) "users list non-empty ($($users.meta.pagination.totalCount))"

$username = "flow-" + (Get-Date -Format "MMdd-HHmmss")
$created = Call-Json -Method "Post" -Path "/users" -Body (Json-Body @{
  username    = $username
  email       = "$username@tekarai.local"
  password    = "Strong-Pass-2026!"
  displayName = "Flow Exercise User"
}) -Label "POST /users (create '$username')"
$userId = $created.data.id

$roles = Call-Json -Method "Get" -Path "/roles" -Label "GET /roles (list)"
if (-not $roles) {
  Write-Host "Cannot continue without /roles (needed to assign the 'member' role)." -ForegroundColor Red
  exit 1
}
$memberRole = $roles.data | Where-Object { $_.code -eq "member" } | Select-Object -First 1
Report ($null -ne $memberRole) "role 'member' present in catalog"

$assigned = Call-Json -Method "Post" -Path "/users/$userId/roles" -Body (Json-Body @{
  roleId = $memberRole.id
}) -Label "POST /users/$userId/roles (assign 'member')"
Report ($assigned.data.assigned -eq $true) "role assignment confirmed"

# ---------------------------------------------------------------------------
# 2. notification broadcast
# ---------------------------------------------------------------------------
Write-Host "-- 2. Notification broadcast" -ForegroundColor Yellow

$broadcast = Call-Json -Method "Post" -Path "/notifications/broadcasts" -Body (Json-Body @{
  notificationType = "FLOW_CHECK"
  title            = "Flow exercise broadcast"
  body             = "Sent by exercise_flows.ps1"
  recipientIds     = @($adminId)
  priority         = "NORMAL"
}) -Label "POST /notifications/broadcasts"

$unread = Call-Json -Method "Get" -Path "/notifications/broadcasts/unread-count" -Label "GET /notifications/broadcasts/unread-count"
Report ($unread.data.unreadCount -ge 1) "admin has an unread broadcast ($($unread.data.unreadCount))"

# ---------------------------------------------------------------------------
# 3. conversation / chat
# ---------------------------------------------------------------------------
Write-Host "-- 3. Conversation & chat" -ForegroundColor Yellow

$conv = Call-Json -Method "Post" -Path "/communication/conversations" -Body (Json-Body @{
  kind      = "group"
  name      = "Flow Exercise Group"
  memberIds = @()
}) -Label "POST /communication/conversations (group)"
$convId = $conv.data.id

$sent = Call-Json -Method "Post" -Path "/communication/conversations/$convId/messages" -Body (Json-Body @{
  body            = "Hello from exercise_flows.ps1"
  clientRequestId = "flow-$([DateTime]::UtcNow.Ticks)"
}) -Label "POST .../messages (send)"

$messages = Call-Json -Method "Get" -Path "/communication/conversations/$convId/messages" -Label "GET .../messages (list)"
Report ($messages.meta.totalCount -ge 1) "message persisted ($($messages.meta.totalCount))"

# ---------------------------------------------------------------------------
# 4. AI agent run (offline deterministic provider)
# ---------------------------------------------------------------------------
Write-Host "-- 4. AI agent run" -ForegroundColor Yellow

$agentCode = "EXERCISE_" + (Get-Date -Format "HHmmss")
$agent = Call-Json -Method "Post" -Path "/ai/agents" -Body (Json-Body @{
  code         = $agentCode
  name         = "Flow exercise agent"
  instructions = "Return a concise release answer."
  riskLevel    = "LOW"
  modelPolicy  = @{ provider = "DETERMINISTIC"; model = "test" }
}) -Label "POST /ai/agents (register '$agentCode')"
$version = $agent.data.version

Call-Json -Method "Post" -Path "/ai/agents/$agentCode/versions/$version/submit" -Body "{}" -Label "POST .../submit" | Out-Null
Call-Json -Method "Post" -Path "/ai/agents/$agentCode/versions/$version/approve" -Body "{}" -Label "POST .../approve" | Out-Null

$run = Call-Json -Method "Post" -Path "/ai/agents/$agentCode/runs" -Body (Json-Body @{
  input = @{ task = "verify release" }
  mode  = "SYNC"
}) -Label "POST /ai/agents/$agentCode/runs (SYNC)"
$runId = $run.data.run.runId
Report ($run.data.executed -eq $true) "run executed synchronously"
Report ($run.data.run.status -eq "COMPLETED") "run status COMPLETED (got '$($run.data.run.status)')"

$steps = Call-Json -Method "Get" -Path "/ai/runs/$runId/steps" -Label "GET /ai/runs/$runId/steps"
Report ($steps.meta.count -ge 1) "run persisted steps ($($steps.meta.count))"

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "== Summary ==" -ForegroundColor Cyan
Write-Host "   PASS: $($script:pass)"
Write-Host "   FAIL: $($script:fail)"
Write-Host ""

if ($script:fail -gt 0) {
  Write-Host "Some flows failed. Scroll up for [FAIL] details." -ForegroundColor Red
  exit 1
}

Write-Host "All flows passed. The backend's ready flows work end-to-end." -ForegroundColor Green
exit 0
