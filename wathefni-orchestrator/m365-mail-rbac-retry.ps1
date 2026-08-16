#Requires -Modules ExchangeOnlineManagement
<#
.SYNOPSIS
  Retry Exchange RBACfA Application Mail.Send assignment after AU replication.
#>
param(
  [Parameter(Mandatory=$true)][string]$AppId,
  [Parameter(Mandatory=$true)][string]$SpObjectId,
  [Parameter(Mandatory=$true)][string]$AuId,
  [string]$AppDisplayName = "Wathefni Email Send",
  [string]$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
  [string]$DeniedUpn = "wathefni-rbac-deny-probe@wathefni.onmicrosoft.com",
  [string]$CalendarClientId = "16f7135a-b7e8-4ac8-adfe-2d2b13de3131",
  [string]$OutDir
)

$ErrorActionPreference = "Stop"
if ($AppId -eq $CalendarClientId) { throw "REFUSING: mail app equals calendar app" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Import-Module ExchangeOnlineManagement
Connect-ExchangeOnline -UserPrincipalName $EvidenceUpn -ShowBanner:$false

# Verify AU is visible to EXO
$auOk = $false
$lastErr = $null
foreach ($i in 1..30) {
  try {
    $au = Get-AdministrativeUnit -Identity $AuId -ErrorAction Stop
    Write-Host ("AU_VISIBLE try=$i name=" + $au.DisplayName)
    $auOk = $true
    break
  } catch {
    $lastErr = $_.Exception.Message
    Write-Host ("AU_WAIT try=$i :: " + $lastErr)
    Start-Sleep -Seconds 20
  }
}
if (-not $auOk) { throw "AU not visible to Exchange after wait: $lastErr" }

$existingSp = @(Get-ServicePrincipal -ErrorAction SilentlyContinue | Where-Object { $_.AppId -eq $AppId -or $_.ObjectId -eq $SpObjectId })
if ($existingSp.Count -eq 0) {
  New-ServicePrincipal -AppId $AppId -ObjectId $SpObjectId -DisplayName $AppDisplayName | Out-Null
}

$role = "Application Mail.Send"
$match = @(Get-ManagementRoleAssignment -Role $role -ErrorAction SilentlyContinue | Where-Object {
  $_.RoleAssigneeName -eq $SpObjectId -or $_.RoleAssigneeName -eq $AppDisplayName -or ("$($_.RoleAssignee)" -eq $SpObjectId)
})
if ($match.Count -eq 0) {
  New-ManagementRoleAssignment -App $SpObjectId -Role $role -RecipientAdministrativeUnitScope $AuId | Out-Null
  Write-Host "Created AU-scoped Application Mail.Send assignment"
} else {
  foreach ($a in $match) {
    try { Set-ManagementRoleAssignment -Identity $a.Identity -RecipientAdministrativeUnitScope $AuId | Out-Null } catch { Write-Host $_ }
  }
  Write-Host "Updated existing Mail.Send assignment scope"
}

Start-Sleep -Seconds 5
$allow = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $EvidenceUpn)
$deny = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $DeniedUpn)
$allow | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutDir "test-allow.json")
$deny | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutDir "test-deny.json")

$allowInScope = (@($allow | Where-Object { $_.RoleName -like "*Mail.Send*" -and $_.InScope -eq $true })).Count -gt 0
$denyInScope = (@($deny | Where-Object { $_.RoleName -like "*Mail.Send*" -and $_.InScope -eq $true })).Count -gt 0
$assignMeta = @(Get-ManagementRoleAssignment -Role $role -ErrorAction SilentlyContinue | Where-Object {
  $_.RoleAssigneeName -eq $SpObjectId -or $_.RoleAssigneeName -eq $AppDisplayName -or ("$($_.RoleAssignee)" -eq $SpObjectId)
} | Select-Object Identity, Role, RoleAssignee, RoleAssigneeName, RecipientWriteScope, CustomResourceScope, WhenCreatedUTC)

$result = [ordered]@{
  evidence_upn = $EvidenceUpn
  denied_upn = $DeniedUpn
  administrative_unit_id = $AuId
  role = $role
  app_id = $AppId
  sp_object_id = $SpObjectId
  allow_mail_send_inscope = $allowInScope
  deny_mail_send_inscope = $denyInScope
  assignments = $assignMeta
}
$result | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $OutDir "rbac-results.json")
Write-Host ("ALLOW_INSCOPE=" + $allowInScope)
Write-Host ("DENY_INSCOPE=" + $denyInScope)
if (-not $allowInScope) { throw "evidence mailbox not InScope for Application Mail.Send" }
if ($denyInScope) { throw "outside-scope mailbox unexpectedly InScope" }
Write-Host "MAIL_RBAC_RETRY_OK"
Disconnect-ExchangeOnline -Confirm:$false
