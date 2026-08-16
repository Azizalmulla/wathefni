$ErrorActionPreference = "Continue"
Import-Module ExchangeOnlineManagement
$Evid = $env:EVID
$SpObjectId = $env:SP
$AuId = $env:AU
$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
$domain = "wathefni.onmicrosoft.com"

Write-Host "Connecting Exchange Online (device code)..."
Connect-ExchangeOnline -Device -ShowBanner:$false

Write-Host "---- DIAG ----"
Get-OrganizationConfig | Select-Object Name, IsDehydrated, Guid | Format-List
try { Get-ManagementRole -Identity "Application Calendars.ReadWrite" | Format-List Name, RoleType } catch { Write-Host $_ }
try { Get-ConnectionInformation | Format-List UserPrincipalName, Organization, State } catch { Write-Host $_ }

Write-Host "Retrying role assignment up to 12 times (60s apart)..."
$ok = $false
$used = $null
for ($i = 1; $i -le 12; $i++) {
  try {
    New-ManagementRoleAssignment -App $SpObjectId -Role "Application Calendars.ReadWrite" -RecipientAdministrativeUnitScope $AuId -ErrorAction Stop | Out-Null
    Write-Host ("ASSIGN_AU_OK attempt=" + $i)
    $ok = $true
    $used = "RecipientAdministrativeUnitScope"
    break
  } catch {
    Write-Host ("ASSIGN_AU_FAIL attempt=" + $i + " :: " + $_.Exception.Message)
  }
  try {
    $ScopeName = "Wathefni-Calendar-Evidence"
    $filter = "PrimarySmtpAddress -eq '$EvidenceUpn'"
    if (-not (Get-ManagementScope -Identity $ScopeName -ErrorAction SilentlyContinue)) {
      New-ManagementScope -Name $ScopeName -RecipientRestrictionFilter $filter -ErrorAction Stop | Out-Null
      Write-Host "SCOPE_CREATED"
    }
    New-ManagementRoleAssignment -App $SpObjectId -Role "Application Calendars.ReadWrite" -CustomResourceScope $ScopeName -ErrorAction Stop | Out-Null
    Write-Host ("ASSIGN_SCOPE_OK attempt=" + $i)
    $ok = $true
    $used = "CustomResourceScope"
    break
  } catch {
    Write-Host ("ASSIGN_SCOPE_FAIL attempt=" + $i + " :: " + $_.Exception.Message)
  }
  if ($i -lt 12) { Start-Sleep -Seconds 60 }
}

if (-not $ok) {
  Write-Host "ASSIGN_GAVE_UP"
  Disconnect-ExchangeOnline -Confirm:$false
  exit 2
}

$allow = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $EvidenceUpn)
$allow | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Evid "test-allow.json")
$allowIn = (@($allow | Where-Object { $_.RoleName -like "*Calendars.ReadWrite*" -and $_.InScope -eq $true })).Count -gt 0

$denied = $null
$denyIdentity = "wathefni-rbac-deny-probe@$domain"
try {
  $mbx = Get-Mailbox -Identity $denyIdentity -ErrorAction SilentlyContinue
  if (-not $mbx) {
    $mbx = New-Mailbox -Shared -Name "wathefni-rbac-deny-probe" -DisplayName "Wathefni RBAC Deny Probe" -Alias "wathefni-rbac-deny-probe"
  }
  $denied = [string]$mbx.PrimarySmtpAddress
} catch {
  Write-Host ("WARN deny mailbox: " + $_.Exception.Message)
  $other = Get-Mailbox -ResultSize 50 | Where-Object { [string]$_.PrimarySmtpAddress -ne $EvidenceUpn } | Select-Object -First 1
  if ($other) { $denied = [string]$other.PrimarySmtpAddress }
}

$denyIn = $null
$denyRows = @()
if ($denied) {
  $deny = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $denied)
  $deny | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Evid "test-deny.json")
  $denyIn = (@($deny | Where-Object { $_.RoleName -like "*Calendars.ReadWrite*" -and $_.InScope -eq $true })).Count -gt 0
  $denyRows = @($deny | Select-Object RoleName, GrantedPermissions, AllowedResourceScope, ScopeType, InScope)
  "WATHEFNI_M365_DENIED_UPN=$denied" | Set-Content (Join-Path $Evid "denied-upn.env")
}

$result = [ordered]@{
  evidence_upn = $EvidenceUpn
  denied_upn = $denied
  scope_type = $used
  administrative_unit_id = $AuId
  role = "Application Calendars.ReadWrite"
  allow_calendars_inscope = $allowIn
  deny_calendars_inscope = $denyIn
  allow_rows = @($allow | Select-Object RoleName, GrantedPermissions, AllowedResourceScope, ScopeType, InScope)
  deny_rows = $denyRows
  commands = @(
    "Enable-OrganizationCustomization",
    "New-ServicePrincipal -AppId <clientId> -ObjectId <enterpriseObjectId> -DisplayName 'Wathefni Platform Integration'",
    "New-MgDirectoryAdministrativeUnit -DisplayName 'Wathefni-Calendar-Evidence' + add evidence user",
    "New-ManagementRoleAssignment -App <enterpriseObjectId> -Role 'Application Calendars.ReadWrite' -RecipientAdministrativeUnitScope <auId>",
    "Test-ServicePrincipalAuthorization -Identity <enterpriseObjectId> -Resource '$EvidenceUpn'"
  )
}
$result | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Evid "rbac-results.json")
Write-Host ("ALLOW_INSCOPE=" + $allowIn)
Write-Host ("DENY_INSCOPE=" + $denyIn)
Write-Host ("DENIED_UPN=" + $denied)
Write-Host ("SCOPE_TYPE=" + $used)
Write-Host "RBAC_SETUP_DONE"
Disconnect-ExchangeOnline -Confirm:$false
