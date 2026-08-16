# Unified Action Inbox — Real-HR Rollout Readiness Audit

**Mode:** research + qualification planning only  
**Date:** 2026-08-03  
**Prerequisite gates:** `STAGING_ACTION_INBOX_WAVE1_GO` · `PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO`  
**Freeze:** `ops/ACTION_INBOX_WAVE1_FREEZE.md` (synthetic-only production posture)  
**This document does not deploy, widen access, flip flags, or start another differentiation wave.**

---

## Executive verdict

| Decision | Verdict |
|---|---|
| Keep synthetic-only posture as-is (honesty flags only) | **Unsafe to treat as “no real visibility”** |
| Run one controlled real-HR canary **today** | **NO-GO** |
| Run one controlled real-HR canary **after** actor + subject gates land | **Conditional GO** (plan below) |
| Broad HR / manager rollout | **NO-GO** |
| Another differentiation wave / AI / Wave 2 / money / ingest / shifts-manager expand | **NO-GO** |

**Bottom line:** Production synthetic qualification proved composition correctness, but **does not equal controlled real-HR readiness**. Live read probe (2026-08-03) shows the inbox already composes **real** Compliance + E360 items for an owner-scoped context while `WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY=1`. There is **no actor allowlist** and **no subject allowlist** on the inbox path. Treat current posture as **compose-live-for-entitled-dashboard-users**, not “synthetic subjects only.”

Until a fail-closed **viewer allowlist** (and preferably a **subject allowlist**) exists, do **not** declare a controlled real-HR canary GO.

---

## 1. What is frozen / in force today

### Product contract (must keep)

- Inbox **read-only** — composes + ranks only; **does not mutate**
- Frozen modules remain **systems of action** (Analytics, Compliance, Employees 360, Onboarding, Attendance, Leave, Shifts, Payroll)
- **Alerts & Delivery** owns notifications
- Hiring Reports stay separate
- No AI; no Compliance/Analytics Wave 2; no Payroll money work; no Attendance ingest; no Shifts manager expansion

### Live production flags (observed)

```
WATHEFNI_ACTION_INBOX_WAVE1=1
WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES=WATHEFNI
WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY=1
WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_KEY_MARKERS=AIW1,AIW1-SYNTH|
WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_PHONE_PREFIXES=965542
```

Sibling source modules also carry Wave-1 `SYNTHETIC_ONLY=1` flags; those flags are **posture/canary markers**, not proof that dashboard reads are empty of real people.

### Live composition probe (read-only, owner context)

For `company=WATHEFNI`, actor phone `96599338566` (owner), with post-hire read permissions:

| Metric | Observed |
|---|---|
| Inbox `total` | **23** |
| Analytics items | **0** (source live, empty attention) |
| Compliance findings | **17** |
| Employees 360 next actions | **6** (after Compliance dedupe of 17) |
| Actor allowlist in code | **Absent** |
| Subject filter by `is_synthetic_subject` on payload | **Absent** |
| Example subjects surfaced | Real employees (e.g. Fouad, Brian, others) — document/onboarding/payroll-timesheet signals |

**Implication:** “Synthetic-only” on Action Inbox today means **qualified under synthetic canaries + honesty flags**, not **hidden from real HR eyes**.

---

## 2. Exact first HR canary (proposed)

### Tenant

| Field | Value |
|---|---|
| Company | **`WATHEFNI` only** (`WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES=WATHEFNI`) |
| Environment | Production dashboard |
| Locale | EN + AR both in-scope for UI proof |

### First viewer (HR canary role)

| Field | Value | Rationale |
|---|---|---|
| Role | **Owner / HR operator** (not manager, not viewer) | Matches Shifts controlled operator pattern |
| Email | `azizalmulla16@gmail.com` | Active `owner` |
| Phone | **`96599338566`** | Same digits as `WATHEFNI_SHIFTS_HR_ALLOWLIST` |
| User id | `88b17ca9-aff4-4721-a553-c1b5514ef95f` | Stable dashboard subject |

**Explicitly out of first canary (deny):**

| Actor | Why deny first |
|---|---|
| `f.burhama@disruptv.tech` (owner, phone `66363363`) | Second owner; would see company-wide inbox; phone digit mismatch risk already documented in Shifts freeze |
| `fslalmulla@gmail.com` / `h.almulla@almulla-media.com` (viewers) | No phone; not operators |
| Any `manager` role | Needs separate manager-scope proof after HR canary |

### Allowed employee / team subject scope (first canary)

**Tightest recommended subject allowlist (one person):**

| Employee key | Name | Why |
|---|---|---|
| `WATHEFNI-96550252254` | Talal Fadhli | Existing ESS + Employee App + Shifts notify canary; classified real |

