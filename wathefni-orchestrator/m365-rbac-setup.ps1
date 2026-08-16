$ErrorActionPreference = "Stop"
$Evid = $env:EVID
$AppId = $env:WATHEFNI_M365_CLIENT_ID
$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
$DeniedAlias = "wathefni-rbac-deny-probe"
$domain = "wathefni.onmicrosoft.com"
$AuDisplayName = "Wathefni-Calendar-Evidence"
$SpMeta = Get-Content (Join-Path $Evid "entra-service-principal.json") | ConvertFrom-Json
$SpObjectId = $SpMeta.objectId
$DisplayName = if ($SpMeta.displayName) { $SpMeta.displayName } else { "Wathefni Platform Integration" }

Write-Host "Connecting Microsoft Graph (device code) for Administrative Unit..."
Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Applications
Import-Module Microsoft.Graph.Users
Import-Module Microsoft.Graph.Identity.DirectoryManagement

Connect-MgGraph -Scopes "AdministrativeUnit.ReadWrite.All","User.Read.All","Group.ReadWrite.All","Directory.Read.All" -NoWelcome -UseDeviceCode

# Resolve evidence user
$evidenceUser = Get-MgUser -Filter "userPrincipalName eq '$EvidenceUpn'"
if (-not $evidenceUser) { throw "evidence_user_not_found:$EvidenceUpn" }

# Create or reuse AU
$au = Get-MgDirectoryAdministrativeUnit -Filter "displayName eq '$AuDisplayName'" | Select-Object -First 1
if (-not $au) {
  $au = New-MgDirectoryAdministrativeUnit -DisplayName $AuDisplayName -Description "Wathefni Calendar evidence mailbox scope" -Visibility "Public"
  Write-Host "Created administrative unit"
} else {
  Write-Host "Administrative unit already exists"
}
$AuId = $au.Id

# Add evidence user as AU member (idempotent)
$members = Get-MgDirectoryAdministrativeUnitMember -AdministrativeUnitId $AuId -All -ErrorAction SilentlyContinue
$already = $false
foreach ($m in @($members)) {
  if ($m.Id -eq $evidenceUser.Id) { $already = $true; break }
}
if (-not $already) {
  $body = @{ "@odata.id" = "https://graph.microsoft.com/v1.0/users/$($evidenceUser.Id)" }
  New-MgDirectoryAdministrativeUnitMemberByRef -AdministrativeUnitId $AuId -BodyParameter $body
  Write-Host "Added evidence user to AU"
} else {
  Write-Host "Evidence user already in AU"
}

@{
  administrativeUnitId = $AuId
  administrativeUnitName = $AuDisplayName
  evidenceUserId = $evidenceUser.Id
  evidenceUpn = $EvidenceUpn
} | ConvertTo-Json | Set-Content (Join-Path $Evid "entra-admin-unit.json")

Disconnect-MgGraph | Out-Null
Write-Host "AU_READY"

Write-Host "Connecting Exchange Online (device code)..."
Import-Module ExchangeOnlineManagement
Connect-ExchangeOnline -Device -ShowBanner:$false

try { Enable-OrganizationCustomization -ErrorAction Stop } catch { Write-Host ("Org customization: " + $_.Exception.Message) }

# Service principal pointer
$existingSp = @(Get-ServicePrincipal -ErrorAction SilentlyContinue | Where-Object { $_.AppId -eq $AppId -or $_.ObjectId -eq $SpObjectId })
if ($existingSp.Count -eq 0) {
  New-ServicePrincipal -AppId $AppId -ObjectId $SpObjectId -DisplayName $DisplayName | Out-Null
  Write-Host "Created Exchange service principal pointer"
} else {
  Write-Host "Exchange service principal pointer already exists"
}

# Role assignment scoped to AU (no tenant-wide Entra calendar app permission)
$role = "Application Calendars.ReadWrite"
$allCal = @(Get-ManagementRoleAssignment -Role $role -ErrorAction SilentlyContinue)
$match = @($allCal | Where-Object {
  $_.RoleAssigneeName -eq $SpObjectId -or
  $_.RoleAssigneeName -eq $DisplayName -or
  ("$($_.RoleAssignee)" -eq $SpObjectId)
})
if ($match.Count -eq 0) {
  New-ManagementRoleAssignment -App $SpObjectId -Role $role -RecipientAdministrativeUnitScope $AuId | Out-Null
  Write-Host "Created AU-scoped role assignment"
} else {
  foreach ($a in $match) {
    try {
      Set-ManagementRoleAssignment -Identity $a.Identity -RecipientAdministrativeUnitScope $AuId | Out-Null
    } catch {
      Write-Host ("WARN set assignment scope: " + $_.Exception.Message)
    }
  }
  Write-Host "Role assignment present; AU scope refreshed if supported"
}

