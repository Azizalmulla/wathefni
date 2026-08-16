# Employees 360 Wave 3B — Lifecycle policy decisions & production-safe defaults

**Stamp:** `20260801T204059Z`  
**Evidence:** `ops/evidence/employees360-wave3b-lifecycle-policy-20260801T204059Z/`  
**Mode:** Policy / operations design only  
**Production deploy:** **NOT DONE**  
**Wave 4 / unrelated modules:** **NOT STARTED**

Builds on Wave 3 PASS (`employees360-wave3-lifecycle-local-20260801T202958Z`) and live Wave 2 authority.

**Disclaimer:** This document separates **statutory research summaries** (Kuwait / GCC) from **Wathefni product policy**. It is **not legal advice**. No AI system may decide termination lawfulness, notice sufficiency, end-of-service amounts, or payroll outcomes. Operators and counsel own those decisions.

---

## Verdict

| Gate | Result |
|---|---|
| Decision matrix for remaining Wave 3 open items | **DONE** |
| Legal vs product-policy separation | **DONE** |
| Safe defaults by small / medium / enterprise | **DONE** |
| Counsel questions listed | **DONE** |
| Scheduler / ops design | **DONE** |
| Exact pre-production change list | **DONE** |
| Wave 3 behavior preserved (no regression intent) | **YES** |
| Production deploy now | **NO-GO** |

### Final GO / NO-GO for Wave 3 deployment

**NO-GO** for production until the pre-production checklist below is implemented, staged, and counsel-reviewed for Kuwait defaults.

Wave 3 code may stay on staging/local with flags off in production.

---

## 1. Legal research vs product policy (hard boundary)

### What law / statute research suggests (informational only)

| Topic | Kuwait private sector (Law No. 6 of 2010 — secondary sources) | Other GCC (templates only; not auto-applied) |
|---|---|---|
| Unlimited-contract notice | Often cited: **3 months** if monthly-paid; **1 month** otherwise; pay in lieu if notice not worked | UAE typically 30–90 days by contract; KSA often 60 days open-ended; others vary by service / contract |
| Fixed-term end | Often ends at term; early exit may trigger compensation rules | Country-specific; do not encode as Wathefni math |
| Job-search time in notice | Kuwait sources: employer-initiated notice may allow ~1 day / 8h per week paid job search | Not universal across GCC |
| End-of-service / indemnity | Statutory entitlement formulas exist; **never computed in Employees 360** | Hand to Payroll + counsel |
| Summary dismissal | Limited serious-misconduct grounds; proof burden on employer | Country-specific |

### What product policy owns (configurable)

- Whether the UI **suggests** a notice length (never silently shortens statutory floors)
- Who may **override** dates (with two-person approval + audit)
- When **app access** is revoked
- Which downstream items are **warn-only** vs **hard-blocked**
- Scheduler cadence and ownership
- Rehire hub-key strategy
- Settlement **handoff packet** shape (inputs only)

**AI / system must not:** declare a termination lawful, waive statutory notice, compute indemnity, or auto-approve irreversible offboarding.

---

## 2. Decision matrix (resolved for Wathefni)