**Optional expansion only after Talal-only GO (still controlled):** the four E360 classified reals — still **not** all 66 active employees.

| Key | Name | Note |
|---|---|---|
| `WATHEFNI-96550252254` | Talal Fadhli | Primary |
| `WATHEFNI-96566363363` | Fouad Burhamad | Lifecycle allowlisted; high document noise |
| `WATHEFNI-96597727743` | mohammad alqattan | Lifecycle allowlisted |
| `WATHEFNI-96599411617` | Brian Saleh | Lifecycle allowlisted; missing-doc heavy |

**Team/location scope:** none beyond the named keys for canary-1. Do not open “all Ops” / “all HQ.”

---

## 3. Which sources may appear (canary-1 allowlist)

| Source stream | Canary-1 | Notes |
|---|---|---|
| **Compliance `findings[]`** | **YES** | Highest-value, already live; deep links → Compliance / Onboarding |
| **Employees 360 next actions** | **YES (filtered)** | Only for allowlisted subjects; exclude payroll-timesheet actions in canary-1 |
| **Analytics `attention[]`** | **Soft YES** | Currently empty on probe; keep enabled for honesty of partial/empty states |
| Payroll money / cost | **NO** | Out of scope permanently for this wave |
| Hiring Reports | **NO** | Stay separate |
| Alerts & Delivery content as inbox rows | **NO** | Delivery ownership stays in Alerts module |

### Recommended stream policy for canary-1

1. Compose Compliance findings for allowlisted subjects only.  
2. Compose E360 next actions for allowlisted subjects only, **excluding** `system_of_action=payroll` / timesheet approval rows (money-adjacent optics; Payroll remains SoA elsewhere).  
3. Compose Analytics attention if present; if empty, treat as healthy empty source (not error).  
4. Keep E360↔Compliance dedupe on.

### Deep links allowed (SoA only; read navigation)

| Destination page | Allowed in canary-1 | Safety note |
|---|---|---|
| `compliance` | YES | System of action for findings |
| `onboarding` | YES | Missing-doc SoA |
| `employees` | YES | Person context only |
| `leave` / `attendance` / `shifts` | YES if Analytics emits | Existing frozen modules; inbox must not mutate |
| `payroll` | **NO for canary-1 deep links** | Avoid money-adjacent entry from inbox until separate sign-off |
| `analytics` / `reports` / `notifications` | NO as primary SoA for item action | Honesty: open the producing module |

Deep-link safety rule: inbox buttons only call existing `onNavigate(page, { employee })` into modules the actor already has entitlement for; **no new mutation APIs**.

---

## 4. Permissions / scope matrix

### Viewer entitlement (proposed fail-closed)

| Layer | Required for canary | Fail-closed if missing |
|---|---|---|
| Company allowlist | `WATHEFNI` | Empty / other company → no inbox |
| Module gate | any post-hire source readable (existing) | 403 |
| Permission gate | existing `*.read` / `employees.read` | 403 |
| **NEW: Actor allowlist** | phone digits / user_id / email match `WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST` | 403 or empty+hidden nav |
| Manager scope | owners: company; managers: `manager_scope_employee_keys` | Unscoped manager → empty / fail-closed |
| **NEW: Subject allowlist** | item `employee_key` ∈ `WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST` (or non-person analytics rows tagged company-only) | Drop item |
| Stream allowlist | optional `WATHEFNI_ACTION_INBOX_REAL_STREAMS=compliance,employees,analytics` | Drop stream |

### Nav visibility

| Actor class | Today (no actor gate) | Required for canary |
|---|---|---|
| Allowlisted HR operator | Can open inbox if modules on | **Only this actor sees `inbox` nav** |
| Other owners | Likely can open inbox | **Must not** |
| Managers / viewers | If entitled to sources | **Must not** until later wave |

### Comparison to approved Shifts pattern

Shifts real use is gated by **named HR allowlist + real mutation gate + code-pinned approved operators**. Action Inbox needs the **viewer-allowlist analogue** (read gate), even though inbox mutations are already forbidden.

---

## 5. Risks and mitigations

