# Payroll Wave 0 — production truth, money-authority and architecture audit

**Stamp:** `20260803T034802Z`  
**Mode:** read-only (no calculate/post/approve/pay/mutate of real payroll money)  
**Evidence:** `ops/evidence/payroll-wave0-20260803T034802Z/`  
**Company scope:** WATHEFNI only  

## Objective verdict

**NO-GO** for production money authority, payslips, bank files, EOS calculation, accounting journals, or any payment rail.

**PARTIAL** for a provisional hours → timesheet → preview → locked CSV-export review surface. That surface exists, is entitlement-gated, and hard-forces `payment_processing=disabled`. It is **not** payroll money.

Do not deploy, enable real payroll calculations, generate payment files, change employee compensation, alter frozen modules, or add XBRL without a specific proven requirement.

---

## Production truth and counts

| Item | Count / value |
|---|---|
| `company_modules.payroll` enabled | WATHEFNI = true |
| `payroll_timesheets` | **2** (both `draft`) |
| Approved / rejected timesheets | **0 / 0** |
| `payroll_exports` | **0** |
| `payroll_policies` | **1** (WATHEFNI) |
| Policy `payment_processing` | **disabled** (hard-forced in code) |
| Policy pay type | `monthly`, hourly rate `null` → preview amounts = `monthly_salary_not_configured` |
| Period with rows | 2026-05-11 → 2026-05-17 (Fouad + Mohammad; smoke residue) |
| Timesheet events | draft_refreshed 2 · approved 2 · draft_restored_after_smoke 2 · recalculation_required 4 |
| Employees (WATHEFNI) | 76 total · ~66 active-ish |
| Attendance records | 42 |
| `attendance_payroll_snapshots` | **0** |
| Day projections / payroll_eligible | 2 / **0** |
| Scheduled shifts (last 90d) | 81 |
| Approved leave requests | 3 |
| Leave rows with `payroll_handoff` | 0 |
| Employment offers with `base_salary` | 1 (`9000.000` KWD, empty allowances) |
| Employees with salary in `raw_json` | 0 |
| ESS bank profiles | 0 |
| Lifecycle settlement packets | 0 |
| Explicit `payroll.*` permission grants | 0 (owners inherit via role defaults) |

**Demo / anomaly note:** The only timesheets are May 2026 smoke artefacts. They were approved once by LLM planner smoke (`Approve timesheets`), then restored to draft. Leave canaries later marked them `recalculation_required` then the current status is again `draft` / `Ready`. **No real payroll period has ever been closed.**

---

## What Payroll currently does

Live pipeline:

```
Shifts (scheduled) + Attendance (records OR authority snapshots) + Leave (approved)
        ↓
list_payroll_hours  →  authority=provisional, money_authority=approved_timesheets
        ↓
create_timesheet_review  →  payroll_timesheets (draft; skips existing approved)
        ↓
approve_timesheet / reject_timesheet  →  approved timesheets = declared money authority
        ↓
preview_payroll  →  payable minutes + optional hourly estimate (monthly = not configured)
        ↓
export_payroll  →  payroll_exports export_kind='payroll_preview' + CSV download
```

Hard safety already present:

- `clean_payroll_policy` always sets `payment_processing="disabled"`
- Preview/export totals echo `payment_processing: "disabled"`
- Export tool copy: does not process payments or create bank files
- Leave unpaid handoff asserts **no money fields**
- Lifecycle settlement packets are **inputs-only** (`handed_to_payroll`); EOSB reserved
- Neighbor freezes (Attendance / Leave / Shifts / Employees 360) declare payroll money **NO-GO** / “Payroll owns money later”

**Does not exist:** payslips, salary-component engine, bank/WPS files, EOS/EOSB calculators, accounting journals, XBRL, dual-control period close, effective-dated salary contracts consumed by Payroll, employee-app payslip surface (`payslips` reserved, `implemented: False`).

---

## Canonical money authority (today)

