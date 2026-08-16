# Microsoft Teams live matrix — after Application Access Policy

**Stamp:** `20260730T235906Z` (prove) / local pack `20260730T235844Z`  
**Overall:** **PASS**

Calendar RBACfA AU scope was **not** modified.

---

## Policy output (Cloud Shell)

From your Azure Cloud Shell session:

| Field | Value |
|---|---|
| Policy Identity | `Tag:Wathefni-OnlineMeetings-Evidence` |
| AppIds | `{16f7135a-b7e8-4ac8-adfe-2d2b13de3131}` |
| Description | Wathefni OnlineMeetings for evidence organizer only — not global |
| Grant | `Grant-CsApplicationAccessPolicy` → evidence user only (**not** `-Global`) |
| `Get-CsOnlineUser` | `ABDULAZIZALMULLA@wathefni.onmicrosoft.com` → **`ApplicationAccessPolicy = Wathefni-OnlineMeetings-Evidence`** |

Screenshot: `cloudshell-aap-grant.png`

---

## Propagation

| Milestone | UTC |
|---|---|
| Policy assigned (Cloud Shell ~screenshot) | ~`2026-07-30T23:57:00Z` |
| First OM poll start | `2026-07-30T23:58:47Z` |
| First OM poll result | **PASS** joinUrl on **poll 1** |
| Propagation elapsed | **~1–2 minutes** (no wait loop needed) |

---

## `prove-m365-teams-meeting.py`

**Verdict: PASS** (`passed=10 failed=0`)

| # | Proof | Result |
|---|---|---|
| 1 | Teams meeting + real `joinUrl` | **PASS** (`teams.microsoft.com`) |
| 2 | Calendar event linked | **PASS** (event id + webLink) |
| 3 | Attendees + Asia/Kuwait | **PASS** (2 attendees; TZ on create) |
| 5 | Reschedule same event id (no duplicate) | **PASS** |
| 6 | Cancel | **PASS** (204) |
| 7 | Evidence organizer allowed | **PASS** |
| 8 | Outside AAP denied | **PASS** (403 no policy on deny-probe) |
| — | Outside AU calendar still denied | **PASS** (403 — RBACfA intact) |
| 9 | Assistant executor wired + live OM helper | **PASS** |

---

## Extended live matrix

| Check | Result | Evidence |
|---|---|---|
| 4. Invitation email delivery | **PASS** | Sent Items: `Wathefni full matrix 20260730T235917Z` + cancel updates containing Teams join URL (`invitation-email-sentitems.json`) |
| Kuwait timezone on GET | **PASS** | With `Prefer: outlook.timezone="Asia/Kuwait"` → `timeZone=Asia/Kuwait` (`extended/timezone-prefer.json`) |
| Audit trail | **PASS** | create OM+event ids → reschedule same ids → cancel 204 → GET after cancel **404** |
| Assistant workflow | **PASS** | `_schedule_interview_executor` uses `microsoft_teams` / `interview_service`; live path = `create_teams_event` with joinUrl |

Unit tests: `test_interview_microsoft_calendar.py` → **PASS**

---

## Authority model (final)

| Layer | Scope |
|---|---|
| Calendar CRUD | Exchange RBACfA `Application Calendars.ReadWrite` + AU `Wathefni-Calendar-Evidence` |
| Teams join URLs | Graph `OnlineMeetings.ReadWrite.All` + AAP `Wathefni-OnlineMeetings-Evidence` **user-scoped** to evidence organizer |

---

## Artifacts

- Prod: `/opt/wathefni/production-evidence/wathefni-calendar-c6b/m365-teams-matrix-20260730T235906Z/`
- Local: `ops/evidence/m365-teams-matrix-20260730T235844Z/`

## Final

**PASS** — Teams + Calendar + Assistant Microsoft interview path complete for the evidence organizer under the narrow model.
