#Requires -Modules Microsoft.Graph.Authentication, ExchangeOnlineManagement
<#
.SYNOPSIS
  Create a SEPARATE Entra app/SP for Wathefni outbound email (Mail.Send only).
  Does NOT reuse the Calendar/Teams client ID.
  Grants Graph application Mail.Send only (no Mail.Read / Mail.ReadWrite).
  Configures Exchange RBACfA "Application Mail.Send" scoped to a mail-evidence AU
  containing only the Wathefni evidence mailbox.

Order (required):
  1) Create app + upload cert + Mail.Send role assignment
  2) Create AU + Exchange RBAC scope + outside-scope deny proof
  3) ONLY THEN configure WATHEFNI_M365_MAIL_* on the orchestrator
#>
param(
  [string]$TenantId = "ffd171d7-94a7-41a2-a38a-b9bc3ba4a082",
  [string]$CalendarClientId = "16f7135a-b7e8-4ac8-adfe-2d2b13de3131",
  [string]$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
  [string]$DeniedUpn = "wathefni-rbac-deny-probe@wathefni.onmicrosoft.com",
  [string]$AuDisplayName = "Wathefni-Mail-Evidence",
  [string]$AppDisplayName = "Wathefni Email Send",
  [string]$PublicCerPath = "",
  [string]$OutDir = "",
  [switch]$SkipAppCreate,
  [string]$ExistingAppId = "",
  [string]$ExistingSpObjectId = ""
)

