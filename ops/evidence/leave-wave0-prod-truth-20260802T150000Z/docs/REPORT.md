# Leave Wave 0 — production truth & architecture audit

**Stamp:** `20260802T150000Z`  
**Evidence:** `ops/evidence/leave-wave0-prod-truth-20260802T150000Z/`  
**Mode:** read-only (no code/deploy/UI/frozen-module changes)  
**DB:** production `wathefni` · company module `leave` = **enabled** for WATHEFNI  

---

## Objective verdict: **PARTIAL**

Leave is **partially useful in production today** for basic WATHEFNI request → approve/reject/cancel over dashboard, WhatsApp/action-registry, HR mobile, and employee app — but it is **not production-grade leave authority**.

Balances/accrual are **live but observe-only** (`enforced=false`, `legal_reviewed=false`). Missing: self-approval hard ban, employment-lifecycle gates, holiday calendar, balance reservation, partial-day/hourly, attachments/sensitive categories, strong concurrency, and proven Attendance reverse linkage on real prod rows.

| Question | Answer |
|---|---|
| Production-ready end-to-end leave product? | **No** |
| Safe to use for basic HR/manager decisions today? | **Yes, with limits** (manual judgment; balances not binding) |
| Architecturally weak relative to Attendance/E360 freezes? | **Yes** — needs a controlled authority wave before feature expansion |

---

## Production truth (counts)

| Object | Count | Notes |
|---|---:|---|
| `leave_requests` | **3** | WATHEFNI only |
| · requested | 1 | **stale** — start `2026-06-16` (past as of audit) |
| · approved | 1 | sick `2026-05-11` |
| · rejected | 1 | sick `2026-06-12` |
| · cancelled | 0 | (events show historical cancels) |
| `leave_events` | 10 | approved 5 / cancelled 3 / requested 1 / rejected 1 |
| `leave_policies` | 2 | annual + sick · **enforced=0 · legal_reviewed=0** |
| `leave_policy_presets` | 2 | `kuwait_private_2010` |
| `leave_ledger` | 28 | **accrual only** (70.0 annual days posted) |
| `leave_balances` | 4 | all 4 WATHEFNI employees · annual 2026 · balance **17.5** each · consumed **0** |
| `public_holidays` | **0** | holiday exclusion is a no-op |
| Carryover ledger | 0 | |
| Overlapping approved pairs | 0 | |
| Duplicate active windows | 0 | |
| Self-approved (decider phone = employee phone) | 0 | **no code hard-ban**; lucky/absence of abuse |
| Attendance rows linked to leave | **0** | approved leave did not leave durable `approved_leave` provenance in prod |
| Partial/hourly/unpaid/attachment metadata | 0 | |
| Orphan leave (no employee) | 0 | |
| Flags | `WATHEFNI_LEAVE_BALANCES=on` · outbound includes `leave_decision` | |
| Accrual timer | **enabled/active** (`wathefni-leave-accrual.timer`) | |

Source: `prod/truth.json`.

---

## Architecture & data-flow map

```
Employee app / WhatsApp / Dashboard / HR mobile
        │
        ▼
 action_registry (request/approve/reject/cancel)
        │
        ▼
 app.request_leave / approve_leave_request / …
        │
        ├─► leave_requests     ← canonical workflow authority
        ├─► leave_events       ← append-only audit (weak versioning)
        │
        ├─► [on approve] apply_leave_attendance_effect → attendance_records (derived)
        ├─► [on approve/cancel] invalidate_provisional_timesheets (payroll draft only)
        │
        └─► [if LEAVE_BALANCES] observe_leave_consumption → leave_ledger → leave_balances
                 ▲
                 │ monthly
           leave-accrual-worker (observe-only)
                 │
           leave_policies (config; enforced=false)
```

**Canonical vs derived**

| Concern | Canonical | Derived / observe |
|---|---|---|
| Request lifecycle | `leave_requests.status` | — |
| Audit trail | `leave_events` | admin audit on employee app |
| Balance math | `leave_ledger` | `leave_balances` rollup |
| Policy figures | `leave_policies` | presets seed-only |
| Day-off attendance | leave approval | `attendance_records` + authority path |
| Payroll money | **not leave** | provisional timesheet invalidation only |

---

## Leave state model

Observed statuses: `requested` → `approved` | `rejected` | `cancelled`  
(`approved` may also → `cancelled` with attendance reverse + ledger reversal observe)

| Gap | Evidence |
|---|---|
| No `row_version` / optimistic lock beyond approve `status='requested'` | schema |
| Reject UPDATE has no status predicate | `reject_leave_request` |
| No `reopened` / `disputed` / `taken` / `payroll_locked` | schema |
| Stale pending not auto-expired | 1 past-start `requested` in prod |
| No reservation state on request | consume only on approve (observe) |

---

## Policy & balance model

