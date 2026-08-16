# Paste into Azure Cloud Shell (PowerShell) — MicrosoftTeams works there (not on Mac Homebrew pwsh).
# Creates a user-scoped Application Access Policy only. Never grants -Global.
# Does NOT change Exchange RBACfA calendar settings.

$AppId = "16f7135a-b7e8-4ac8-adfe-2d2b13de3131"
$EvidenceUserId = "dcb6b7dd-8509-4a20-8069-ec0de9445dd7"
$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
$PolicyIdentity = "Wathefni-OnlineMeetings-Evidence"

Import-Module MicrosoftTeams
Connect-MicrosoftTeams

$existing = Get-CsApplicationAccessPolicy -Identity $PolicyIdentity -ErrorAction SilentlyContinue
if (-not $existing) {
  New-CsApplicationAccessPolicy `
    -Identity $PolicyIdentity `
    -AppIds $AppId `
    -Description "Wathefni OnlineMeetings for evidence organizer only — not global"
}

Grant-CsApplicationAccessPolicy -PolicyName $PolicyIdentity -Identity $EvidenceUserId

Get-CsOnlineUser -Identity $EvidenceUpn |
  Select-Object UserPrincipalName, Identity, ApplicationAccessPolicy |
  Format-List

Write-Host "IMPORTANT: Do NOT run Grant-CsApplicationAccessPolicy -Global"
Write-Host "Wait 1-5 minutes, then re-run prove-m365-teams-meeting.py on the VPS."