| Layer | Authority claim | Reality |
|---|---|---|
| Live hours | `authority: provisional` | Recalculable; not money |
| Draft / rejected timesheets | Provisional | Invalidated on leave change |
| **Approved timesheets** | **`money_authority: approved_timesheets`** | Hours authority only — **no salary applied** |
| Preview amounts | Estimate | Hourly only if rate set; monthly always `monthly_salary_not_configured` |
| Export | Locked **preview snapshot** | Not a payment file; locks attendance mutation for period dates |

**Canonical money authority for KWD net/gross does not exist.** The closest frozen claim is “approved timesheets are money authority,” but that authority is **hours**, not money. Neighbor modules correctly refuse to calculate money.

---

## Canonical payroll state model (as implemented)

Timesheet statuses: `draft` → `approved` | `rejected`  
Dirty signal: `payroll_status='recalculation_required'` (blocks approve)  
Export statuses: `exported` (only observed kind: `payroll_preview`)  
Policy: single row per company (`payroll_policies.settings` jsonb), events in `payroll_policy_events`

Missing vs a real payroll run model: period entity, period lock/close, run version, payslip lines, payment batch, reversal/rerun, dual-control gates.

---

## Salary-component model

| Source | Exists? | Consumed by Payroll? |
|---|---|---|
| `employment_offers.base_salary` / `allowances_json` | Yes (1 prod offer) | **No** |
| Employee master salary / effective dates | **No** | — |
| Recurring allowances / deductions registry | **No** | — |
| ESS bank / IBAN | Table exists, **0 rows** | Not used in calc |
| Policy `default_hourly_rate_kwd` | Optional | Only for hourly preview |
| Monthly salary in Payroll | **Not configured** | Preview status `monthly_salary_not_configured` |

**Source-of-truth salary components: undefined.** Offer salary is pre-hire terms, not a post-hire compensation ledger.

---

## Attendance / Leave / Shifts handoff matrix

| Upstream | Fields consumed | Payroll use | Money? |
|---|---|---|---|
| Shifts `shift_assignments` | `employee_key`, `shift_date`, `start_time`, `end_time`, `status='scheduled'` | `scheduled_minutes`; leave-day scheduled minutes → leave minutes | No |
| Attendance legacy `attendance_records` | check-in/out, late/early, status, scheduled window | `worked_minutes`, late/early/absent | No |
| Attendance authority `attendance_payroll_snapshots` | payload worked/late/early/status | Preferred when authority enabled | No |
| Attendance projections | `payroll_eligible` | Eligibility gate on authority path | No |
| Attendance ops | `payroll_excluded`; date lock via approved timesheet/export | Exclude / block mutate | No |
| Leave approved `leave_requests` | date overlap | Approved leave minutes; invalidate provisional timesheets | No |
| Leave unpaid handoff | chargeable days/hours, classification | Classification only (`assert_handoff_has_no_money`) | **Forbidden** |
| Lifecycle settlement | `handed_to_payroll` inputs | Reserved for future EOS | Amounts **forbidden** |

**Production path reality:** `WATHEFNI_ATTENDANCE_AUTHORITY=on` **and** `SYNTHETIC_ONLY=on` → real subjects still use the **legacy** `attendance_records` path; snapshot count is **0**.

---

## Permission and approval matrix

| Role / grant | Permissions | Notes |
|---|---|---|
| Owner / full HR | `payroll.read` · `manage` · `export` | Both owners inherit all three |
| Team manager | `read` · `manage` (no export) | Scope via `viewer_phone` |
| Viewer | `read` | — |
| `payroll_operator` | read · manage · export | Least-privilege role template |
| ESS | `employees.ess.approve.payroll` | Bank/ESS path, not pay calc |
| Tenant-control SOD | pair `payroll.approve` × `payroll.export` | **Runtime tools use `payroll.manage`, not `payroll.approve`** → SOD pair is ineffective |

Gaps:

- No hard ban that timesheet creator ≠ approver  
- No hard ban that employee phone ≠ approver  
- Same role can approve timesheets **and** export  
- No dual-control period close  

