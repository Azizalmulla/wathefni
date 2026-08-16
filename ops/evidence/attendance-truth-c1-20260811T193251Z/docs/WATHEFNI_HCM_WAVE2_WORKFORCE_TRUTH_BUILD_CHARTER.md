# Wave 2 — Workforce Truth Build Charter

**Status:** APPROVED — `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED` (owner 2026-08-11)  
**Execution authority parent:** `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` §4  
**Prior gate:** `WAVE1_PRODUCT_FULL_PASS` accepted 2026-08-11 — Wave 1 remains frozen (`ops/WAVE1_PRODUCT_FREEZE.md`)  
**Audit SoT:** 111-capability HCM gap audit  
**Charter date:** 2026-08-11 · **Approved:** 2026-08-11  
**Scope:** Wave 2 — Workforce Truth (attendance → leave → shifts/MSS → payroll → payslips/payment → settlement)  
**Implementation gate:** Open for **C1 Attendance Truth only**; stop after each C-slice stamp for review.

---

## 0. Charter principles (non-negotiable)

### 0.1 Modularity (same as Wave 1)

| Rule | Requirement |
|---|---|
| Independent enablement | Every Wave 2 module works alone when enabled |
| Composability | Peers integrate only through **explicit capability contracts** — never silent hard wiring |
| Hard deps only when true | Catalog `depends_on` only for HARD DEPENDENCY |
| Clean disappearance | Disabled modules vanish from HR Web, HR Mobile, Employee App, Assistant — no empty shells |
| Premium small suites | e.g. Attendance-only, Leave-only, or Payroll+Attendance tenants still feel intentional |
| Full-suite richness | Entitled multi-module tenants get connected time → pay truth |
| Canonical truth | Shared `employees` / employment / org / `hr_tasks` / approvals — no per-module duplicate SoT |

### 0.2 Dependency classes

| Class | Definition |
|---|---|
| **HARD DEPENDENCY** | Cannot enable or operate Module B without A |
| **OPTIONAL INTEGRATION** | B works alone; when A enabled, a versioned contract connects them (company-configurable) |
| **ENHANCEMENT WHEN ENABLED** | B works alone; A present improves UX/automation/analytics only |

### 0.3 Dynamic navigation

Runtime nav = `enabled company modules ∩ permission grants ∩ surface capability matrix`.  
Zero visible children → omit the group entirely.

### 0.4 Wave 1 freeze boundary

- Do **not** reopen Wave 1 Hire→Ready SMs for safe debt.
- Wave 1 safe debt (N-step requisition binding, live channel reminder fan-out, Setup card OTA, broad Wave 1 rollout) stays documented; Wave 2 may consume platform approvals/tasks/SLA for **leave/OT/payroll** subjects without rewriting Wave 1 modules.
- Wave 1 remains **WATHEFNI-canary only** until a separate owner decision — Wave 2 canaries are independent entitlements.

### 0.5 Out of scope for this charter

- Wave 3+ lifecycle/clearance/letters product (settlement **pay path** is in; exit clearance module is not)
- Wave 4 Performance/Talent
- Wave 5 executive KPI suite (emit facts only)
- Wave 6 Benefits/ER/L&D
- Global unlock of BioTime ingest, leave `enforced=true`, or payroll money for all tenants
- Inventing parallel punch/leave/pay ledgers outside existing module authorities
- E360 / Employees 360 performing payroll money math (inputs-only forever)

---

## 1. Exact scope

**Goal:** Time and pay numbers are authoritative enough to run a real payroll cycle for an entitled company — not synthetic demos.

### 1.1 Serial core (customer-facing chain)

```text
Real attendance capture
  → Correction authority (approve → apply)
  → Enforced leave (balances bind requests)
  → Production shifts / MSS
  → Authoritative payroll finalize
  → Payslips + payment files
  → Final settlement (pay)
```

OT authorization is in-scope as a thin attendance↔payroll contract.

### 1.2 Workstreams