$ErrorActionPreference = "Stop"
if (-not $OutDir) {
  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $OutDir = Join-Path (Split-Path $PSScriptRoot -Parent) "ops" "evidence" "hybrid-email-m365-mail-sp-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Write-Host "OUT=$OutDir"

function Write-Json($Path, $Obj) {
  $Obj | ConvertTo-Json -Depth 12 | Set-Content -Path $Path -Encoding utf8
}

if (-not $PublicCerPath) {
  throw "PublicCerPath is required (PEM or CER public cert for the NEW mail SP)."
}
if (-not (Test-Path $PublicCerPath)) {
  throw "PublicCerPath not found: $PublicCerPath"
}

# Load public cert bytes + compute customKeyIdentifier (SHA1 of cert DER) for Graph keyCredentials
$rawText = Get-Content -Raw $PublicCerPath
if ($rawText -match "BEGIN CERTIFICATE") {
  $b64 = (($rawText -split "-----") | Where-Object { $_ -match "^\s*[A-Za-z0-9+/=\r\n]+\s*$" } | Select-Object -First 1)
  $b64 = ($b64 -replace "\s", "")
  $certBytes = [Convert]::FromBase64String($b64)
} else {
  $certBytes = [System.IO.File]::ReadAllBytes($PublicCerPath)
}
# macOS/.NET: X509Certificate2 is immutable — use constructor, not Import()
$cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($certBytes)
$keyId = [Guid]::NewGuid().ToString()
$customKeyIdBytes = $cert.GetCertHash()
$customKeyIdB64 = [Convert]::ToBase64String($customKeyIdBytes)
$certB64 = [Convert]::ToBase64String($cert.RawData)
Write-Host ("CERT_THUMBPRINT=" + $cert.Thumbprint)
Write-Json (Join-Path $OutDir "mail-cert-public-meta.json") @{
  thumbprint = $cert.Thumbprint
  subject = $cert.Subject
  notBefore = $cert.NotBefore.ToUniversalTime().ToString("o")
  notAfter = $cert.NotAfter.ToUniversalTime().ToString("o")
  keyId = $keyId
}

Write-Host "Connecting Microsoft Graph (interactive browser)..."
Import-Module Microsoft.Graph.Authentication
Connect-MgGraph -TenantId $TenantId -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All","Directory.Read.All","AdministrativeUnit.ReadWrite.All","User.Read.All" -NoWelcome

$AppId = $ExistingAppId
$SpObjectId = $ExistingSpObjectId
$AppObjectId = $null

if (-not $SkipAppCreate -and -not $AppId) {
  $keyCredential = @{
    type = "AsymmetricX509Cert"
    usage = "Verify"
    keyId = $keyId
    displayName = "wathefni-m365-mail"
    customKeyIdentifier = $customKeyIdB64
    key = $certB64
  }
  $createBody = @{
    displayName = $AppDisplayName
    signInAudience = "AzureADMyOrg"
    keyCredentials = @($keyCredential)
    requiredResourceAccess = @()
  }
  $created = Invoke-MgGraphRequest -Method POST -Uri "https://graph.microsoft.com/v1.0/applications" -Body ($createBody | ConvertTo-Json -Depth 8) -ContentType "application/json"
  Write-Json (Join-Path $OutDir "entra-application-created.json") $created
  $AppId = [string]$created.appId
  $AppObjectId = [string]$created.id
  Write-Host "Created application appId=$AppId"

  # Ensure enterprise SP exists
  $spCreate = Invoke-MgGraphRequest -Method POST -Uri "https://graph.microsoft.com/v1.0/servicePrincipals" -Body (@{ appId = $AppId } | ConvertTo-Json) -ContentType "application/json"
  Write-Json (Join-Path $OutDir "entra-service-principal-created.json") $spCreate
  $SpObjectId = [string]$spCreate.id
} else {
  if (-not $AppId) { throw "ExistingAppId required when -SkipAppCreate" }
  $apps = Invoke-MgGraphRequest -Method GET -Uri ("https://graph.microsoft.com/v1.0/applications?`$filter=appId eq '{0}'" -f $AppId)
  $AppObjectId = [string]$apps.value[0].id
  if (-not $SpObjectId) {
    $sps = Invoke-MgGraphRequest -Method GET -Uri ("https://graph.microsoft.com/v1.0/servicePrincipals?`$filter=appId eq '{0}'" -f $AppId)
    $SpObjectId = [string]$sps.value[0].id
  }
  # Upload/replace key credential
  $patchBody = @{
    keyCredentials = @(
      @{
        type = "AsymmetricX509Cert"
        usage = "Verify"
        keyId = $keyId
        displayName = "wathefni-m365-mail"
        customKeyIdentifier = $customKeyIdB64
        key = $certB64
      }
    )
  }
  Invoke-MgGraphRequest -Method PATCH -Uri "https://graph.microsoft.com/v1.0/applications/$AppObjectId" -Body ($patchBody | ConvertTo-Json -Depth 8) -ContentType "application/json" | Out-Null
  Write-Host "Patched keyCredentials on existing app"
}

if ($AppId -eq $CalendarClientId) {
  throw "REFUSING: mail AppId must differ from Calendar/Teams client id"
}

Write-Json (Join-Path $OutDir "entra-service-principal.json") @{
  appId = $AppId
  objectId = $SpObjectId
  applicationObjectId = $AppObjectId
  displayName = $AppDisplayName
  calendarClientId = $CalendarClientId
  distinctFromCalendar = ($AppId -ne $CalendarClientId)
}

# --- Graph application permission Mail.Send ONLY ---
$graphSp = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals?`$filter=appId eq '00000003-0000-0000-c000-000000000000'&`$select=id,appId,displayName"
$graphSpId = [string]$graphSp.value[0].id
$roles = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$graphSpId/appRoles"
$mailSend = $roles.value | Where-Object { $_.value -eq "Mail.Send" -and $_.isEnabled } | Select-Object -First 1
$mailRead = $roles.value | Where-Object { $_.value -eq "Mail.Read" -and $_.isEnabled } | Select-Object -First 1
$mailReadWrite = $roles.value | Where-Object { $_.value -eq "Mail.ReadWrite" -and $_.isEnabled } | Select-Object -First 1
if (-not $mailSend) { throw "Mail.Send app role not found on Microsoft Graph" }
Write-Json (Join-Path $OutDir "mail-send-approle.json") $mailSend

# Update application requiredResourceAccess to declare Mail.Send only
$rra = @{
  requiredResourceAccess = @(
    @{
      resourceAppId = "00000003-0000-0000-c000-000000000000"
      resourceAccess = @(
        @{ id = $mailSend.id; type = "Role" }
      )
    }
  )
}
Invoke-MgGraphRequest -Method PATCH -Uri "https://graph.microsoft.com/v1.0/applications/$AppObjectId" -Body ($rra | ConvertTo-Json -Depth 8) -ContentType "application/json" | Out-Null

# Admin consent via appRoleAssignment on the SP
$existing = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignments"
Write-Json (Join-Path $OutDir "existing-approle-assignments-before.json") $existing
$already = @($existing.value) | Where-Object { $_.appRoleId -eq $mailSend.id -and $_.resourceId -eq $graphSpId }
$banned = @($existing.value) | Where-Object {
  ($mailRead -and $_.appRoleId -eq $mailRead.id) -or ($mailReadWrite -and $_.appRoleId -eq $mailReadWrite.id)
}
if ($banned) {
  throw "REFUSING: Mail.Read / Mail.ReadWrite already assigned to mail SP"
}
$permResult = [ordered]@{ already = [bool]$already; granted_now = $false; permission = "Mail.Send" }
if (-not $already) {
  $body = @{
    principalId = $SpObjectId
    resourceId = $graphSpId
    appRoleId = $mailSend.id
  }
  $createdAssign = Invoke-MgGraphRequest -Method POST -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignments" -Body ($body | ConvertTo-Json) -ContentType "application/json"
  Write-Json (Join-Path $OutDir "approle-assignment-created.json") $createdAssign
  $permResult.granted_now = $true
  $permResult.assignment_id = $createdAssign.id
} else {
  $permResult.assignment_id = $already.id
}
Write-Json (Join-Path $OutDir "permission-grant.json") $permResult

# Re-read assignments; assert only Mail.Send (from Graph resource)
$after = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SpObjectId/appRoleAssignments"
$graphAssignments = @($after.value) | Where-Object { $_.resourceId -eq $graphSpId }
$roleValues = @()
foreach ($a in $graphAssignments) {
  $matchRole = $roles.value | Where-Object { $_.id -eq $a.appRoleId } | Select-Object -First 1
  $roleValues += [string]$matchRole.value
}
Write-Json (Join-Path $OutDir "graph-approle-values.json") @{ values = $roleValues; assignments = $graphAssignments }
if ($roleValues -contains "Mail.Read" -or $roleValues -contains "Mail.ReadWrite") {
  throw "REFUSING: unexpected Mail.Read/Mail.ReadWrite on mail SP"
}
if ($roleValues -notcontains "Mail.Send") {
  throw "Mail.Send not present on mail SP after grant"
}

# --- Administrative Unit for mail evidence mailbox only ---
$evidenceUser = Invoke-MgGraphRequest -Method GET -Uri ("https://graph.microsoft.com/v1.0/users?`$filter=userPrincipalName eq '{0}'" -f $EvidenceUpn)
if (-not $evidenceUser.value) { throw "evidence_user_not_found:$EvidenceUpn" }
$evidenceUserId = [string]$evidenceUser.value[0].id

$auList = Invoke-MgGraphRequest -Method GET -Uri ("https://graph.microsoft.com/v1.0/directory/administrativeUnits?`$filter=displayName eq '{0}'" -f $AuDisplayName)
$au = $null
if ($auList.value) {
  $au = $auList.value[0]
  Write-Host "Administrative unit already exists"
} else {
  $au = Invoke-MgGraphRequest -Method POST -Uri "https://graph.microsoft.com/v1.0/directory/administrativeUnits" -Body (@{
    displayName = $AuDisplayName
    description = "Wathefni outbound email evidence mailbox scope (Mail.Send RBACfA)"
    visibility = "Public"
  } | ConvertTo-Json) -ContentType "application/json"
  Write-Host "Created administrative unit"
}
$AuId = [string]$au.id

$members = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/v1.0/directory/administrativeUnits/$AuId/members"
$alreadyMember = $false
foreach ($m in @($members.value)) {
  if ($m.id -eq $evidenceUserId) { $alreadyMember = $true; break }
}
if (-not $alreadyMember) {
  $ref = @{ "@odata.id" = "https://graph.microsoft.com/v1.0/users/$evidenceUserId" }
  Invoke-MgGraphRequest -Method POST -Uri "https://graph.microsoft.com/v1.0/directory/administrativeUnits/$AuId/members/`$ref" -Body ($ref | ConvertTo-Json) -ContentType "application/json" | Out-Null
  Write-Host "Added evidence user to mail AU"
}
Write-Json (Join-Path $OutDir "entra-admin-unit.json") @{
  administrativeUnitId = $AuId
  administrativeUnitName = $AuDisplayName
  evidenceUserId = $evidenceUserId
  evidenceUpn = $EvidenceUpn
}

Disconnect-MgGraph | Out-Null
Write-Host "GRAPH_APP_AND_AU_READY"

# --- Exchange Online RBACfA Application Mail.Send ---
Write-Host "Connecting Exchange Online (interactive browser)..."
Import-Module ExchangeOnlineManagement
Connect-ExchangeOnline -UserPrincipalName $EvidenceUpn -ShowBanner:$false

try { Enable-OrganizationCustomization -ErrorAction Stop } catch { Write-Host ("Org customization: " + $_.Exception.Message) }

$existingSp = @(Get-ServicePrincipal -ErrorAction SilentlyContinue | Where-Object { $_.AppId -eq $AppId -or $_.ObjectId -eq $SpObjectId })
if ($existingSp.Count -eq 0) {
  New-ServicePrincipal -AppId $AppId -ObjectId $SpObjectId -DisplayName $AppDisplayName | Out-Null
  Write-Host "Created Exchange service principal pointer"
} else {
  Write-Host "Exchange service principal pointer already exists"
}

$role = "Application Mail.Send"
$allMail = @(Get-ManagementRoleAssignment -Role $role -ErrorAction SilentlyContinue)
$match = @($allMail | Where-Object {
  $_.RoleAssigneeName -eq $SpObjectId -or
  $_.RoleAssigneeName -eq $AppDisplayName -or
  ("$($_.RoleAssignee)" -eq $SpObjectId)
})
if ($match.Count -eq 0) {
  New-ManagementRoleAssignment -App $SpObjectId -Role $role -RecipientAdministrativeUnitScope $AuId | Out-Null
  Write-Host "Created AU-scoped Application Mail.Send assignment"
} else {
  foreach ($a in $match) {
    try {
      Set-ManagementRoleAssignment -Identity $a.Identity -RecipientAdministrativeUnitScope $AuId | Out-Null
    } catch {
      Write-Host ("WARN set assignment scope: " + $_.Exception.Message)
    }
  }
  Write-Host "Mail.Send role assignment present; AU scope refreshed if supported"
}

Start-Sleep -Seconds 5

$allow = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $EvidenceUpn)
Write-Json (Join-Path $OutDir "test-allow.json") $allow
$allowRows = @($allow | Where-Object { $_.RoleName -like "*Mail.Send*" })
$allowInScope = (@($allowRows | Where-Object { $_.InScope -eq $true })).Count -gt 0