# Deny probe shared mailbox
$deniedUpn = $null
$deniedIdentity = "$DeniedAlias@$domain"
$existingDenied = Get-Mailbox -Identity $deniedIdentity -ErrorAction SilentlyContinue
if (-not $existingDenied) {
  try {
    $mbx = New-Mailbox -Shared -Name $DeniedAlias -DisplayName "Wathefni RBAC Deny Probe" -Alias $DeniedAlias
    $deniedUpn = [string]$mbx.PrimarySmtpAddress
    Write-Host "Created deny probe shared mailbox"
  } catch {
    Write-Host ("WARN create deny mailbox: " + $_.Exception.Message)
    $other = Get-Mailbox -ResultSize 50 | Where-Object { [string]$_.PrimarySmtpAddress -ne $EvidenceUpn } | Select-Object -First 1
    if ($other) { $deniedUpn = [string]$other.PrimarySmtpAddress }
  }
} else {
  $deniedUpn = [string]$existingDenied.PrimarySmtpAddress
}

Start-Sleep -Seconds 5

$allow = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $EvidenceUpn)
$allow | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Evid "test-allow.json")
$allowRows = @($allow | Where-Object { $_.RoleName -like "*Calendars.ReadWrite*" })
$allowInScope = (@($allowRows | Where-Object { $_.InScope -eq $true })).Count -gt 0

$denyInScope = $null
if ($deniedUpn) {
  $deny = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $deniedUpn)
  $deny | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Evid "test-deny.json")
  $denyRows = @($deny | Where-Object { $_.RoleName -like "*Calendars.ReadWrite*" })
  $denyInScope = (@($denyRows | Where-Object { $_.InScope -eq $true })).Count -gt 0
}

$result = [ordered]@{
  evidence_upn = $EvidenceUpn
  denied_upn = $deniedUpn
  scope_type = "RecipientAdministrativeUnitScope"
  administrative_unit_id = $AuId
  administrative_unit_name = $AuDisplayName
  role = $role
  sp_object_id_suffix = $SpObjectId.Substring($SpObjectId.Length - 8)
  app_id_suffix = $AppId.Substring($AppId.Length - 8)
  allow_calendars_inscope = $allowInScope
  deny_calendars_inscope = $denyInScope
  allow_rows = @($allow | Select-Object RoleName, GrantedPermissions, AllowedResourceScope, ScopeType, InScope)
  deny_rows = if ($deniedUpn) { @($deny | Select-Object RoleName, GrantedPermissions, AllowedResourceScope, ScopeType, InScope) } else { @() }
  commands = @(
    "New-ServicePrincipal -AppId <clientId> -ObjectId <enterpriseObjectId> -DisplayName 'Wathefni Platform Integration'",
    "New-MgDirectoryAdministrativeUnit -DisplayName '$AuDisplayName'",
    "New-MgDirectoryAdministrativeUnitMemberByRef (evidence user)",
    "New-ManagementRoleAssignment -App <enterpriseObjectId> -Role 'Application Calendars.ReadWrite' -RecipientAdministrativeUnitScope <auId>",
    "Test-ServicePrincipalAuthorization -Identity <enterpriseObjectId> -Resource '$EvidenceUpn'"
  )
  note = "Used Administrative Unit scope because New-ManagementScope remained blocked after Enable-OrganizationCustomization (Microsoft-supported RBACfA alternative)."
}
$result | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Evid "rbac-results.json")
# Persist denied UPN for live calendar proof
"WATHEFNI_M365_DENIED_UPN=$deniedUpn" | Set-Content (Join-Path $Evid "denied-upn.env")
Write-Host ("ALLOW_INSCOPE=" + $allowInScope)
Write-Host ("DENY_INSCOPE=" + $denyInScope)
Write-Host ("DENIED_UPN=" + $deniedUpn)
Write-Host ("AU_ID_SUFFIX=" + $AuId.Substring($AuId.Length - 8))
Write-Host "RBAC_SETUP_DONE"
Disconnect-ExchangeOnline -Confirm:$false