| ID | Workstream | Deliverable |
|---|---|---|
| W2.1 | Attendance capture | Company-entitled punch ingest → append-only punches → day projections; synthetic history stays labeled |
| W2.2 | Attendance corrections | Exception cases; manager/HR approve → **apply** mutates projection; employee dispute path |
| W2.3 | Leave enforcement | Legal-reviewed KW pack; `enforced=true` per company; request rejected when insufficient (unless unpaid/override) |
| W2.4 | Leave N-step + delegation | Bind leave requests to Phase A `workflow_approvals` + delegation |
| W2.5 | Leave carry / encashment hooks | Carry writers; encashment as **payroll input** only |
| W2.6 | Shifts production MSS | Non-empty manager allowlist with scope; roster/open/swap/claim; self-decision still banned |
| W2.7 | Authoritative payroll | Period → snapshot → calculate → approve → **finalize** seals period for entitled Mode A/B companies |
| W2.8 | Payslips | Release gate; employee sees only released; bilingual PDF/fields |
| W2.9 | Payment files | Bank/WPS export; `payment_processing` company-gated + kill switch |
| W2.10 | Final settlement (pay) | Lifecycle/exit inputs packet → payroll settlement run → payslip/payment inputs; no E360 money math |
| W2.11 | OT authorization | Thin `ot_request` SM; approved OT → payroll input component |
| W2.12 | Surfaces + Setup | HR Web / HR Mobile / Employee App / Assistant (confirm-mutate optional) / channels; Setup Console Wave 2 policies |
| W2.13 | Cross-cutting | EN/AR+RTL, RBAC/manager scope, analytics fact emits, company-scoped flags, qualify/rollback |

### 1.3 Explicit non-goals

- Forcing Attendance to require Shifts (or vice versa) — schedule may be optional for projection
- Forcing Leave to require Payroll (balances work; encashment contract only when payroll on)
- Forcing Payroll to require Attendance/Leave/Shifts — **payroll independence is non-negotiable**: authoritative runs from manual/imported/external inputs even when Wathefni Attendance/Leave/Shifts are disabled
- Marketing “complete HCM” after Wave 2 alone
- Broad production enable beyond named canary companies without owner gates
- **Assistant mutations** in Wave 2 MVP (`ASSISTANT_MUTATIONS` stays off; Assistant remains read/explain/deep-link only — mutation unlock needs its own later charter)
- Silent expansion of payment-file generate/ack into **direct money movement** / live bank push
- Turning leave `enforced=true` without an explicit company legal/policy pack

---

## 2. Starting posture (honest inventory)

Wave 2 is primarily **EXTEND + unlock**, not greenfield:

| Area | Today (summary) | Wave 2 change |
|---|---|---|
| `attendance` | Capture/exceptions scaffolding; ingest often off; corrections may not apply | Entitled ingest on; approve→apply |
| `leave` | Ledger + UI; often `enforced=false` / observe-only | Entitled enforcement + N-step |
| `shifts` | Deep product; empty manager allowlists = dead MSS | Allowlist unlock + scope |
| `payroll` | Waves 1–5 scaffolding; synthetic / external / preview / payslip / export freezes | Authoritative finalize for entitled; payment_processing gated |
| Phase A | Approvals + tasks + SLA proven | Bind leave/OT (and payroll approval subjects as needed) |
| Wave 1 employment | Hire→Ready frozen; `pending_start` excluded from W2 domains | Active employment only for punches/leave/shifts/pay |

Existing freezes (attendance/leave/shifts/payroll wave freezes) remain until Wave 2 workstreams explicitly amend them with dated notes + re-qualify.

---

## 3. Dependency matrix

### 3.1 Module independence

| Module | HARD depends_on | Works alone when |
|---|---|---|
| `attendance` | Active employment + company/RBAC | Punches + projections + corrections without leave/shifts/payroll |
| `leave` | Active employment + company/RBAC | Request/approve/balances without attendance/payroll |
| `shifts` | Active employment + company/RBAC | Roster/MSS without attendance/payroll |
| `payroll` | Employment + compensation contracts + company/RBAC | Run/finalize from contracts + manual/imported inputs without live attendance/leave |

### 3.2 Capability contracts (OPTIONAL / ENHANCEMENT)