| # | Decision | Recommended product default (WATHEFNI / SMB-safe) | Enterprise override | Legal layer |
|---|---|---|---|---|
| D1 | Notice-period behavior | System **suggests** notice end date from company policy template (Kuwait monthly → 90 calendar days hint). Operator enters `termination_effective_on` + `last_working_day`. No pay-in-lieu calculation. | Stricter: block submit if effective date &lt; suggested floor **unless** override reason + dual approval + counsel ref | Suggest ≠ enforce law. Floor warnings labeled “policy hint / counsel required” |
| D2 | Who can override dates | Requester proposes; **designated approver** confirms. Override of suggested floor requires `date_override_reason` + `approval_reference`. | Require role `employees.lifecycle.override` + second approver | Counsel must confirm override is lawful for that case |
| D3 | App/session revoke timing | **Not on approval.** Revoke at **end of `last_working_day`** in `Asia/Kuwait` (23:59:59). If LWD omitted, use end of day before `termination_effective_on`, else end of effective date. | May choose revoke at `termination_effective_on` 00:00, or immediate on summary dismissal case type | Access control is product; employment rights remain legal |
| D4 | Effective termination time | Calendar date `termination_effective_on` becomes effective at **00:00 Asia/Kuwait** on that date (employment `terminated`). Scheduler applies when `CURRENT_DATE >= effective` in company TZ. | Optional timestamptz later; v1 stays date-based | Date semantics must match payroll cutover agreed with counsel/payroll |
| D5 | Reversal **before** effective (`notice_period`) | Named **cancel scheduled termination**: same `employment_id`; clear term fields; return `active`; two-person approval; audit `termination_cancelled_before_effective` | Same + optional manager notification | Usually reversible ops action; still audited |
| D6 | Reversal **after** effective (`terminated`) | Named **reinstate employment**: same `employment_id` (not rehire); two-person; mandatory reason + approval_reference; impact re-check; **does not** auto-restore revoked sessions or cancelled shifts | Require legal_ack flag + owner role | High-risk; counsel for back-pay / continuity |
| D7 | Downstream: warn vs block | **SMB default: warn-only** on shifts/leave/attendance/payroll/onboarding/docs/access. Termination approval never blocked by open downstream items. UI requires explicit “I reviewed impact” ack. | Optional hard blocks: open **submitted** payroll timesheets; approved leave overlapping post-effective dates | Blocking is policy, not law |
| D8 | Always hard-fail (all tiers) | Self-approval; stale concurrency; out-of-scope manager; cross-tenant; rehire while not terminated; idempotency payload conflict | Same | Safety / tenancy |
| D9 | Scheduler ownership | **Platform Ops** owns systemd timer `wathefni-lifecycle-effective.timer` → oneshot service calling `execute_due_scheduled_terminations` per allowlisted company. Idempotent; retries = next tick; alert on non-zero exit / lag. | 15-minute cadence + pager | Ops reliability ≠ legal determination |
| D10 | True rehire ↔ `employee_key` | **Prefer same `employee_key`** when phone unchanged: new `employment_id` + `assignment_id`, remap authority map, keep hub key; prior employment row immutable `terminated`. New key only if phone/identity requires it. | Always mint new key + link prior_key in provenance | Compatibility with child tables keyed by `employee_key` |
| D11 | Final settlement handoff | Emit **settlement input packet** (no amounts): person/employment IDs, LWD, effective date, term type/reason, leave balance snapshot refs, open timesheet IDs, attendance exception IDs. Status `handed_to_payroll`. Payroll owns formulas. | Require payroll assignee before case close | Employees 360 never computes EOSB |
| D12 | After termination effective | Freeze new leave/shift assignments; mark future shifts `cancelled_lifecycle` only via **explicit approved downstream action** (not silent); pending leave → warn or enterprise auto-decline with audit; attendance: no new posts after effective; onboarding open items → `abandoned_employment_ended`; sessions revoked per D3 | Auto-decline leave + auto-cancel shifts on effective tick | Explicit + reversible preferred over silent mutation |

---

## 3. Recommended defaults by tier

| Policy knob | Small | Medium | Enterprise |
|---|---|---|---|
| Notice suggestion template | Kuwait monthly 90d / non-monthly 30d hints | Same + contract field override | Country pack + contract-required notice days |
| Date override | Dual approval + reason | Dual approval + reason + manager notify | Dual approval + `lifecycle.override` + counsel ref |
| Impact ack | Required checkbox | Required + store ack user/time | Required + optional hard blocks |
| Downstream blocks | None (warn only) | Warn; block only if payroll timesheet `submitted` | Configurable block set |
| Access revoke | End of LWD (Kuwait TZ) | Same | Configurable: LWD end vs effective 00:00 vs immediate (summary cases) |
| Scheduler | Hourly timer | Hourly + lag alert &gt; 2h | Every 15m + on-call |
| Rehire key | Same `employee_key` if phone stable | Same | Same, plus identity verification step |
| Settlement | Packet + manual payroll | Packet + assignee | Packet + maker-checker in Payroll |
| Reinstate after effective | Allowed with dual approval | Dual + owner | Dual + owner + legal_ack |
| Pending_start enforcement | Optional | Default on for new hires | Required |

---

## 4. Legal questions requiring counsel

1. Confirm Kuwait Law 6/2010 notice floors for Wathefni’s actual contract types (monthly vs other; fixed-term vs unlimited; probation).
2. Whether UI “suggested notice” creates any representation risk if shorter dates are approved.
3. Pay-in-lieu / garden-leave handling — must stay outside Employees 360 math.
4. End-of-service / leave encashment formulas and which payroll fields are authoritative.
5. When summary dismissal without notice is permissible and what evidence must be retained.
6. Reinstate-after-effective: continuous service vs broken service for indemnity and visa.
7. Job-search day during employer notice — product tracking vs legal entitlement.
8. Document retention / legal hold after termination (especially Civil ID / residency).
9. Cross-border remote workers (if any) — which country’s notice applies.
10. Whether auto-decline of leave / auto-cancel of shifts on effective date is acceptable under local practice.

Until counsel answers 1–4 and 6, production remains **NO-GO** for WATHEFNI live terminations beyond synthetic staging.

---

## 5. Scheduler / operations design

### Ownership