---

## Calculation and rounding inventory

| Calculation | Formula / rule | Provenance | Safe for money? |
|---|---|---|---|
| Scheduled minutes | shift end − start | Code only | Hours OK |
| Worked minutes | checkout − checkin (legacy) or snapshot | Code only | Hours OK |
| Overtime minutes | `max(0, worked − scheduled)` | Code only; **not** Art. 66 premiums | **No** |
| Payable minutes | worked + paid leave − deductions − OT capped excess | Policy flags | Minutes only |
| Estimated amount | `(payable/60) * hourly_rate` rounded **3 dp** | Only if hourly + rate set | Preview only |
| Monthly amount | — | Always `monthly_salary_not_configured` | **None** |
| OT premium +25%/+50% | — | Research flags counsel-required | **Not implemented** |
| EOS / PIFSS | — | Explicitly out of P0 in Kuwait research | **Not implemented** |
| Proration / join / depart | — | — | **Not implemented** |

---

## Audit / reversal / locking posture

| Control | Present? | Notes |
|---|---|---|
| Timesheet event log | Yes | `payroll_timesheet_events` |
| Policy event log | Yes | `payroll_policy_events` |
| Export event log | Yes | `payroll_export_events` |
| Approved timesheet immutability on leave change | Yes | Only draft/rejected invalidated |
| Attendance date lock after approve/export | Yes | `_ai_date_locked` |
| Concurrency token on timesheet approve | **No** | Status=`draft` predicate only |
| Idempotency keys on approve/export | **No** | Export always inserts a new row |
| Reversal / rerun of approved money | **N/A** | No money postings |
| Period lock entity | **No** | Export presence acts as soft lock |

---

## Legal and policy source matrix

| Topic | Class | Source posture | Product rule today |
|---|---|---|---|
| Wage elements (basic + contractual allowances) | Statutory KW | Art. 55–56 | Store later; **not in Payroll** |
| Overtime premium / written order / OT record | Statutory KW | Art. 66; Worker’s Guide | Minutes stored; policy `review_only`; **no premium calc** |
| Sick-leave wage bands | Statutory KW | Art. 69 — counsel confirm | Not enforced |
| EOS / terminal indemnity | Statutory KW | Art. 51–53; Law 17/2018 | **No auto-EOS**; lifecycle inputs only |
| PIFSS vs expat EOS pathways | Statutory / counsel | Research CQ | Design rule only |
| Leave paid vs unpaid impact | Company policy | Policy pack | `leave_policy` paid/unpaid/review_only |
| Absence / late / early deductions | Company policy | Policy jsonb | Boolean flags |
| OT pay vs review vs ignore vs cap | Company policy | Policy jsonb | Default `review_only` |
| Bank / IBAN for salary | Accounting / bank practice | Research O6 | ESS table empty |
| WPS / bank file / journals / XBRL | Accounting export | No proven requirement | **Out of scope** |
| Manual exceptions | Manual | Ops | Attendance `payroll_excluded`; timesheet reject |

Separate clearly:

1. **Statutory Kuwait** — store evidence, do not auto-enforce premiums/EOS until counsel signs.  
2. **Company-configurable policy** — today’s `payroll_policies.settings`.  
3. **Accounting/export** — preview CSV only; no bank/journal/XBRL.  
4. **Manual exceptions** — attendance exclusion + timesheet reject/review flags.

---

## Critical risks (with evidence)

### P0

1. **No production money authority** — approved timesheets are hours only; monthly salary not wired; cannot pay. Evidence: policy + preview status; 0 exports; 0 payslip tables.  
2. **No salary-component source of truth for Payroll** — one offer salary exists but is not consumed; employees have no salary master. Evidence: `employment_offers` sample; `employees` salary-json count 0.  
3. **Timesheet self-approval not hard-blocked** — `decide_timesheets` has no actor≠creator / actor≠employee check. Evidence: `app.py` `decide_timesheets`.  
4. **SOD pair is dead** — `tenant_control_roles.SOD_CONFLICT_PAIRS` uses `payroll.approve`, runtime uses `payroll.manage`. Evidence: `tenant_control_roles.py` vs tool map.  
5. **Attendance authority synthetic-only on production company** — real hours still come from legacy `attendance_records`; snapshot table empty. Evidence: env + snapshot count 0.

