# Wave B — Microsoft Teams + outbound email production re-proof

**Stamp:** `20260801T033857Z`  
**Scope:** Fresh production re-proof only. No product code changes. Waves C/D not started.  
**Evidence tenant:** `WATHEFNI` · organizer/mailbox UPN `ABDULAZIZALMULLA@wathefni.onmicrosoft.com`  
**Overall:** **PASS** (authority + cleanup). Assistant catalog has one readiness under-report (email) noted below — not an M365 authority failure.

---

## Gates

| # | Gate | Result | Evidence |
|---|---|---|---|
| 1 | Create interview with Teams meeting | **PASS** | `teams/results.json` → `teams_create_join_url` |
| 2 | Valid Teams `joinUrl` | **PASS** | host `teams.microsoft.com`, `online_meeting_id` present |
| 3 | Calendar event + attendee invites | **PASS** | event + webLink; **2** attendees |
| 4 | Reschedule updates meeting (same id) | **PASS** | `reschedule_same_event_no_duplicate` |
| 5 | Cancel removes/cancels correctly | **PASS** | cancel **204**; cleanup GET **404** (`cleanup/cleanup-audit.json`) |
| 6 | Approved Microsoft sender can send | **PASS** | Graph **202** `accepted_by_provider` + dispatch path |
| 7 | Outside-scope sender denied | **PASS** | Graph **403** RAOP / AppOnly AccessPolicy |
| 8 | Wathefni/Postmark remains default sender | **PASS** | restored `outbound_mode=wathefni`, provider `postmark`; zero branded tenants |
| 9 | Permissions + tenant isolation fail-closed | **PASS** | outside AAP OM **403**; outside AU calendar **403**; calendar SP cannot send mail; mail SP cannot create calendar; mailbox list/get isolation vs `C1A1EFB783A` |
| 10 | Assistant capability/readiness state | **PASS*** | executor wired to `microsoft_teams`; live catalog fail-closed on Teams without MS connection; see note |
| 11 | Safe records + cleanup | **PASS** | Teams cancelled + GET 404; mail mode restored; no non-wathefni outbound modes |

\*Assistant: see “Assistant readiness” — Teams reporting is honest/fail-closed; email catalog flag under-reports Postmark.

---

## Teams matrix (`prove-m365-teams-meeting.py`)

**Remote:** `/opt/wathefni/production-evidence/m365-teams-waveB-20260801T033857Z/`  
**Verdict:** `passed=10 failed=0`

| Proof | Result |
|---|---|
| cert_token_mint | PASS |
| teams_create_join_url | PASS |
| calendar_event_linked | PASS |
| attendees_on_invite (2) | PASS |
| timezone_consistency (`Asia/Kuwait`) | PASS |
| reschedule_same_event_no_duplicate | PASS |
| cancel (204) | PASS |
| outside_aap_online_meeting_denied (403) | PASS |
| outside_au_calendar_still_denied (403) | PASS |
| assistant_schedule_executor_wired | PASS |

**Cleanup probe:** create → cancel 204 → GET event **404** `ErrorItemNotFound` → `cleanup/cleanup-audit.json` **PASS**

---

## Outbound Microsoft mail matrix (`prove-hybrid-email-microsoft-outbound.py`)

**Remote (clean rerun):** `/opt/wathefni/production-evidence/hybrid-email-m365-waveB-20260801T033857Z-rerun/`  
**Verdict:** `passed=22 failed=0` · marker `hybrid-email-ms-outbound-d065ad06550d`

| Proof (selected) | Result |
|---|---|
| mail SP configured / differs from calendar SP | PASS |
| mail token `Mail.Send` only (no Mail.Read*) | PASS |
| calendar SP cannot send mail (403) | PASS |
| email SP cannot use calendar authority (403) | PASS |
| microsoft mode activated evidence-only | PASS |
| only evidence tenant microsoft | PASS |
| approved mailbox send (202) | PASS |
| dispatch accepted_by_provider | PASS |
| outside_scope_send_denied (403) | PASS |
| tenant isolation no mailbox leak / get-by-id | PASS |
| switch_back_to_wathefni + resolve postmark | PASS |

### First attempt abort (non-product)

First run aborted on `inbound_still_postmark` because the SSH prove shell lacked systemd’s `WATHEFNI_INBOUND_EMAIL=on` (defaults off in CLI). That left `outbound_mode=microsoft_mailbox` briefly.

- **Root cause:** prove harness env gap (not inbound regression; service has `WATHEFNI_INBOUND_EMAIL=on`).
- **Mitigation:** emergency `force_wathefni_fallback` → `cleanup/mail-emergency-restore.json`
- **Rerun:** exported `WATHEFNI_INBOUND_EMAIL=on` → full matrix PASS + in-script restore.

Artifacts of first fail: `mail/first-attempt-fail/` · clean pass: `mail/artifacts/`

---

## Assistant readiness

**Live API:** `GET /dashboard/prehire/assistant/capabilities` → `assistant/prehire-assistant-capabilities.json`

| Signal | Observed | Interpretation |
|---|---|---|
| `_schedule_interview_executor` wires `microsoft_teams` | PASS (Teams prove) | Executor path ready |
| `providers.microsoft_calendar` | `false` | No `calendar_sync_connections` row with `provider_key=microsoft` + `status=connected` |
| `teams_meet` | `enabled_but_not_configured`, `offerable=false` | **Correct fail-closed:** certs ready, company MS calendar not connected |
| `providers.email` / `email` capability | `false` / `enabled_but_not_configured` | Catalog `_email_configured` checks `WATHEFNI_EMAIL_PROVIDER`/`SMTP`/`RESEND`/`SENDGRID` only — **does not detect Postmark**, while integrations email API reports `current_sender=wathefni` `status=ready` |
| `interviews_schedule` / `google_meet` / `calendar_events` | offerable | Interview tools remain offerable via Google path |

**No product code changed.** Email catalog under-report is recorded for a future readiness fix; it does not break Graph mail/Teams authority proved above.

---

## Cleanup proof

| Check | Result |
|---|---|
| Teams event GET after cancel | **404** (`cleanup/cleanup-audit.json`) |
| Emergency restore after first mail abort | `outbound_mode=wathefni` (`cleanup/mail-emergency-restore.json`) |
| Matrix restore + final resolve | mode `wathefni`, provider `postmark` (`cleanup/final-default-sender.json`) |
| Non-wathefni branded tenants | **none** |
| Dashboard email settings final | `current_sender=wathefni` `status=ready` (`cleanup/email-settings-final.json`) |

---

## Failures / root causes

| Item | Severity | Root cause | Action taken |
|---|---|---|---|
| First mail run `inbound_still_postmark` FAIL | Harness | Prove shell missing `WATHEFNI_INBOUND_EMAIL=on` | Restored wathefni; reran with env → PASS |
| Transient microsoft_mailbox left active | Ops | `ok()` abort before restore step | Emergency `force_wathefni_fallback` + successful rerun restore |
| Assistant `email` not offerable despite Postmark ready | Catalog accuracy | `_email_configured` omits Postmark env/signals | Documented only (no code change in Wave B) |

---

## Local pack

`ops/evidence/m365-teams-email-waveB-reproof-20260801T033857Z/`  
See `MANIFEST.txt` (48 files).
