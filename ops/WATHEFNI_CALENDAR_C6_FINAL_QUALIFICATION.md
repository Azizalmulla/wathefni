# Wathefni Calendar — C6 Final Qualification (C6B production closure)

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260729T170639Z` (prior C6 simulation stamp `20260729T164350Z`)  
**Evidence:** `/opt/wathefni/production-evidence/wathefni-calendar-c6b/20260729T170639Z/`  
**Authority:** C0–C5 implementation docs; C6B = controlled live production closure attempt  
**Preserves:** Waves 1–6, Calendar C1–C6 platform modes, communication handoff  
**Evidence tenant with `calendar` enabled:** **WATHEFNI** (controlled; module enablement only)  
**Out of scope (explicit):** recurrence, resources, two-way sync, SSO, directory, email/files platform capabilities, broad tenant launch

---

## Final verdict: **NO-GO** (unconditional production closure)

C6B **does not** convert the prior CONDITIONAL GO into an unconditional production GO.

Platform modes, Google OAuth live sync, Meet, live Calendar email (Postmark), outbox idempotency, candidate privacy, and C1–C6 regressions are proven on the evidence tenant. Unconditional GO remains blocked by missing Microsoft Entra credentials, Google Workspace DWD (consumer Gmail cannot be impersonated), and inactive Octopus WhatsApp sessions for a live WA send.

Controlled evidence-tenant use may continue under the previous **CONDITIONAL GO** posture (dry-run sync/delivery workers by default; oneshot live proofs only).

| Gate | Result |
|---|---|
| Unconditional production GO | **NO-GO** |
| Evidence-tenant CONDITIONAL use | **Allowed** (unchanged from C6) |

---

## Real integration evidence

| Integration | Status | Evidence |
|---|---|---|
| Google OAuth client | **PASS** | `/root/.openclaw/secrets/wathefni-google-oauth.production.env` + orchestrator drop-in; `google_oauth_client_provisioned` |
| Google OAuth refresh (evidence) | **PASS** | `/root/.openclaw/secrets/gog-refresh.evidence.env` → account `azizalmulla16@gmail.com` |
| Google DWD service account JSON | **Present / live FAIL** | `/root/.openclaw/secrets/wathefni-service-account.json` (`wathefni@wathefni-493221.iam.gserviceaccount.com`); mint vs Gmail → `401` |
| Microsoft Entra app registration | **MISSING** | `/root/.openclaw/secrets/wathefni-m365.production.env` documents required `WATHEFNI_M365_CLIENT_*` — not provisioned |
| Fernet mailbox/credential secret | **PASS** | `WATHEFNI_MAILBOX_SECRET_KEY` already on host (C5) |

---

## Controlled live provider proof

Stamp results: `c6b-final-results.json` → **16 PASS / 6 FAIL(blocked)**

| Proof | Result | Notes |
|---|---|---|
| Google `oauth_delegated` connect | **PASS** | Single connection (legacy dual-write disabled for proof) |
| Google token refresh | **PASS** | Access token minted |
| Google live create | **PASS** | Provider event `266vookco8mkvaggulcpoe2bto` |
| Google live update same id | **PASS** | Same `provider_event_id` retained |
| Google live cancel | **PASS** | Wathefni `cancelled` |
| No duplicate after retry | **PASS** | Binding count 1 |
| Reconnect no duplicate | **PASS** | |
| Provider failure ≠ Wathefni damage | **PASS** | Disconnect left cancelled truth intact |
| Google Meet live | **PASS** | `https://meet.google.com/vkg-dyrr-wro` (cleaned up) |
| Microsoft app-only live | **BLOCKED** | No Entra credentials |
| Microsoft delegated OAuth live | **BLOCKED** | No Entra credentials |
| Microsoft Teams live | **BLOCKED** | Depends on M365 |
| Google DWD live | **BLOCKED** | No Workspace domain impersonation target; Gmail DWD invalid |

Workers restored to defaults: `CALENDAR_SYNC_DRY_RUN=true`; sync connections for WATHEFNI left **disconnected** after oneshot.

---

## Controlled live communication (evidence tenant)

Policy: WATHEFNI `communication_policy` external_guest/pre_hire → email preferred, WhatsApp fallback, company account `default`.

