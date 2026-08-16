# Run on your Mac (browser auth — NOT device code).
# Requires: pwsh + ExchangeOnlineManagement
#   brew install --cask powershell
#   pwsh -Command "Install-Module ExchangeOnlineManagement -Scope CurrentUser -Force"
#
# Usage:
#   pwsh -File ./m365-rbac-local-connect.ps1
# After CONNECT proves admin, re-run with -Assign to create the role assignment.

param(
  [switch]$Assign
)

$ErrorActionPreference = "Stop"
Import-Module ExchangeOnlineManagement

$Upn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
$Org = "wathefni.onmicrosoft.com"
$Sp  = "46f5549d-4382-48fa-9c20-aff2f13451d5"
$Au  = "9d4e6a0e-47af-4603-a8f2-532e45911d40"
$Role = "Application Calendars.ReadWrite"
$Evidence = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"

Write-Host "Connecting with interactive browser (no -Device)..."
Connect-ExchangeOnline -UserPrincipalName $Upn -Organization $Org -ShowBanner:$false

$who = Get-ConnectionInformation | Select-Object -First 1
Write-Host ("SIGNED_IN_USER=" + $who.UserPrincipalName)
Write-Host ("SIGNED_IN_TENANT=" + $who.TenantId)

$cfg = Get-OrganizationConfig
Write-Host ("IsDehydrated=" + $cfg.IsDehydrated)
$me = Get-User -Identity $Upn | Select-Object UserPrincipalName, RemotePowerShellEnabled, RecipientTypeDetails
$me | Format-List
Get-ManagementRoleAssignment -Role $Role | Select-Object -First 3 | Format-Table Name, Role, RoleAssigneeName

if (-not $Assign) {
  Write-Host "Admin probe OK. Re-run with -Assign to run New-ManagementRoleAssignment."
  Disconnect-ExchangeOnline -Confirm:$false
  exit 0
}

New-ManagementRoleAssignment -App $Sp -Role $Role -RecipientAdministrativeUnitScope $Au
$allow = @(Test-ServicePrincipalAuthorization -Identity $Sp -Resource $Evidence)
$allow | Format-Table RoleName, InScope, AllowedResourceScope, ScopeType
$ok = (@($allow | Where-Object { $_.RoleName -like "*Calendars.ReadWrite*" -and $_.InScope -eq $true })).Count -gt 0
Disconnect-ExchangeOnline -Confirm:$false
if (-not $ok) { throw "VERIFY_FAIL: Application Calendars.ReadWrite InScope!=True" }
Write-Host "VERIFY_PASS"
