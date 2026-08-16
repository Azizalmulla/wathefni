# Read-only diagnosis: Teams license + online meeting providers for evidence mailbox.
# Does NOT change RBAC, app permissions, or policies.
param(
  [string]$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
  [string]$TenantId = "ffd171d7-94a7-41a2-a38a-b9bc3ba4a082",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $OutDir) {
  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $OutDir = Join-Path $PSScriptRoot ".." "ops" "evidence" "m365-teams-authority-diag-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "OUT=$OutDir"
Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
Import-Module Microsoft.Graph.Identity.DirectoryManagement -ErrorAction SilentlyContinue

# Delegated interactive read for license details (admin user).
Connect-MgGraph -TenantId $TenantId -Scopes "User.Read.All","Organization.Read.All","Directory.Read.All" -NoWelcome

$user = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/users/$([uri]::EscapeDataString($EvidenceUpn))?`$select=id,displayName,userPrincipalName,accountEnabled,assignedLicenses"
$user | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $OutDir "user.json") -Encoding utf8

$lic = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/users/$([uri]::EscapeDataString($EvidenceUpn))/licenseDetails"
$lic | ConvertTo-Json -Depth 10 | Set-Content -Path (Join-Path $OutDir "licenseDetails.json") -Encoding utf8

$cal = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/users/$([uri]::EscapeDataString($EvidenceUpn))/calendar?`$select=allowedOnlineMeetingProviders,defaultOnlineMeetingProvider,name,owner"
$cal | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $OutDir "calendar-delegated.json") -Encoding utf8

$teamsPlans = @()
foreach ($row in @($lic.value)) {
  foreach ($sp in @($row.servicePlans)) {
    $name = [string]$sp.servicePlanName
    if ($name -match 'TEAMS|MCOSTANDARD|MCOEV|MCOMEETADV|MCO_') {
      $teamsPlans += [pscustomobject]@{
        skuPartNumber = $row.skuPartNumber
        servicePlanName = $name
        provisioningStatus = $sp.provisioningStatus
      }
    }
  }
}
$summary = [ordered]@{
  evidence_upn = $EvidenceUpn
  user_id = $user.id
  account_enabled = $user.accountEnabled
  allowedOnlineMeetingProviders = $cal.allowedOnlineMeetingProviders
  defaultOnlineMeetingProvider = $cal.defaultOnlineMeetingProvider
  teams_related_plans = $teamsPlans
  has_active_teams_plan = [bool]($teamsPlans | Where-Object { $_.provisioningStatus -eq 'Success' -and $_.servicePlanName -match 'TEAMS' })
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $OutDir "SUMMARY.json") -Encoding utf8
$summary | ConvertTo-Json -Depth 8
Write-Host "Wrote $OutDir"
Disconnect-MgGraph | Out-Null