| Risk | Severity | Evidence | Mitigation before canary |
|---|---|---|---|
| **SYNTHETIC_ONLY does not hide real people** | **Critical** | Live 23 real items under `SYNTHETIC_ONLY=1` | Implement actor (+ subject) allowlists; until then keep expectation honest and do not market “synthetic-only visibility” |
| **Second owner sees company-wide PII/docs** | High | Fouad is active owner | Actor deny-list / allowlist excludes him for canary-1 |
| **Manager-scope leakage** | High | E360 uses `manager_scope_employee_keys`; owners see all | Canary is owner-only first; later manager canary with empty-scope proof |
| **Cross-employee privacy in one queue** | High | Inbox ranks many employees | Subject allowlist (Talal-only) |
| **Payroll timesheet rows in E360 stream** | Medium | Live items with `soa=payroll` | Exclude payroll SoA from canary streams |
| **Stale / partial source misread as truth** | Medium | UI has stale/partial banners | Canary checklist: force partial by denying one module perm; verify honesty copy |
| **Deep link into module actor cannot use** | Medium | Deep link pages vary | Only emit links for modules in actor’s accessible set; soft-hide otherwise |
| **Users treat inbox as notification system** | Medium | Product confusion | Keep Alerts & Delivery ownership; canary briefing script |
| **Users try to “complete” work in inbox** | Low–Med | Read-only | UI honesty + support script: “open SoA” |
| **Kill switch too coarse** | Medium | Drop-in removal affects whole company flag | Prefer soft kill: clear viewer allowlist first; then `ACTION_INBOX_WAVE1=0` |
| **Analytics/Compliance still synthetic-flagged** | Low | Sibling freezes | Do not reopen Wave 2; inbox may compose their **existing** read contracts only |

---

## 6. Stale / partial / error behavior (qualification expectations)

| State | Expected UX | Canary proof |
|---|---|---|
| Empty (no items in scope) | Empty state EN/AR; not an error | Talal with no outstanding docs/actions |
| Partial sources | Banner listing unavailable source keys | Temporarily remove one source permission for canary actor (lab) or disable one module for company in staging twin |
| Source error | Partial/error banner; other streams still show | Inject/observe source error path in staging before prod canary |
| Stale (> freshness window) | Stale warning + Refresh | Wait or skew client clock in staging; confirm copy |
| After SoA completion | Item clears on refresh | Complete one Compliance/Onboarding action on allowlisted subject; confirm disappearance |

Do **not** invent AI summaries for partial/stale.

---

## 7. Rollback and kill-switch procedure (no deploy in this audit)

### Soft kill (preferred first — minutes)

1. Clear `WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST` (once implemented) → no real viewer.  
2. Optionally clear subject allowlist.  
3. Restart orchestrator; confirm nav 403/hidden for canary actor.  
4. Confirm Analytics / Compliance / E360 sibling freezes unchanged.

### Hard kill (company-wide inbox off)

1. Set `WATHEFNI_ACTION_INBOX_WAVE1=0` **or** remove Action Inbox systemd drop-in  
   `/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-action-inbox-wave1b-synthetic.conf`  
2. `systemctl daemon-reload && systemctl restart wathefni-orchestrator`  
3. Health check `:8010/health`  
4. Confirm `/dashboard/posthire/action-inbox` denied or empty-disabled for company.

### Full code/config rollback

Use backup `ROLLBACK.sh` under:

`/opt/wathefni/backups/production-pre-action-inbox-wave1b-*`

Durable `action_inbox_wave_acks` rows are retained (audit); canary-tagged ACK rows cleaned by canary tools only.

### What rollback must **not** do

- Must not turn on Attendance capture ingest  
- Must not widen Shifts manager allowlists  
- Must not alter Compliance/Analytics Wave-1 honesty  
- Must not delete real employee documents or leave/attendance rows

---

## 8. Support / incident procedure (canary window)

| Item | Spec |
|---|---|
| Window | Business hours Asia/Kuwait; max **4 hours** first session |
| Primary operator | Aziz (`96599338566`) |
| Backup | Owner-designated; **not** auto-include second owner |
| Comms | Private operator channel only; no broadcast to all dashboard users |
| Severity SEV-1 | Cross-tenant leak, unscoped manager seeing others, mutation attempted/succeeded from inbox | Hard kill + preserve logs |
| Severity SEV-2 | Wrong deep link, stale presented as live, payroll row shown despite policy | Soft kill allowlist; file evidence |
| Severity SEV-3 | Copy/EN-AR glitch, empty when expected item | Continue; log |
| Evidence pack | `ops/evidence/action-inbox-real-hr-canary-<stamp>/` with screenshots EN+AR, item IDs, before/after clear proof |
| Stop rule | Any SEV-1/2 → end canary; remain synthetic posture / allowlist empty |

**Support script (operator):**  
“Action Inbox lists what needs attention. It does not send WhatsApp and does not change records. Open the linked module to act. Alerts & Delivery owns reminders.”

---

## 9. Success metrics for the canary

Must all pass for **GO to keep allowlist live** (still not broad rollout):