| Contract ID | Class | Modules | Company setting (illustrative) | Behavior |
|---|---|---|---|---|
| `attendance.project_against_shifts` | OPTIONAL INTEGRATION | attendance, shifts | `attendance.use_shift_schedule` | Day projection uses published roster when both on; else policy/default schedule |
| `attendance.feed_payroll_hours` | OPTIONAL INTEGRATION | attendance, payroll | `payroll.inputs.attendance=true` | Finalized/approved projections → payroll period inputs |
| `attendance.ot_to_payroll` | OPTIONAL INTEGRATION | attendance, payroll | `payroll.inputs.ot=true` | Approved `ot_request` → pay component |
| `leave.enforce_balances` | HARD for enforcement feature | leave (+ legal pack) | `leave.enforced=true` | Feature inside leave — not a second module |
| `leave.n_step_approvals` | OPTIONAL INTEGRATION | leave, workflow_approvals | leave approval policy bound | Single-step fallback until bound |
| `leave.encashment_to_payroll` | OPTIONAL INTEGRATION | leave, payroll | year-end / exit policy | Encashment quantity → payroll input; money in payroll only |
| `leave.overlap_attendance` | ENHANCEMENT WHEN ENABLED | leave, attendance | — | Conflict hints / auto-exception; leave remains SoT for approved absence |
| `shifts.mss_manager_allowlist` | HARD for MSS mutate | shifts | non-empty allowlist + scope | Empty allowlist = read-only / blocked mutate (honest) |
| `shifts.feed_attendance_expected` | OPTIONAL INTEGRATION | shifts, attendance | same as project_against_shifts | Expected punches / open-shift coverage |
| `payroll.finalize_authoritative` | HARD for money authority | payroll | Mode A/B entitlement; not synthetic-only | Finalize seals period |
| `payroll.payment_processing` | OPTIONAL INTEGRATION | payroll (+ bank/WPS adapter) | `payment_processing=enabled` + kill switch | File generate/ack |
| `payroll.payslip_release` | HARD for employee visibility | payroll | release action | Employee sees released only |
| `payroll.settlement_from_lifecycle` | OPTIONAL INTEGRATION | payroll, lifecycle/exit inputs | settlement packet present | Wave 2 delivers pay path; Wave 3 makes exit close depend on ack |
| `payroll.inputs_from_leave` | OPTIONAL INTEGRATION | leave, payroll | `payroll.inputs.leave=true` | Unpaid/deduction/encashment inputs |

### 3.3 Platform reuse (not sold modules)

| Platform | Wave 2 use |
|---|---|
| `workflow_approvals` + delegation | Leave N-step, OT approve, optional payroll approve chain |
| `hr_tasks` + SLA | Correction pending, leave pending, OT pending, payroll finalize/release, payment file ack, settlement |
| Setup Console + `module_catalog` | Entitlements + Wave 2 policy cards (ingest, enforce, allowlist, payment_processing, input feeds) |
| Notification / channels | Delivery only — same APIs as Web/Mobile; no parallel workflow state |
| Assistant | Read first; confirm-mutate only behind separate flag + confirm UX |

---

## 4. Canonical entities and state machines

### 4.1 Attendance

#### `attendance_punch` (append-only)

```text
ingested → (immutable)
```

- Device/adapter source, timezone Asia/Kuwait, branch rules
- Never update-in-place; corrections create adjustment events

#### `attendance_day_projection`

```text
open → locked | corrected → locked
```

- Derived from punches (+ optional shift schedule contract)
- Correction apply writes a new projection version / adjustment — audit before/after

#### `attendance_exception` / correction case

```text
open → pending_approval → applied | rejected | cancelled
```

- Employee dispute may open case; manager/HR decide; **applied** mutates projection

#### `ot_request` (thin)

```text
draft → pending_approval → approved | rejected | cancelled → (payroll_exported)
```

### 4.2 Leave

#### `leave_request`

```text
draft → pending_approval → approved | rejected | cancelled
```

- When `leave.enforced=true`: create/submit fails closed on insufficient balance (except unpaid/override with permission + audit)
- N-step via `approval_instance` when policy bound

#### `leave_ledger` / balances

- Append-only ledger movements; UI balances are projections of ledger
- Carry-over job writes ledger; encashment writes **quantity entitlement** consumed + payroll input row (not money)

### 4.3 Shifts / MSS

#### Existing `shift_assignment` / open shift / swap SMs (extend)

- Publish templates (HR)
- Manager roster / open / swap within **scope ∩ allowlist**
- Employee view / ack / claim / swap request
- **Self-decision banned** (manager cannot approve own swap as final authority)

### 4.4 Payroll

#### Period run

```text
open → snapshotted → calculated → pending_approval → approved → finalized
                                                      ↘ rejected → calculated
```

