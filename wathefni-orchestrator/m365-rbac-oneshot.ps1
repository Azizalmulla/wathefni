$ErrorActionPreference = "Continue"
Import-Module ExchangeOnlineManagement

$Evid = $env:EVID
$SpObjectId = $env:SP
$AuId = $env:AU
$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
$domain = "wathefni.onmicrosoft.com"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

Write-Host ("ATTEMPT_START utc=" + $stamp)
Write-Host "Connecting Exchange Online (device code)..."
Connect-ExchangeOnline -Device -ShowBanner:$false

$cfg = Get-OrganizationConfig
Write-Host ("IsDehydrated=" + $cfg.IsDehydrated)

$assignOk = $false
$scopeType = $null
$assignError = $null

try {
  New-ManagementRoleAssignment -App $SpObjectId -Role "Application Calendars.ReadWrite" -RecipientAdministrativeUnitScope $AuId -ErrorAction Stop | Out-Null
  $assignOk = $true
  $scopeType = "RecipientAdministrativeUnitScope"
  Write-Host "ASSIGN_OK via RecipientAdministrativeUnitScope"
} catch {
  $assignError = [string]$_.Exception.Message
  Write-Host ("ASSIGN_AU_FAIL :: " + $assignError)
  # One fallback path only if AU fails for a non-org-customization reason
  if ($assignError -notmatch "Enable-OrganizationCustomization") {
    try {
      $ScopeName = "Wathefni-Calendar-Evidence"
      $filter = "PrimarySmtpAddress -eq '$EvidenceUpn'"
      if (-not (Get-ManagementScope -Identity $ScopeName -ErrorAction SilentlyContinue)) {
        New-ManagementScope -Name $ScopeName -RecipientRestrictionFilter $filter -ErrorAction Stop | Out-Null
      }
      New-ManagementRoleAssignment -App $SpObjectId -Role "Application Calendars.ReadWrite" -CustomResourceScope $ScopeName -ErrorAction Stop | Out-Null
      $assignOk = $true
      $scopeType = "CustomResourceScope"
      $assignError = $null
      Write-Host "ASSIGN_OK via CustomResourceScope"
    } catch {
      $assignError = [string]$_.Exception.Message
      Write-Host ("ASSIGN_SCOPE_FAIL :: " + $assignError)
    }
  }
}

$record = [ordered]@{
  attempt_utc = $stamp
  is_dehydrated = [bool]$cfg.IsDehydrated
  assign_ok = $assignOk
  scope_type = $scopeType
  error = $assignError
  evidence_upn = $EvidenceUpn
  sp_object_id = $SpObjectId
  administrative_unit_id = $AuId
  role = "Application Calendars.ReadWrite"
}

if (-not $assignOk) {
  $record | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Evid "rbac-oneshot-result.json")
  Write-Host "ONESHOT_FAILED"
  Write-Host ("ERROR=" + $assignError)
  Disconnect-ExchangeOnline -Confirm:$false
  if ($assignError -match "Enable-OrganizationCustomization") { exit 3 }
  exit 2
}

# Authorization proofs
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

$record.allow_calendars_inscope = $allowIn
$record.deny_calendars_inscope = $denyIn
$record.denied_upn = $denied
$record.allow_rows = @($allow | Select-Object RoleName, GrantedPermissions, AllowedResourceScope, ScopeType, InScope)
$record.deny_rows = $denyRows
$record | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Evid "rbac-oneshot-result.json")

Write-Host ("ALLOW_INSCOPE=" + $allowIn)
Write-Host ("DENY_INSCOPE=" + $denyIn)
Write-Host ("DENIED_UPN=" + $denied)
Write-Host "ONESHOT_ASSIGN_OK"
Disconnect-ExchangeOnline -Confirm:$false
