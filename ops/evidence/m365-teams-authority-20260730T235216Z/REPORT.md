# Microsoft Teams authority — diagnosis + narrow OnlineMeetings model

**Stamp:** `20260730T235216Z`  
**Overall:** **FAIL** (blocked on Teams Application Access Policy — requires your Cloud Shell approval)  
**Calendar RBACfA:** **untouched / still PASS**

---

## Diagnosis

### 1) Evidence mailbox Teams license — PASS

| Field | Value |
|---|---|
| UPN | `ABDULAZIZALMULLA@wathefni.onmicrosoft.com` |
| Object id | `dcb6b7dd-8509-4a20-8069-ec0de9445dd7` |
| SKU | `O365_BUSINESS_ESSENTIALS` |
| `TEAMS1` | **Success** |
| `MCOSTANDARD` | **Success** |
| Account enabled | true |

Delegated `/me/onlineMeetings` create returns a real `joinWebUrl` → mailbox **can** create Teams meetings.

### 2) `allowedOnlineMeetingProviders` — empty

| Caller | `allowedOnlineMeetingProviders` | `defaultOnlineMeetingProvider` |
|---|---|---|
| App-only (RBACfA calendar read) | `[]` | `unknown` |
| Delegated `/me/calendar` | `[]` | `unknown` |

`teamsForBusiness` is **not** listed as a calendar-embedded provider for this mailbox.

### 3) Event payload behavior — why `isOnlineMeeting=false`

Wathefni / prove scripts send:

```json
{
  "isOnlineMeeting": true,
  "onlineMeetingProvider": "teamsForBusiness"
}
```

Graph accepts the calendar event (**201**) but returns:

- `isOnlineMeeting: false`
- `onlineMeetingProvider: unknown`
- `onlineMeeting: null`

**Root cause:** when `allowedOnlineMeetingProviders` is empty, Graph **silently ignores** online-meeting flags on calendar events. This is independent of Exchange RBACfA (calendar CRUD works). Teams join links must be created via **Online Meetings API**, then attached to the calendar invite.

### 4) Direct Online Meetings API — required

| Step | Result |
|---|---|
| Before Graph app role | `403 Missing required permissions` |
| After `OnlineMeetings.ReadWrite.All` admin consent | Token `roles: ["OnlineMeetings.ReadWrite.All"]` |
| `POST /users/{upn}/onlineMeetings` | `400` — app-only requires **GUID**, not UPN |
| `POST /users/{evidence-guid}/onlineMeetings` | `403` **`No application access policy found for this app … on the user`** |

→ Narrow model confirmed: **OnlineMeetings.ReadWrite.All + user-scoped Application Access Policy**.

---

## What was implemented (code + partial admin)

### Done without changing Calendar RBACfA

| Item | Status |
|---|---|
| Assign Graph app role `OnlineMeetings.ReadWrite.All` to SP `46f5549d-4382-48fa-9c20-aff2f13451d5` | **DONE** (assignment id `nVT1RoJD-kicIK_y8TRR1ebhMqBFvGdPlZy-DUS-Ll0`) |
| Code: create OM → link join URL on RBACfA calendar event (no `isOnlineMeeting` dependency) | **DONE** |
| Code: reschedule same calendar event id; keep join URL; optional OM PATCH | **DONE** |
| Code: cancel calendar (+ OM when id known) | **DONE** |
| Unit tests `test_interview_microsoft_calendar.py` | **PASS** |
| Deploy helpers to `/opt/wathefni/orchestrator` | **DONE** |

### Blocked on your machine / needs your approval

`Connect-MicrosoftTeams` **fails on Mac Homebrew PowerShell** (`kernel32.dll` native dependency). AAP must be created in **Azure Cloud Shell** (or Windows PowerShell).

---

## Exact steps requiring your approval

### A) Already completed (Graph)

App role `OnlineMeetings.ReadWrite.All` is assigned and present in app-only token `roles`.

### B) You must run — Teams Application Access Policy (user-scoped only)

1. Open [Azure Cloud Shell](https://shell.azure.com) → **PowerShell**.
2. Paste / run `wathefni-orchestrator/m365-teams-aap-cloudshell.ps1` (copy also in this evidence folder):

```powershell
$AppId = "16f7135a-b7e8-4ac8-adfe-2d2b13de3131"
$EvidenceUserId = "dcb6b7dd-8509-4a20-8069-ec0de9445dd7"
$EvidenceUpn = "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
$PolicyIdentity = "Wathefni-OnlineMeetings-Evidence"

Import-Module MicrosoftTeams
Connect-MicrosoftTeams

$existing = Get-CsApplicationAccessPolicy -Identity $PolicyIdentity -ErrorAction SilentlyContinue
if (-not $existing) {
  New-CsApplicationAccessPolicy -Identity $PolicyIdentity -AppIds $AppId `
    -Description "Wathefni OnlineMeetings for evidence organizer only — not global"
}
Grant-CsApplicationAccessPolicy -PolicyName $PolicyIdentity -Identity $EvidenceUserId
Get-CsOnlineUser -Identity $EvidenceUpn | Select UserPrincipalName, ApplicationAccessPolicy
```

3. **Do not** run `Grant-CsApplicationAccessPolicy -Global`.
4. Wait 1–5 minutes for policy propagation.
5. Tell me to re-run `prove-m365-teams-meeting.py`.

### Portal alternative (same outcome)

Teams admin center → **Users** → evidence user → Policies → Application access policy → assign policy that allows app `16f7135a-b7e8-4ac8-adfe-2d2b13de3131` only (no tenant-wide grant).

---

## Live prove (current — before AAP)

`prove-m365-teams-meeting.py` on prod:

| Proof | Result |
|---|---|
| Cert token mint | **PASS** |
| Teams create + joinUrl | **FAIL** — AAP missing |
| Calendar event linked | **FAIL** (blocked) |
| Attendees / timezone / reschedule / cancel | **FAIL** (blocked) |
| Outside-AAP OM deny (deny-probe GUID) | **PASS** (403 no AAP) |
| Outside-AU calendar deny | **PASS** (403) — RBACfA intact |
| Assistant executor wired to microsoft_teams | **PASS** (code path) |

Summary: `passed=4 failed=6 verdict=FAIL`

---

## Files

| Path | Purpose |
|---|---|
| `interview_microsoft_calendar.py` | OM-first Teams + calendar link |
| `interview_service.py` | Persist `online_meeting_id` / reschedule-cancel wiring |
| `prove-m365-teams-meeting.py` | Live matrix |
| `test_interview_microsoft_calendar.py` | Unit tests |
| `m365-teams-online-meetings-setup.ps1` | Graph permission + (Teams policy when module works) |
| `m365-teams-aap-cloudshell.ps1` | **Your AAP grant script** |
| `platform_connection_c6.py` | Documents `OnlineMeetings.ReadWrite.All` |

Evidence: `ops/evidence/m365-teams-authority-20260730T235216Z/`

---

## Verdict

| Area | Status |
|---|---|
| License / manual Teams capability | **PASS** |
| Why calendar `isOnlineMeeting=false` | **Explained** (empty providers → flags ignored) |
| Narrow OM permission grant | **PASS** |
| User-scoped AAP | **PENDING your Cloud Shell run** |
| Full Teams + Assistant matrix | **FAIL until AAP** |
| Calendar RBACfA AU scope | **Preserved PASS** |