- **Finalized** is authoritative for entitled companies (immutable inputs sealed; corrections = next period / adjustment run)
- Synthetic / preview tenants remain labeled non-authoritative

#### Payslip

```text
generated → released | voided
```

- Employee App/Web: released only

#### Payment file

```text
draft → generated → acknowledged | failed | cancelled
```

- Requires `payment_processing` entitlement; kill switch halts new generates

#### Settlement run (pay)

```text
inputs_ready → calculated → approved → finalized → (payslip/payment)
```

- Inputs from lifecycle/exit packet + leave encashment + EOSB worksheets (Kuwait)
- E360 remains inputs-only

---

## 5. Module catalog / Setup Console

### 5.1 Commercial modules (existing keys — entitle carefully)

| module_key | Wave 2 Setup ownership |
|---|---|
| `attendance` | Ingest on/off, schedule contract, correction SLA, OT policy |
| `leave` | `enforced`, legal pack version, approval policy bind, carry/encashment hooks |
| `shifts` | MSS allowlist, manager scope, Ramadan/seasonal policy refs |
| `payroll` | Mode A/B, input feeds (attendance/leave/OT), payslip release, payment_processing, settlement |

### 5.2 Company settings (illustrative — finalize in design review)

| Setting | Default | Notes |
|---|---|---|
| `attendance.ingest_enabled` | false | Company canary only |
| `attendance.use_shift_schedule` | true if both on else false | OPTIONAL INTEGRATION |
| `leave.enforced` | false | Legal pack required before true |
| `leave.approval_policy_id` | null | Falls back to single-step domain decide |
| `shifts.mss_allowlist` | empty | Empty = no manager mutate |
| `payroll.authoritative_finalize` | false | Synthetic stays default |
| `payroll.inputs.attendance` / `.leave` / `.ot` | false | Explicit contracts |
| `payroll.payment_processing` | disabled | Kill-switchable |
| `payroll.payslip_auto_release` | false | Prefer explicit release |

No long-term env-only customer configuration where Setup Console ownership is required.

---

## 6. Permissions / RBAC / manager scope

| Permission (additive / extend) | Module |
|---|---|
| `attendance.read` / `monitor` / `correct` / `apply_correction` | attendance |
| `attendance.ot_request` / `ot_approve` | attendance |
| `leave.request` / `approve` / `adjust_balance` / `override_enforcement` | leave |
| `shifts.read` / `publish` / `roster` / `mss_decide` | shifts |
| `payroll.run` / `approve` / `finalize` / `release_payslip` / `export_payment` / `settlement` | payroll (SoD: approve × export) |
| Platform `approvals.decide` / `delegate` | leave/OT/payroll subjects |

Manager scope: corrections, leave approve, roster/MSS — reports-only unless HR.  
Employee: own punches/disputes, leave request, shift view/claim, released payslips only.

---

## 7. Surfaces

| Capability | HR Web | HR Mobile | Employee App | Assistant | Channels |
|---|---|---|---|---|---|
| Attendance monitor / exceptions | Strong | Strong | Punch/dispute | Read; confirm correct later | Notify |
| Leave request / approve | Strong | Strong | Strong | Confirm approve optional | Notify |
| Shifts / MSS | Strong | Strong | Strong | Tools/read | Remind |
| Payroll run / finalize | Strong | Thin (status) | — | Read | Notify HR |
| Payslips | Strong | Thin | Strong | Read | Notify release |
| Payment files | Strong | — | — | Read | — |
| Settlement | Strong | Thin | Thin (receive) | Read | Notify |

Empty shell rule applies. Payroll-only tenant must not show empty Attendance/Leave groups.

---

## 8. Workflows by persona (happy path)

### 8.1 HR

1. Entitle modules + Setup policies (ingest, enforce, allowlist, payment_processing)  
2. Monitor attendance exceptions; apply corrections  
3. Configure leave pack + enforcement; handle overrides  
4. Publish shift templates; oversee MSS  
5. Run payroll → approve → finalize → release payslips → generate payment file  
6. Process final settlement from exit/lifecycle inputs  

### 8.2 Manager

1. Approve attendance corrections / OT within scope  
2. Approve leave steps (or delegate)  
3. Roster, open shifts, decide swaps (not self)  

### 8.3 Employee

