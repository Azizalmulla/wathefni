# Assistant + Calendar hardening — Microsoft RBAC + schedule authority

**Stamp:** `20260730T214942Z`  
**Overall verdict:** **FAIL** (Microsoft live Teams/calendar proof still blocked)  
**Assistant schedule-path hardening:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)

---

## Exact Microsoft blocker

| Field | Value |
|---|---|
| **Blocked command** | `New-ManagementRoleAssignment -App <spObjectId> -Role "Application Calendars.ReadWrite" -RecipientAdministrativeUnitScope <auId>` |
| **Role** | `Application Calendars.ReadWrite` (Exchange RBACfA) |
| **Service principal ObjectId** | `46f5549d-4382-48fa-9c20-aff2f13451d5` |
| **AppId** | `16f7135a-b7e8-4ac8-adfe-2d2b13de3131` |
| **AU** | `Wathefni-Calendar-Evidence` (`9d4e6a0e-47af-4603-a8f2-532e45911d40`) |
| **Evidence mailbox** | `ABDULAZIZALMULLA@wathefni.onmicrosoft.com` |
| **Last successful pre-step** | Cert app-only Graph token mint (**PASS**) |
| **Org customization** | `IsDehydrated=False` (already enabled) |
| **Historical assign error (2026-07-29T19:59:20Z)** | *The command you tried to run isn't currently allowed in your organization. To run this command, you first need to run the command: Enable-OrganizationCustomization.* |
| **Propagation status now (2026-07-30T21:46Z / 21:49Z)** | **Not propagated / not assigned.** Graph `POST /users/{evidence}/events` → **403** `ErrorAccessDenied` |
| **EXO cert admin connect** | **Unauthorized** (app lacks Exchange.ManageAsApp for unattended PowerShell) |

**Interpretation:** Wathefni certificate authentication works. Exchange RBACfA role assignment for `Application Calendars.ReadWrite` scoped to AU `Wathefni-Calendar-Evidence` is still missing or ineffective. Live Teams meeting creation cannot complete until a Global Admin finishes the assignment via interactive Exchange Online.

**Not used (by design):** Application Access Policy — would require tenant-wide Entra `Calendars.ReadWrite` first, defeating scoped-only authority.

---

## Portal / PowerShell steps required (human Global Admin)

1. Connect interactively (device code):

```powershell
Import-Module ExchangeOnlineManagement
Connect-ExchangeOnline -Device
Get-OrganizationConfig | Select IsDehydrated   # expect False
```

2. Ensure Exchange service principal pointer exists for app `16f7135a-b7e8-4ac8-adfe-2d2b13de3131` / object `46f5549d-4382-48fa-9c20-aff2f13451d5`.

3. Assign scoped calendar role (AU already exists: `Wathefni-Calendar-Evidence`):

```powershell
New-ManagementRoleAssignment `
  -App 46f5549d-4382-48fa-9c20-aff2f13451d5 `
  -Role "Application Calendars.ReadWrite" `
  -RecipientAdministrativeUnitScope 9d4e6a0e-47af-4603-a8f2-532e45911d40
```

4. Verify:

```powershell
Test-ServicePrincipalAuthorization `
  -Identity 46f5549d-4382-48fa-9c20-aff2f13451d5 `
  -Resource "ABDULAZIZALMULLA@wathefni.onmicrosoft.com"
# Expect Application Calendars.ReadWrite InScope=True
```

5. Re-run live proof on the host:

```bash
source /root/.openclaw/secrets/wathefni-m365.production.env
export WATHEFNI_M365_CERT_BUNDLE_PATH=/root/.openclaw/secrets/wathefni-m365.bundle.pem
cd /opt/wathefni/orchestrator && .venv/bin/python prove-m365-live-calendar.py
```

Scripts already in tree: `m365-rbac-oneshot.ps1`, `m365-rbac-setup.ps1`, `prove-m365-live-calendar.py`.

---

## Required Microsoft live proof checklist (current status)

| Proof | Status |
|---|---|
| Microsoft certificate authentication succeeds | **PASS** |
| Scoped Exchange/Graph permissions effective for intended mailbox only | **FAIL** (403 AccessDenied; assignment not effective) |
| Wathefni schedules interview + creates Teams link | **BLOCKED** |
| Calendar event, interview record, attendees, timezone, Teams link consistent | **BLOCKED** |
| Invitation email delivered | **BLOCKED** |
| Reschedule updates event/interview/comms | **BLOCKED** |
| Cancel removes meeting + audit trail | **BLOCKED** (code path wired; live Graph cancel unproven) |
| Tenant isolation / unauthorized mailbox denied | **BLOCKED** (deny probe needs successful allow path first) |

---

## Assistant hardening shipped (PASS)

| Gap | Change |
|---|---|
| Migrate schedule off legacy `gog` | `_schedule_interview_executor` → `interview_service.schedule_interview` |
| One workflow authority | schedule / reschedule / cancel all via `interview_service` + shared `sync_provider_for_interview` |
| Microsoft provider wiring | `interview_microsoft_calendar.py`; `microsoft_teams` meeting type; `_sync_microsoft_for_interview` |
| Stop/cancel late external success | Turn cancel no longer reports a completed tool as `cancelled`; appends “Stopped further steps…” after truthful result |
| Idempotency / partial / retry | Preserved from prior workflow card + interview operation keys |

### Files changed
- `wathefni-orchestrator/interview_microsoft_calendar.py` (**new**)
- `wathefni-orchestrator/interview_service.py`
- `wathefni-orchestrator/interview_lifecycle.py`
- `wathefni-orchestrator/action_registry.py`
- `wathefni-orchestrator/tool_call_orchestrator.py`
- `wathefni-orchestrator/assistant_capability_catalog.py`
- `wathefni-orchestrator/test_assistant_calendar_hardening.py`
- `ops/deploy-assistant-calendar-hardening.sh`

### Tests (prod)
- `test_assistant_calendar_hardening.py` → **PASS**
- `smoke-test-toolcall-orchestrator.py` → **PASS**
- Schedule authority JSON: `schedule_uses_interview_service=true`, `schedule_no_run_gog=true`, `microsoft_sync_wired=true`

---

## Deployment / rollback

- **Deploy:** `ops/deploy-assistant-calendar-hardening.sh`
- **Backup:** `/opt/wathefni/backups/production-pre-assistant-calendar-hardening-20260730T214942Z`
- **Rollback:** `$BACKUP/ROLLBACK.sh`
- **Evidence:** `ops/evidence/assistant-calendar-hardening-20260730T214942Z/`

---

## PASS / FAIL

| Check | Result |
|---|---|
| Cert auth | **PASS** |
| Exchange RBACfA assignment / Graph calendar write | **FAIL** (still blocked) |
| Full Teams interview live matrix | **FAIL** / **BLOCKED** |
| Assistant schedule → `interview_service` | **PASS** |
| Unified schedule/reschedule/cancel authority | **PASS** (code) |
| Microsoft sync code path ready for when RBAC lands | **PASS** (code; live blocked) |
| Cancel reconciliation (late success not reported cancelled) | **PASS** |
| **Overall (requested Microsoft live proof)** | **FAIL** |
| **Assistant not fully complete** | Confirmed — waiting on Exchange RBAC assignment |

---

## Next action (human)

Run the PowerShell `New-ManagementRoleAssignment` above as Global Admin, then re-run `prove-m365-live-calendar.py` and a live Assistant/dashboard schedule with `meeting_type=microsoft_teams` against the evidence mailbox. Do not mark Assistant fully complete until that live matrix is green.