- P1 types: `annual` (30 d/yr monthly accrual, 6-mo eligibility), `sick` (tiers empty, accrual `none`)
- Chargeable days: weekdays minus configured weekends (`fri`,`sat`) minus `public_holidays` (**empty in prod**)
- **No half-day / hourly** in `chargeable_leave_days`
- `allow_negative=false` in policy but **enforcement off** — approvals never check balance
- Accrual uses `date.today()` in catchup (not consistently `kuwait_today`) — timezone risk near midnight
- Sick approved leave did **not** create ledger consume (balances show annual only, consumed 0) — observe path incomplete vs prod history and/or silent failure

**Reservation vs deduction:** request does **not** reserve; approve observes consume; cancel observes reversal. No pending hold.

---

## Permission & ownership matrix

| Actor | Capabilities | Scope / gaps |
|---|---|---|
| Owner/HR (`leave.*` full) | read, request-on-behalf, decide | company-wide |
| Manager / team manager | read + decide | `manager_scope_allows_employee` when `viewer_phone` set |
| Viewer | read | |
| Employee app | request + cancel own | ownership check on cancel; feature-gated |
| Payroll | no leave.decide | sees invalidation side-effect only |
| Self-approval (employee decides own) | **not hard-blocked in `approve_leave_request`** | P0 gap vs E360/onboarding pattern |
| Lifecycle (future-start / suspended / notice / terminated) | **not gated in `request_leave`** | P0/P1 |

Dashboard: PostHire Leave page + Employees 360 leave section (frozen E360 surface — do not redesign for Leave waves).  
Mobile: employee `/app/leave` + HR `LeaveApprovalView` (EN/AR/RTL present in apps).

---

## Attendance / Shifts / Payroll boundaries

| Boundary | Behavior | Risk |
|---|---|---|
| Shifts | Soft conflict on approve; confirmable via `allow_shift_conflicts` | OK for V1 |
| Attendance | Approval derives `approved_leave`; cancel reverses **derived-only** | Prod has **0** leave-linked attendance rows for existing approved leave |
| Attendance freeze | Leave must not weaken punch immutability | Use authority `apply_leave` when enabled; do not rewrite punches |
| Payroll | Invalidates **provisional** timesheets only | Must not invent money from leave |
| Payroll policy `leave_policy` paid/unpaid | Separate company payroll settings | Not wired as leave-type unpaid engine |

---

## Critical risks (ranked)

### P0 — production blockers / safety

1. **No leave self-approval hard ban** in approve path (unlike lifecycle/onboarding/ESS).  
2. **No employment-status gate** on request/approve (terminated/suspended/future-start/notice).  
3. **Balances look authoritative in UI but are non-binding** (`enforced=false`) — risk of HR trusting 17.5 days while approvals ignore them.  
4. **Stale pending request** still open after start date — queue hygiene / wrong operational signal.

### P1 — correctness / authority gaps

5. **`public_holidays` empty** → working-day math wrong once enforcement turns on.  
6. **No balance reservation** → double-booking risk if enforcement enabled later without holds.  
7. **Approve↔Attendance linkage unproven in prod** (0 linked rows) — reversal safety not evidenced on live data.  
8. **Reject lacks status guard**; weak concurrency (no version).  
9. **Sick policy empty tiers** + no consume evidence for approved sick day.  
10. Accrual **`date.today()` vs Asia/Kuwait**.

### P2 — product completeness (not blockers for basic use)

11. No partial-day / hourly.  
12. No unpaid leave type workflow.  
13. No attachments / sensitive-category privacy.  
14. No carryover implementation despite ledger kind.  
15. Dashboard/employee EN-AR polish secondary to authority.

---

## Stay / move / remove / rebuild

| Item | Recommendation |
|---|---|
| `leave_requests` + `leave_events` workflow | **Stay** — canonical |
| Overlap check + manager scope + shift soft-conflict | **Stay** |
| Action registry leave executors + employee app ownership cancel | **Stay** |
| Observe-only ledger/balances + accrual timer | **Stay** but label clearly non-binding until legal review |
| Kuwait presets `enforced=false` | **Stay** until counsel |
| Direct UI redesign / new leave types / enforcement on | **Do not** until Wave 1 authority |
| Duplicate “leave_policy” payroll string vs leave_policies | **Clarify boundary** — don’t merge carelessly |
| Rebuild from scratch | **No** — harden in place |

---

## Recommended phased plan

| Wave | Goal | Freeze impact |
|---|---|---|
| **0** | Truth + architecture (this doc) | none |
| **1** | Authority & safety hardening | no frozen module edits |
| **2** | Balance/policy correctness (holidays, reservation, sick tiers) still observe or counsel-gated enforce | |
| **3** | Partial-day / unpaid / attachments | |
| **4** | UX polish EN/AR after authority green | don’t touch E360/Onboarding/Attendance freezes |

---