| # | Metric | Pass rule |
|---|---|---|
| 1 | Actor isolation | Only allowlisted viewer can load inbox; Fouad/viewers denied or nav hidden |
| 2 | Subject isolation | Only Talal (or declared subject set) appears in person-scoped items |
| 3 | Stream policy | No payroll SoA items in canary-1 |
| 4 | Deep-link safety | Each item opens intended SoA; no mutation from inbox |
| 5 | Clears-on-resolve | ≥1 real item disappears after SoA completion + refresh |
| 6 | Ranking sanity | High severity before medium for mixed set |
| 7 | Partial/stale honesty | Banners correct; no false “all sources live” when partial |
| 8 | EN/AR | Same item readable in both locales |
| 9 | Mobile web | Usable at ~390px width |
| 10 | Sibling freezes | Analytics/Compliance/E360/Onboarding/Attendance/Leave/Shifts/Payroll freeze smokes still green |
| 11 | Residual | No new canary ACK residue; no synthetic marker pollution on real keys |
| 12 | Kill switch drill | Soft kill proven in ≤5 minutes during window |

---

## 10. Exact canary plan (qualification sequence)

### Phase 0 — Blockers (must ship before any real-HR “canary GO”)

**Implementation-sized, still not “another differentiation wave”** — control-plane only:

1. `WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST` (phones/user_ids); empty = no real viewers (fail closed).  
2. `WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST` (employee_keys); empty while real-viewer mode on = show **zero** person items (fail closed).  
3. Optional stream deny: drop `payroll` SoA from inbox while flag set.  
4. Nav + API both enforce viewer allowlist.  
5. Staging prove of allowlists, then production drop-in **without** enabling second owner.  
6. Update freeze honesty: distinguish **synthetic canary markers** vs **real-viewer allowlist**.

Until Phase 0 is done: **NO-GO**.

### Phase 1 — Controlled real-HR canary (after Phase 0)

1. Pre-brief operator; soft-kill path reviewed.  
2. Set viewer allowlist = `96599338566` only.  
3. Set subject allowlist = `WATHEFNI-96550252254` only.  
4. Streams = compliance + employees (+ analytics if present); exclude payroll SoA.  
5. Operator session: EN, then AR; desktop + mobile web.  
6. Complete one real SoA action on Talal if an item exists; prove clear.  
7. Attempt access as Fouad/viewer → must fail.  
8. Soft-kill drill; re-enable only if metrics pass.  
9. Evidence pack + gate stamp `PROD_REAL_HR_ACTION_INBOX_CANARY_GO` or `NO_GO`.

### Phase 2 — Explicitly later (out of this audit’s GO)

- Manager-role canary  
- Multi-subject allowlist  
- Payroll SoA rows  
- Broad company HR

---

## 11. GO / NO-GO

### NOW (no code/access change)

**NO-GO for one controlled real-HR canary.**

Reasons:

1. No fail-closed **viewer allowlist** on Action Inbox.  
2. No fail-closed **subject allowlist**; live probe already shows multi-employee real data.  
3. `SYNTHETIC_ONLY=1` is **not** a visibility control for this module.  
4. Second owner and other entitled users are not isolated.  
5. E360 stream can surface payroll-timesheet deep links (money-adjacent optics).

**Recommended interim posture:** remain on current synthetic freeze documentation; treat Phase 0 control-plane as the next change-control item — **not** a new product differentiation wave. Prefer soft-kill (`ACTION_INBOX_WAVE1=0` or hide nav) if operators want zero real composition exposure until Phase 0 ships — that kill is an **ops decision**, not authorized by this audit.

### AFTER Phase 0 gates exist and staging-proved

**Conditional GO** for **one** controlled real-HR canary:

- Tenant `WATHEFNI`  
- Viewer `96599338566` only  
- Subject `WATHEFNI-96550252254` only  
- Streams: Compliance + filtered E360 (+ empty-ok Analytics)  
- No payroll SoA items  
- Soft kill drilled  
- Sibling freezes green  

Still **NO-GO** for broad HR, managers, or any further differentiation wave.

---

## 12. Decision fork (owner)

| Path | When to choose |
|---|---|
| **A. Keep synthetic-only / no real canary** | If Phase 0 cannot ship soon; accept honesty gap or soft-kill inbox visibility |
| **B. Build Phase 0 gates → run Talal/Aziz canary** | Preferred if product needs real-HR proof before freeze language changes |

This audit chooses **Path A for immediate action** (no deploy) and documents **Path B** as the only safe real-HR canary design.

---

## References

- `ops/ACTION_INBOX_WAVE1_FREEZE.md`  
- `ops/evidence/action-inbox-wave1b-prod-canary-20260803T170914Z/`  
- `ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` (allowlist pattern)  
- `ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` (classified reals / Talal)  
- `ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md` / `ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md`  
- Live read probe 2026-08-03 (owner context): 23 real inbox items; no actor/subject allowlist