1. Punch / view day / dispute  
2. Request leave against balance  
3. View/ack/claim/swap shifts  
4. Download released payslip  

---

## 9. Integrations

| Integration | Wave 2 role | Gate |
|---|---|---|
| BioTime / device adapter | Punch ingest | Per-company entitlement; off globally by default |
| Bank / WPS file formats | Payment export | `payment_processing` + format pack; kill switch |
| Legal leave pack (KW) | Enforcement prerequisite | Signed/versioned before `enforced=true` |

Adapters call the same authority as Web/Mobile — no parallel state.

---

## 10. EN / AR + Kuwait

- All new/changed UI + notification templates bilingual; RTL  
- Device timezone Asia/Kuwait; branch rules  
- Leave types: annual / sick / unpaid (+ company pack)  
- Payslip fields bilingual; WPS constraints documented  
- PIFSS / EOS worksheets remain payroll-owned (extend existing Wave 5 scaffolding honestly)

---

## 11. Analytics / audit

### 11.1 Audit (required)

Every punch ingest batch, correction apply, leave decide, balance adjust, roster publish, payroll snapshot/finalize/release/export/settlement — append-only with actor, before/after, company_code.

### 11.2 Facts to emit (visualize in Wave 5)

| Fact | Keys |
|---|---|
| `attendance_day_closed` | employee_key, date, hours, late_min |
| `attendance_correction_applied` | exception_id, ts |
| `leave_approved` / `leave_rejected_insufficient` | request_id, days, type |
| `shift_assignment_published` | assignment_id, date |
| `payroll_finalized` | period_id, company_code |
| `payslip_released` | payslip_id, employee_key |
| `payment_file_generated` | file_id, format |
| `settlement_finalized` | settlement_id, employee_key |
| `ot_approved` | ot_request_id, hours |

No executive money KPI cards until authoritative finalize is true for that company.

---

## 12. Rollout flags (company-scoped)

| Flag / entitlement | Default prod | Purpose |
|---|---|---|
| `attendance.ingest_enabled` | off | Canary company only |
| `leave.enforced` | false | Legal pack gate |
| `shifts.mss_allowlist` | empty | Honest dead-end until filled |
| `payroll.authoritative_finalize` | false | Synthetic default |
| `payroll.payment_processing` | disabled | Kill switch |
| Umbrella `workforce_truth_wave2` | off | Kill switch for new mutate routes |
| `ASSISTANT_MUTATIONS` | remains 0 unless confirm charter | |

Never systemd-global enable for money, ingest, or enforcement.

---

## 13. Freeze amendments (expected — each needs its own note)

| Existing posture | Likely amendment |
|---|---|
| Attendance ingest off | Company-entitled ingest on |
| Leave observe-only / `enforced=false` | Company-entitled enforcement after legal pack |
| Shifts empty manager allowlist | Entitled non-empty allowlist + scope |
| Payroll synthetic / preview / external-only money | Entitled authoritative finalize Mode A/B |
| `payment_processing=disabled` | Company-gated enable + kill switch |
| Assistant mutations=0 | Optional confirm-mutate for leave/OT only under separate approval |

Each amendment: one-page freeze note + qualify + rollback before production entitle.

---

## 14. Production-safe migration strategy

1. Additive schema / policy tables only; modules remain safe defaults  
2. Deploy behind umbrella + company allowlists  
3. Qualify on synthetic / WATHEFNIQA-style tenants first  
4. Enable **one** canary company per workstream (attendance ≠ payroll can differ)  
5. Legal pack sign-off before leave enforcement  
6. Payment file dry-run → ack → live with kill switch  
7. Expand entitlement only after owner gates  

Rollback: disable umbrella + company settings; retain schema/data; halt payment generates; reopen periods only via audited adjustment policy.

---

## 15. Serial delivery plan (after charter approval)

| Phase | Focus | Exit |
|---|---|---|
| C0 | Charter review + freeze amendment list agreed | **APPROVED** — `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED` |
| C1 | Attendance ingest + projection + correction apply | `ATTENDANCE_TRUTH_FULL_PASS` |
| C2 | Leave enforcement + N-step/delegation | `LEAVE_ENFORCEMENT_FULL_PASS` |
| C3 | Shifts MSS allowlist unlock | `SHIFTS_MSS_FULL_PASS` |
| C4 | Payroll authoritative finalize + input contracts | `PAYROLL_AUTHORITY_FULL_PASS` |
| C5 | Payslips release + payment files | `PAYSLIP_PAYMENT_FULL_PASS` |
| C6 | Final settlement pay path + OT contract | `SETTLEMENT_OT_FULL_PASS` |
| C7 | Product acceptance / modularity matrix / Setup | `WAVE2_PRODUCT_FULL_PASS` |