| Proof | Result | Notes |
|---|---|---|
| Invitation | **PASS** | Outbox `guest_invite` → Postmark; `company_code=WATHEFNI` |
| Event change | **PASS** | `guest_update` → Postmark |
| Cancellation | **PASS** | `guest_cancel` → Postmark |
| Reminder | **PASS (email fallback)** | WhatsApp preferred → `conversation_inactive` → email success; fallback stopped after first success |
| Outbox idempotency | **PASS** | Second enqueue `ON CONFLICT` → `idempotent: true` (no duplicate row) |
| Correct company account | **PASS** | Attempts/outbox threaded `WATHEFNI` |
| Live WhatsApp session send | **BLOCKED** | Octopus `Invalid conversation_id` / inactive session on evidence phones |

Evidence: `c6b-comm-results.json` + `c6b-final-results.json`.

---

## Final visual QA

Inspiration assets under `…/inspirations/` (Overview soft bento, Intelly, SaaS onboarding).  
Shipped CalendarShell tokens (cream `#fffaf0` / `#f7f2e9`, ink, rounded drawers) aligned; no unrelated page redesign.

Screenshots (design-fidelity of shipped Calendar UX + C6 connect checklist):

| File | Coverage |
|---|---|
| `screenshots/c6b-week.png` | Week · My · event drawer |
| `screenshots/c6b-day.png` | Day · Team |
| `screenshots/c6b-month.png` | Month · Company |
| `screenshots/c6b-overview.png` | Overview panel (inspiration-aligned) |
| `screenshots/c6b-connect.png` | Enterprise vs Simple OAuth checklist |
| `screenshots/c6b-mobile-rtl.png` | Mobile Arabic RTL |
| `screenshots/c6b-full.png` | Full capture |
| `screenshots/c3-*.png` | Prior C3 baseline retained |

Source fixture: `screenshots/calendar-c6b-visual-qa.html`.

---

## Production qualification matrix

| Area | Result |
|---|---|
| Tenant isolation | **PASS** (C1–C6 smokes) |
| Candidate privacy | **PASS** (live payload summary hides candidate name) |
| Permissions | **PASS** (smokes) |
| OCC / conflicts | **PASS** (C1/C4 smokes) |
| OAuth / app-only / DWD security | **PARTIAL** — Google OAuth live; M365/DWD fail-closed without credentials |
| Live sync idempotency | **PASS** (Google) |
| Live communication idempotency | **PASS** (outbox) |
| Performance | **PASS** (oneshot sync/delivery within smoke envelopes; health 200) |
| Rollback / restore | **PASS** — timers dry-run; connections disconnected; health **200** after restart path |
| C1–C6 regressions | **PASS** — C6 34/0, C5 62/0, C4 39/0, C1 53/0 |

---

## Ops blockers to lift NO-GO → unconditional GO

1. Provision Microsoft Entra app (`WATHEFNI_M365_CLIENT_ID/SECRET/REDIRECT_URI/TENANT_ID`) and run live app-only + delegated create/update/cancel + Teams on an evidence mailbox.  
2. Provision Google Workspace domain Admin DWD for the SA and an impersonation identity (not consumer Gmail); prove DWD create/update/cancel + Meet.  
3. Establish an **active** Octopus WhatsApp conversation for the evidence recipient; prove live WA reminder with company account and no duplicate after outbox conflict.  
4. Re-run `c6b-live-evidence.py` + attach updated stamp; flip this doc to **GO**.

---

## Optional backlog (do not start as Calendar closure)

- Recurrence product UI  
- Resources / rooms  
- Two-way sync / conflict UI  
- Per-user OAuth calendars  
- SSO / directory / email / files as platform capabilities  
- Broad Calendar enablement beyond evidence tenant  
- Authenticated live dashboard screenshot capture (session cookie automation)

---

## Rollback

| Action | State |
|---|---|
| Disable evidence module | `UPDATE company_modules SET enabled=false WHERE company_code='WATHEFNI' AND module_key='calendar'` |
| Keep sync dry-run | Default on `wathefni-calendar-sync.service` (**confirmed true**) |
| Keep delivery dry-run | Default on reminders service |
| Disconnect sync | WATHEFNI connections left `disconnected` after C6B |
| Restart orchestrator | Health **200** |

---

## Files

| File | Role |
|---|---|
| `wathefni-orchestrator/c6b-live-evidence.py` | Controlled live evidence pack |
| `wathefni-orchestrator/platform_connection_c6.py` | Enterprise + OAuth + health/expiry/rotation |
| `ops/WATHEFNI_CALENDAR_C6_FINAL_QUALIFICATION.md` | This document |
| Evidence stamp | `/opt/wathefni/production-evidence/wathefni-calendar-c6b/20260729T170639Z/` |