## Exact first implementation wave — **Leave Wave 1: Authority & safety**

**In scope (backend + tests only; no UI redesign; no enable `enforced=true`):**

1. Fail-closed **self-approval forbidden** on decide (approve/reject/cancel-of-others) when actor phone == employee phone (HR-on-behalf request still allowed).  
2. **Employment lifecycle gates** on request/approve: block terminated/suspended; warn or block future-start & notice-period per explicit policy knobs.  
3. **Stale-pending policy**: expire or surface past-start `requested` (deterministic rule + audit event).  
4. Reject/cancel **status predicates** + optional `expected_updated_at` / row version.  
5. Explicit API/UI flag `balances_enforced=false` in payloads so clients cannot imply binding balances.  
6. **Normalize leave-type vocabulary** (`vacation`/`time_off` → canonical `annual`/`sick`/…) so observe consumption cannot silently skip.  
7. **Lifecycle status hygiene**: map `declined_lifecycle` / reverse-to-`pending` onto the primary state machine (or document as E360-owned terminal with no approve path).  
8. Synthetic staging canary: self-deny, scope-deny, overlap, cancel reverse path, no payroll money mutation, no Attendance freeze regressions.  
9. Seed/document holiday calendar path (may stay empty until ops provides dates — but code path tested).

**Out of scope for Wave 1:** enabling legal enforcement, partial-day, attachments, carryover, UI redesign, real payroll postings, changes to frozen Employees 360 / Onboarding / Attendance / pre-hiring / Wave D (lifecycle *hooks* must not rewrite frozen E360 behavior — only leave-side status compatibility).

---

## Tests & qualification required (Wave 1)

- Unit/smoke: self-approval deny; lifecycle deny; overlap; reject race; cancel reverse attendance (synthetic); ledger observe idempotency.  
- Staging E2E canary + cleanup.  
- Production: **read-only** posture check first; synthetic-only canary if promoted later.  
- Regression: Employees 360 / Onboarding / Attendance freeze smokes must stay green.  
- Explicit non-goals checklist in qualify script (no `enforced=true`, no CAPTURE_INGEST, no payroll money).

---

## Bottom line

**PARTIAL GO for constrained HR/manager leave decisions on WATHEFNI.**  
**NO-GO for “production-complete leave product,” balance enforcement, or payroll/attendance authority expansion** until Wave 1+ lands.

---

## Addendum — codebase inventory follow-up

Supplement from [Explore Leave module codebase](3ec37485-3860-470c-943c-4d1f6d777351) (read-only). Does not change the PARTIAL verdict; adds precision for Wave 1 scoping.

### Additional surfaces
| Surface | Path / symbol |
|---|---|
| HR operator mobile API | `operator_mobile_data.mobile_leave_*` · `/dashboard/mobile/leave*` |
| E360 termination leave impact | `employee_lifecycle_wave3` open-leave snapshot |
| E360 decline open leave | `employee_lifecycle_wave3c.decline_open_leave` / `reverse_decline_open_leave` |
| Staging leave→payroll proof | `ops/authority-p0-leave-payroll-proof.py` |
| Accrual worker | `leave-accrual-worker.py` + `ops/wathefni-leave-accrual.{service,timer}` |

### Additional P1 gaps
1. **Leave-type vocabulary drift** — WhatsApp `infer_leave_type` can yield `vacation` / `time_off`, while P1 observe consumption only runs for `_LEAVE_P1_TYPES = ("annual","sick")`. Dashboard files `annual`/`sick`. Risk: approved “vacation” never hits ledger even when balances are on.  
2. **Lifecycle status pollution** — `declined_lifecycle` written on termination decline; reverse restores **`pending`**, which is **not** in the primary `requested|approved|rejected|cancelled` machine or `LEAVE_HISTORY_STATUSES` approve path.  
3. **Manager cannot `leave.request`** — intentional (`_POSTHIRE_PERMS_MANAGER` has decide, not request); document so Wave 1 does not “fix” it by accident.  
4. **Stale table name in attendance canaries** — some canaries still probe `employee_leave_balances`; live table is `leave_balances`.  
5. **No Leave freeze/completion doc** — unlike Attendance / Onboarding / Employees 360 (expected until Wave 1+ closes).  
6. **Payroll `leave_policy` paid/unpaid** is a separate payroll settings knob — not leave-module unpaid authority.

### Permission nuance (confirmed)
| Role tier | `leave.request` | `leave.decide` |
|---|---|---|
| Owner / HR admin / HR manager | yes | yes |
| Manager / team manager / hiring manager | **no** | yes |
| Viewer | no | no |
| Employee app | self request/cancel via `/app/leave*` | n/a |

### Schema note
Leave DDL is **inline bootstrap in `app.py`** (~leave_requests through leave_balances + public_holidays) — no dedicated versioned leave `*.sql` pack as product SoT.