Parallelism: C2 and C3 may overlap after C1 contracts are stable; C4 depends on honest input contracts (manual OK); C5–C6 after C4.

---

## 16. Acceptance tests (charter-level)

| ID | Test |
|---|---|
| W2-A01 | Entitled company: punches ingest → day projection; global ingest remains off |
| W2-A02 | Correction approve→apply mutates projection; rejected does not |
| W2-L01 | `enforced=true`: insufficient balance rejects request; unpaid/override audited |
| W2-L02 | N-step leave + delegation; SoD where configured |
| W2-S01 | Entitled manager completes roster path; empty allowlist fails closed |
| W2-S02 | Manager cannot self-decide swap as final authority |
| W2-P01 | Finalize seals period; synthetic tenant cannot claim authoritative |
| W2-P02 | Attendance/leave/OT feeds optional; payroll runs without them on manual inputs |
| W2-P03 | Payslip visible to employee only after release |
| W2-P04 | Payment file generate blocked when `payment_processing` disabled; kill switch works |
| W2-P05 | Settlement produces payslip/payment inputs; E360 has no money math |
| W2-M01 | Modularity: each of attendance/leave/shifts/payroll alone; pairwise contracts as matrix |
| W2-X01 | EN/AR + tenant isolation + manager scope + audit on all transitions |
| W2-X02 | Channels/Assistant do not invent workflow state |

---

## 17. Wave 2 acceptance gate (roadmap §4.2)

- [ ] Entitled company: punches ingested → projections → exceptions → corrections applied  
- [ ] Leave balances enforce; multi-step approve + delegation  
- [ ] Manager can roster within scope without empty allowlist dead-end  
- [ ] Payroll finalize authoritative for entitled company; payslips released to app  
- [ ] Payment file generation gated, audited, kill-switchable  
- [ ] Final settlement path from lifecycle inputs → payroll  
- [ ] Analytics hooks emit canonical facts (hours, leave days, pay components) for Wave 5  
- [ ] Modularity matrix proven (independent modules + explicit contracts)  
- [ ] Setup Console owns Wave 2 company policies (not env-only)  

---

## 18. Owner review checklist (LOCKED 2026-08-11)

| # | Decision | Status |
|---|---|---|
| 1 | Serial phases C1–C7 and pass stamp names | **Locked** — see §15 |
| 2 | Existing Attendance/Leave/Shifts/Payroll freezes amended **individually per C1–C6** with qualify + rollback each time | **Locked** |
| 3 | Canary only — **WATHEFNI** or a dedicated workforce-truth tenant; **no broad enable** | **Locked** |
| 4 | Leave enforcement requires an **explicit company legal/policy pack** before `enforced=true` | **Locked** |
| 5 | Payment processing remains **company-gated + kill-switchable**; Wave 2 may **generate/ack** payment files but must **not** silently expand into direct money movement | **Locked** |
| 6 | **Assistant mutations are OUT of Wave 2 MVP** — Assistant stays read/explain/deep-link only; mutation unlock gets its own later charter | **Locked** |
| 7 | **Payroll independence is non-negotiable** — authoritative payroll must run from manual/imported/external inputs even when Wathefni Attendance/Leave/Shifts are disabled | **Locked** |

```text
WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED
date: 2026-08-11
signer: owner
```

Implementation may proceed slice-by-slice (C1 first). Stop after each `*_FULL_PASS` for review before the next slice.
---

## 19. Related documents

| Doc | Role |
|---|---|
| `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` | Parent execution authority |
| `ops/WATHEFNI_HCM_PHASE_A_WAVE1_BUILD_CHARTER.md` | Prior charter (frozen Wave 1 + Phase A) |
| `ops/WAVE1_PRODUCT_FREEZE.md` | Wave 1 freeze boundary |
| Existing `ops/PAYROLL_*_FREEZE.md`, attendance/leave/shifts qualify docs | Starting freezes to amend deliberately |