| Role | Responsibility |
|---|---|
| Platform Ops | systemd unit/timer, monitoring, on-call for failed ticks |
| HR Ops (company) | Enter dates, approve lifecycle, review impact, hand settlement to payroll |
| Payroll Ops | Compute and pay; close settlement packet |
| Engineering | Idempotent executor, audit events, lag metrics — **no legal discretion** |

### Mechanism (align with existing Wathefni timers)

```
wathefni-lifecycle-effective.timer
  OnCalendar=hourly (SMB/medium) | *:0/15 (enterprise)
  Persistent=true
  → wathefni-lifecycle-effective.service (oneshot)
      → python -c "execute_due_scheduled_terminations(company)"
      for each allowlisted company with LIFECYCLE_V3 on
```

### Reliability requirements

1. **Idempotent:** re-running the same day does not double-terminate.
2. **Auditable:** each effective transition writes `employee_lifecycle_events` with `event_type=termination_effective`, `payload.scheduler=true`, run_id.
3. **Retries:** failed tick leaves rows in `notice_period`; next tick retries; no silent skip.
4. **Monitoring:** metric `lifecycle_effective_lag_seconds` (max of due-but-not-terminated); alert if lag &gt; 2h (medium) / 30m (enterprise).
5. **Kill switch:** `WATHEFNI_EMPLOYEE_LIFECYCLE_V3=off` stops executor; does not rewind history.
6. **Staging first:** enable timer only on staging; prove future-dated → effective overnight; then prod canary.

### Explicit non-automation

Scheduler **may** flip employment to `terminated` and invoke **approved** access-revoke / optional downstream actions configured as policy. It **must not** invent settlement amounts or waive notice.

---

## 6. Exact changes needed before production

These are Wave **3B implementation** items (still not Wave 4). Do not deploy until done and re-proven.

| ID | Change | Why |
|---|---|---|
| P0-1 | Company lifecycle **policy config** (tier, notice hints, revoke mode, warn/block set, TZ) | Encode decisions without hardcoding law |
| P0-2 | Impact **ack** required on create request; store actor + snapshot hash | Irreversible path evidence |
| P0-3 | Split case labels: `cancel_scheduled` vs `reinstate` (API can alias today’s `reversal`) | Clear before/after effective semantics |
| P0-4 | Access revoke executor bound to D3, gated by approval + effective tick; reversible restore path on reinstate | Close the biggest open security gap |
| P0-5 | systemd timer + service + journal + lag alert (staging → prod) | Owned scheduled execution |
| P0-6 | Rehire: **same `employee_key` remap** when phone unchanged; keep `-R` key only for phone change | Child-table compatibility |
| P0-7 | `payroll_settlement_handoff` (or equivalent) packet with no amounts | Clean Payroll boundary |
| P0-8 | Post-effective domain rules as **explicit actions** with audit (cancel shifts / decline leave / abandon onboarding) — SMB warn-first | No silent irreversible ops |
| P0-9 | Counsel review checklist signed for Kuwait defaults | Legal separation |
| P0-10 | Staging re-smoke: future term → timer → revoke → settlement packet → reinstate/rehire; rollback drill | Preserve Wave 3 PASS bar |
| P1-1 | Optional enterprise hard-blocks | Tier support |
| P1-2 | Date override permission + UI copy “not legal advice” | Safer overrides |
| P1-3 | Prod canary: WATHEFNI only, synthetic then 1 real with dual control | Deploy gate after P0 |

**Out of scope for 3B:** Employees 360 UI redesign, Wave 4 child-table cutover, auto EOSB math, pre-hire / Wave D changes.

---

## 7. Preservation of Wave 2 / Wave 3

| Invariant | Status |
|---|---|
| Person / employment / assignment authority | Unchanged |
| Hub `active`/`left` projection | Unchanged |
| Two-person approval | Preserved; strengthened with ack + override reasons |
| Manager scope / idempotency / optimistic concurrency | Preserved |
| No left→active fake rehire | Preserved; same-key rehire still new employment_id |
| Downstream non-automatic legal/payroll decisions | Preserved and tightened via handoff packet |
| Wave 3 staging PASS suite | Must remain green after 3B code |

---

## 8. GO / NO-GO summary

**NO-GO for Wave 3 production deployment now.**

Minimum for a future **GO**:

1. P0-1 … P0-10 complete  
2. Staging timer proof + revoke + settlement handoff evidence pack  
3. Counsel sign-off on Kuwait notice/settlement boundaries  
4. Production flags still WATHEFNI-only with canary plan  
5. Explicit owner for scheduler on-call  

Interactive decision board: Cursor canvas `employees360-wave3b-lifecycle-policy.canvas.tsx`.
