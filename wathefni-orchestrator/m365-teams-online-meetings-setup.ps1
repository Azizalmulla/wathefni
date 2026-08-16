#Requires -Modules Microsoft.Graph.Authentication
<#
.SYNOPSIS
  Narrow Teams Online Meetings authority for Wathefni — does NOT touch Exchange RBACfA.

Steps (require Global Admin approval):
  1) Ensure Entra app has application permission OnlineMeetings.ReadWrite.All
  2) Grant tenant admin consent for that permission
  3) Create Teams Application Access Policy bound to Wathefni app id
  4) Grant that policy ONLY to the evidence/authorized organizer user (never -Global)

Preserves existing Exchange RBACfA Application Calendars.ReadWrite + AU scope.
#>
param(
  [string]$TenantId = "ffd171d7-94a7-41a2-a38a-b9bc3ba4a082",
  [string]$AppId = "16f7135a-b7e8-4ac8-adfe-2d2b13de3131",
  [string]$SpObjectId = "46f5549d-4382-48fa-9c20-aff2f13451d5",
  [string]$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
  [string]$EvidenceUserId = "dcb6b7dd-8509-4a20-8069-ec0de9445dd7",
  [string]$PolicyIdentity = "Wathefni-OnlineMeetings-Evidence",
  [string]$OutDir = "",
  [switch]$SkipPermissionGrant,
  [switch]$SkipTeamsPolicy,
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
if (-not $OutDir) {
  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $OutDir = Join-Path (Split-Path $PSScriptRoot -Parent) "ops" "evidence" "m365-teams-aap-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Write-Host "OUT=$OutDir"

function Write-Json($Path, $Obj) {
  $Obj | ConvertTo-Json -Depth 10 | Set-Content -Path $Path -Encoding utf8
}

# ---- 1+2: Graph application permission OnlineMeetings.ReadWrite.All + admin consent via role assignment
Import-Module Microsoft.Graph.Authentication
Connect-MgGraph -TenantId $TenantId -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All","Directory.Read.All" -NoWelcome

$graphSp = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals?`$filter=appId eq '00000003-0000-0000-c000-000000000000'&`$select=id,appId,displayName"
$graphSpId = $graphSp.value[0].id
$roles = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$graphSpId/appRoles"
$omRole = $roles.value | Where-Object { $_.value -eq "OnlineMeetings.ReadWrite.All" -and $_.isEnabled } | Select-Object -First 1
if (-not $omRole) { throw "OnlineMeetings.ReadWrite.All app role not found on Microsoft Graph" }
Write-Json (Join-Path $OutDir "onlineMeetings-approle.json") $omRole

$existing = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignments"
$already = @($existing.value) | Where-Object { $_.appRoleId -eq $omRole.id -and $_.resourceId -eq $graphSpId }
Write-Json (Join-Path $OutDir "existing-approle-assignments.json") $existing

$permResult = [ordered]@{ already = [bool]$already; granted_now = $false }
if (-not $already) {
  if ($SkipPermissionGrant -or $WhatIf) {
    $permResult.skipped = $true
    $permResult.note = "Run without -SkipPermissionGrant to assign OnlineMeetings.ReadWrite.All"
  } else {
    $body = @{
      principalId = $SpObjectId
      resourceId = $graphSpId
      appRoleId = $omRole.id
    }
    $created = Invoke-MgGraphRequest -Method POST -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignments" -Body ($body | ConvertTo-Json) -ContentType "application/json"
    Write-Json (Join-Path $OutDir "approle-assignment-created.json") $created
    $permResult.granted_now = $true
    $permResult.assignment_id = $created.id
  }
} else {
  $permResult.assignment_id = $already.id
}
Write-Json (Join-Path $OutDir "permission-grant.json") $permResult
Write-Host "PERMISSION: $(ConvertTo-Json $permResult -Compress)"

Disconnect-MgGraph | Out-Null

# ---- 3+4: Teams Application Access Policy (requires MicrosoftTeams module + Teams admin)
$policyResult = [ordered]@{ skipped = $false }
if ($SkipTeamsPolicy) {
  $policyResult.skipped = $true
  $policyResult.note = "Skipped by switch; run Teams policy section separately"
} else {
  if (-not (Get-Module -ListAvailable -Name MicrosoftTeams)) {
    Write-Host "Installing MicrosoftTeams module..."
    Install-Module MicrosoftTeams -Scope CurrentUser -Force -AllowClobber
  }
  Import-Module MicrosoftTeams
  # Interactive Teams admin login (same GA as Exchange RBAC work)
  Connect-MicrosoftTeams -TenantId $TenantId | Out-Null

  $existingPolicy = $null
  try { $existingPolicy = Get-CsApplicationAccessPolicy -Identity $PolicyIdentity -ErrorAction SilentlyContinue } catch {}
  if (-not $existingPolicy) {
    if ($WhatIf) {
      $policyResult.would_create = $PolicyIdentity
    } else {
      New-CsApplicationAccessPolicy -Identity $PolicyIdentity -AppIds $AppId -Description "Wathefni OnlineMeetings for evidence organizer only (not global)"
      $existingPolicy = Get-CsApplicationAccessPolicy -Identity $PolicyIdentity
    }
  }
  Write-Json (Join-Path $OutDir "application-access-policy.json") $existingPolicy

  if (-not $WhatIf) {
    Grant-CsApplicationAccessPolicy -PolicyName $PolicyIdentity -Identity $EvidenceUserId
    $assigned = Get-CsOnlineUser -Identity $EvidenceUpn | Select-Object UserPrincipalName, Identity, ApplicationAccessPolicy
    Write-Json (Join-Path $OutDir "policy-grant-user.json") $assigned
    $policyResult.granted_to = $EvidenceUpn
    $policyResult.granted_to_id = $EvidenceUserId
    $policyResult.global_grant = $false
    $policyResult.note = "Do NOT run Grant-CsApplicationAccessPolicy -Global"
  }
  Disconnect-MicrosoftTeams | Out-Null
}
Write-Json (Join-Path $OutDir "policy-result.json") $policyResult

$summary = [ordered]@{
  app_id = $AppId
  sp_object_id = $SpObjectId
  permission = "OnlineMeetings.ReadWrite.All"
  permission_result = $permResult
  policy_identity = $PolicyIdentity
  policy_result = $policyResult
  calendar_rbacfa_untouched = $true
  calendar_role = "Application Calendars.ReadWrite"
  calendar_au = "9d4e6a0e-47af-4603-a8f2-532e45911d40"
}
Write-Json (Join-Path $OutDir "SUMMARY.json") $summary
$summary | ConvertTo-Json -Depth 8
Write-Host "DONE OUT=$OutDir"