### P1

6. **Naive overtime** (`worked − scheduled`) with no written-order flag or premium table.  
7. **Stale smoke timesheets** still present for May 2026.  
8. **Export inserts unbounded history** (no idempotency); period “lock” is side-effect of any preview export.  
9. **Owner phone formatting drift** (Fouad dashboard `66363363` vs employee `96566363363`) can break digit-based actor matching.  
10. **No period/run model** — cannot close, reverse, or rerun a pay period as a first-class object.

### P2

11. Employee-app `payslips` key reserved but unimplemented.  
12. Policy settings lack immutable version fingerprint on every preview row (export stores a snapshot, live preview does not version-pin beyond current policy row).  
13. Rounding to 3 decimal KWD without counsel-approved monetary rules.

---

## Architecture / data-flow (summary)

```
[Shifts L0 assignments]──┐
[Attendance records|snaps]──┼──► list_payroll_hours (provisional)
[Leave approved requests]──┘              │
                                          ▼
                               payroll_timesheets (draft)
                                          │ approve
                                          ▼
                               approved timesheets  ≈  hours money_authority
                                          │
                                          ▼
                               preview (minutes ± hourly estimate)
                                          │ export
                                          ▼
                               payroll_exports (payroll_preview CSV)
                                          ✗  no bank / payslip / journal / EOS
```

UI: dashboard `PayrollPage` (post-hire). Mobile employee: no payslips. HR mobile: hub tile only if `payroll.read`. WhatsApp: hours/status; blocks salary/bank/payment asks.

---

## Recommended phased plan

| Wave | Goal | Mutates real money? |
|---|---|---|
| **0 (this)** | Production truth + architecture audit | No |
| **1** | Money-authority foundation: salary contracts + effective dates, SOD/self-approval bans, period model, attendance handoff truth for real subjects, freeze hours pipeline | **No payment** |
| **2** | Calculation engine with policy/version provenance; OT/leave/absence as company policy; Kuwait defaults remain review-only until counsel | Preview amounts only |
| **3** | Payslips + employee visibility + sensitive-data permissions | Still no bank file |
| **4** | Bank / salary export after counsel + bank contract proof | Controlled canary |
| **5** | EOS worksheet after counsel (no auto-claim) | Controlled |
| **6** | Accounting journals only if a specific proven requirement appears | Controlled |

Frozen modules (Employees 360, Onboarding, Attendance, Leave, Shifts) stay unchanged except documented handoff contracts.

---

## Exact first implementation wave

**Payroll Wave 1 — Money-authority foundation (no payment processing)**

Must deliver:

1. Effective-dated **salary contract / component ledger** (base + allowances + deductions) owned by Payroll, seeded from accepted offer terms without silent derivation.  
2. Hard bans: no self-approve timesheet; fix SOD to `payroll.manage` × `payroll.export` (or introduce real `payroll.approve` and wire it).  
3. First-class **pay period** entity with lock/close semantics (replace “export exists ⇒ locked”).  
4. Resolve attendance handoff: either promote real subjects onto approved snapshots under controlled allowlist, or explicitly freeze legacy `attendance_records` path with honesty flags.  
5. Retire/quarantine May 2026 smoke timesheets.  
6. Keep `payment_processing=disabled`; no bank files, payslips, EOS math, or XBRL.  
7. Wave 1 evidence pack + freeze gates before Wave 2 calculations.

---

## Freeze boundary reminder

Sibling freezes already require: Attendance/Leave/Shifts must not calculate Payroll money; lifecycle settlement must not embed EOS amounts; PAM remains export-only. Wave 0 confirms those boundaries are still holding in code and production data.