$deny = @(Test-ServicePrincipalAuthorization -Identity $SpObjectId -Resource $DeniedUpn)
Write-Json (Join-Path $OutDir "test-deny.json") $deny
$denyRows = @($deny | Where-Object { $_.RoleName -like "*Mail.Send*" })
$denyInScope = (@($denyRows | Where-Object { $_.InScope -eq $true })).Count -gt 0

$assignMeta = @(Get-ManagementRoleAssignment -Role $role -ErrorAction SilentlyContinue | Where-Object {
  $_.RoleAssigneeName -eq $SpObjectId -or $_.RoleAssigneeName -eq $AppDisplayName -or ("$($_.RoleAssignee)" -eq $SpObjectId)
} | Select-Object Identity, Role, RoleAssignee, RoleAssigneeName, RecipientWriteScope, CustomResourceScope, WhenCreatedUTC)

$result = [ordered]@{
  evidence_upn = $EvidenceUpn
  denied_upn = $DeniedUpn
  scope_type = "RecipientAdministrativeUnitScope"
  administrative_unit_id = $AuId
  administrative_unit_name = $AuDisplayName
  role = $role
  graph_permission = "Mail.Send"
  graph_permissions_forbidden = @("Mail.Read", "Mail.ReadWrite")
  app_id = $AppId
  sp_object_id = $SpObjectId
  distinct_from_calendar = ($AppId -ne $CalendarClientId)
  allow_mail_send_inscope = $allowInScope
  deny_mail_send_inscope = $denyInScope
  assignments = $assignMeta
  note = "Configure WATHEFNI_M365_MAIL_* only after allow_mail_send_inscope=true and deny_mail_send_inscope=false."
}
Write-Json (Join-Path $OutDir "rbac-results.json") $result
"WATHEFNI_M365_MAIL_CLIENT_ID=$AppId" | Set-Content (Join-Path $OutDir "mail-env.partial.env")
"WATHEFNI_M365_MAIL_TENANT_ID=$TenantId" | Add-Content (Join-Path $OutDir "mail-env.partial.env")
"WATHEFNI_M365_MAIL_EVIDENCE_UPN=$EvidenceUpn" | Add-Content (Join-Path $OutDir "mail-env.partial.env")
"WATHEFNI_M365_MAIL_DENIED_UPN=$DeniedUpn" | Add-Content (Join-Path $OutDir "mail-env.partial.env")
"WATHEFNI_M365_MAIL_AU_ID=$AuId" | Add-Content (Join-Path $OutDir "mail-env.partial.env")

Write-Host ("ALLOW_INSCOPE=" + $allowInScope)
Write-Host ("DENY_INSCOPE=" + $denyInScope)
Write-Host ("MAIL_APP_ID=" + $AppId)
Write-Host ("MAIL_SP_OBJECT_ID=" + $SpObjectId)
Write-Host ("AU_ID=" + $AuId)
if (-not $allowInScope) { Write-Host "WARN: evidence mailbox not yet InScope for Application Mail.Send" }
if ($denyInScope) { throw "FAIL: outside-scope mailbox unexpectedly InScope" }
Write-Host "MAIL_SP_RBAC_SETUP_DONE"
Disconnect-ExchangeOnline -Confirm:$false
