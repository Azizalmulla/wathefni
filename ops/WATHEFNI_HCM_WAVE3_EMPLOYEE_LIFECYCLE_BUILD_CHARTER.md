# Wave 3 — Employee Lifecycle Build Charter

**Status:** APPROVED — `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED` (owner 2026-08-11)  
**Execution authority parent:** `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` §5  
**Prior gate:** `WAVE2_PRODUCT_FULL_PASS` **ACCEPTED** 2026-08-11 — Wave 2 remains frozen (`ops/WAVE2_PRODUCT_FREEZE.md`)  
**Wave 1 freeze:** `WAVE1_PRODUCT_FULL_PASS` ACCEPTED — Hire→Ready remains frozen  
**Audit SoT:** 111-capability HCM gap audit + roadmap §5  
**Charter date:** 2026-08-11 · **Approved:** 2026-08-11  
**Scope:** Wave 3 — Employee Lifecycle (employment changes → ESS records/letters → Offboarding product → exit close + settlement handoff)  
**Implementation gate:** **Wave 3 ACCEPTED / FROZEN** (`WAVE3_PRODUCT_FULL_PASS`) — do not reopen for safe debt; real termination remains locked (`WATHEFNI_REAL_TERMINATION_CANARY=off`) until owner explicitly names a real canary company/case. Wave 4 is charter-only until approved.

---

## 0. Charter principles (non-negotiable)

### 0.1 Modularity (same as Wave 1 / Wave 2)

| Rule | Requirement |
|---|---|
| Independent enablement | Every Wave 3 module works alone when enabled |
| Composability | Peers integrate only through **explicit capability contracts** — never silent hard wiring |
| Hard deps only when true | Catalog `depends_on` only for HARD DEPENDENCY |
| Clean disappearance | Disabled modules vanish from HR Web, HR Mobile, Employee App, Assistant — no empty shells |
| Premium small suites | e.g. Letters-only, Employment-change-only, or Offboarding without Payroll still feel intentional |
| Full-suite richness | Entitled multi-module tenants get governed change → Offboarding (notice→clearance→close) → settlement handoff |
| Canonical truth | Shared `employees` / employment / org history / `hr_tasks` / approvals — **no duplicate employment or offboarding SoT** |

### 0.2 Dependency classes

| Class | Definition |
|---|---|
| **HARD DEPENDENCY** | Cannot enable or operate Module B without A |
| **OPTIONAL INTEGRATION** | B works alone; when A enabled, a versioned contract connects them (company-configurable) |
| **ENHANCEMENT WHEN ENABLED** | B works alone; A present improves UX/automation/analytics only |

### 0.3 Dynamic navigation

Runtime nav = `enabled company modules ∩ permission grants ∩ surface capability matrix`.  
Zero visible children → omit the group entirely.

### 0.4 Prior freeze boundaries (do not reopen)

| Freeze | Rule for Wave 3 |
|---|---|
| Wave 1 Hire→Ready | Do **not** reopen for Wave 1 safe debt |
| Wave 2 Workforce Truth (C1–C7) | Do **not** reopen for Wave 2 safe debt (Setup OTA, channel fan-out, analytics completeness, broad rollout, clearance coupling) |
| Wave 2 C6 Settlement | **Settlement finalized ≠ paid** and **≠ clearance complete** — forever; Wave 3 couples exit-close via ack/waiver, never by equating finalize to clearance/paid |
| E360 lifecycle (3C–3H) | **EXTEND** request/decide/scheduler/policy packs — do not rewrite parallel lifecycle engines |
| Impact preview | Remains informational counts — **not** a clearance product |

### 0.5 Out of scope for this charter

- Wave 4 Performance / Talent — see `ops/WATHEFNI_HCM_WAVE4_PERFORMANCE_TALENT_BUILD_CHARTER.md` (PENDING; no implementation from Wave 3)
- Wave 5 executive KPI suite (emit facts only in Wave 3)
- Wave 6 Benefits / ER / L&D / insurance dependents products
- Inventing Kuwait EOS / notice-pay / garden-leave **money formulas** in lifecycle or clearance (Payroll owns money; Wave 2 settlement authority stays frozen)
- Treating settlement `finalized` as paid or as clearance complete
- Rebuilding Wave 2 payslip/payment/OT/settlement SMs
- Parallel approval engines or a second task inbox
- Using onboarding `asset_handover` as exit clearance (map explicitly; do not merge SoTs)
- Soft-enabling unsupported jurisdiction packs
- Global unlock of real (non-synthetic) termination for all tenants without canary gates
- **Assistant mutations** in Wave 3 MVP — Assistant stays read / explain / deep-link / remind only; lifecycle mutations need a separate later confirmation/security charter

### 0.6 Owner decisions (LOCKED 2026-08-11)

| # | Decision | Locked |
|---|---|---|
| 1 | **Assistant mutations = OUT** of Wave 3 MVP (read / explain / deep-link / remind only) | **Locked** |
| 2 | **Real non-synthetic termination remains dark** until the final canary qualification after the complete **synthetic** journey is green: initiate → approvals/SoD → notice → offboarding → required clearance → asset/IT/access actions → settlement handoff → close. Only then may one explicitly named canary company/case unlock real termination. No broad enable. Rollback must leave canonical history intact. | **Locked** |
| 3 | Commercial/module key = **`offboarding`**. **`clearance` is a sub-workflow/capability inside Offboarding**, not the module itself. | **Locked** |
| 4 | **Offboarding** encompasses resignation/termination/EOC handoff, notice, handover, clearance, assets, access revoke, exit interview, settlement handoff, close, and rehire/alumni history. | **Locked** |
| 5 | Modularity: Offboarding works without Payroll; Settlement OPTIONAL; IT/identity revoke OPTIONAL; Employee resignation may work without the full Offboarding module where the lifecycle contract permits, with an honest handoff. | **Locked** |

---

## 1. Exact scope

**Goal:** Employee changes and exits are **governed end-to-end products** — not loose fields or impact-preview checklists.

### 1.1 Serial core (customer-facing chain)

```text
Employment change cases (promotion / transfer / salary / secondment)
  → ESS records + letter fulfillment + dependents
  → Resignation / termination / end-of-contract (governed + SoD)
  → Offboarding / clearance (required items block exit close)
  → Exit interview + settlement handoff to Wave 2 Payroll authority
  → Exit close (only when clearance complete or waived + settlement ack/waiver per policy)
  → Rehire eligibility / alumni history
```

### 1.2 Workstreams

| ID | Workstream | Deliverable |
|---|---|---|
| W3.1 | Employment change cases | Governed `employment_change_case` for promotion, dept/manager/position transfer, salary change linked to Payroll compensation contracts, secondment/temporary assignment |
| W3.2 | ESS employee records | Employee-initiated personal/bank/emergency paths reused; dependents CRUD; no duplicate profile SoT |
| W3.3 | Employment letters / certificates | ESS letter orders → **actual fulfillment** (PDF generate + archive on employee docs); Art. 54 service-certificate track remains E360-compatible |
| W3.4 | Resignation (ESS) | Employee resigns from Employee App → dual-control lifecycle case + notice-period orchestration; may run **without** full Offboarding module when lifecycle contract permits (honest handoff) |
| W3.5 | Termination / EOC (synthetic first) | Manager/HR initiation; end-of-contract; governed approvals/SoD; **synthetic journey first**; real path dark until final canary unlock |
| W3.6 | Offboarding module | NEW commercial module `offboarding`: resignation/termination/EOC handoff, notice, handover, **clearance sub-workflow**, assets, access revoke, exit interview, settlement handoff, close, rehire/alumni |
| W3.7 | Clearance sub-workflow | Inside Offboarding — required vs optional items, dependencies, waive/escalate; blocks exit close |
| W3.8 | Exit close + settlement handoff | Exit cannot close until required clearance complete **or** waived; settlement handoff OPTIONAL INTEGRATION (ack/waiver) — never “finalized = closed/paid” |
| W3.9 | Surfaces + Setup | HR Web / HR Mobile / Employee App / Assistant (**read/explain/deep-link/remind only**); Setup Console Wave 3 policies |
| W3.10 | Cross-cutting | EN/AR+RTL, RBAC/confidentiality, Phase A approvals+delegation+`hr_tasks`+SLA, analytics/audit facts, company-scoped flags, qualify/rollback |
| W3.11 | Final canary real-termination unlock | Only after complete synthetic Offboarding chain green; one named company/case; no broad enable; rollback preserves history |

### 1.3 Explicit non-goals

- Forcing Offboarding to require Wathefni Payroll
- Forcing Payroll settlement to require Offboarding (settlement remains company-scoped Wave 2 path)
- Forcing Employee App resignation to require Letters / Dependents / full Offboarding module (honest lifecycle handoff when Offboarding off)
- Inventing legal formulas for notice pay / EOSB / PIFSS in lifecycle
- Marketing “complete HCM” after Wave 3 alone
- Broad production enable beyond named canary companies without owner gates
- Silent merge of clearance and settlement into one money-authority module

---

## 2. Starting posture (honest inventory)

Wave 3 is primarily **EXTEND + NEW clearance product**, not greenfield lifecycle:

| Area | Today (summary) | Wave 3 change |
|---|---|---|
| E360 lifecycle (3C–3H) | Request/decide SMs; KW case classes; notice hints; dual-control; synthetic-default; impact preview; downstream actions; settlement **inputs** packet; service-certificate **track** | EXTEND; resign-from-ESS; controlled real-path unlock; exit-close gates |
| Org Wave 4 | Assignment change types (transfer/manager/job) | Wrap into governed `employment_change_case` (+ promotion/salary/secondment) |
| ESS Wave 5 | Request types + letter **orders** (pending overlay) | Letter **fulfillment** + dependents entity |
| Wave 2 C6 settlement | Pay path sealed; finalized ≠ paid/clearance | OPTIONAL INTEGRATION: exit ack/waiver only |
| Phase A | Approvals + delegation + `hr_tasks` + SLA | Bind lifecycle/clearance/letter subjects — do not fork engines |
| Onboarding assets | `asset_handover` in onboarding | Explicit mapping ≠ exit clearance SoT |

Existing freezes remain until Wave 3 workstreams explicitly amend them with dated notes + re-qualify.

---

## 3. Dependency / capability contract matrix

### 3.1 HARD DEPENDENCY

| Consumer | Requires | Why |
|---|---|---|
| Employment change **execute** | Canonical employment + org history writers | Must mutate one SoT |
| Resignation → `notice_period` | Lifecycle employment SM | Same employment truth |
| Clearance item assign | Offboarding case | Items belong to a case |
| Exit close (strict mode) | Offboarding case in closable state | Product definition of governed exit |

### 3.2 OPTIONAL INTEGRATION (versioned contracts)

| Contract | Modules | Company setting (illustrative) | Behavior when enabled |
|---|---|---|---|
| `lifecycle.settlement_from_exit` | offboarding/lifecycle ↔ payroll settlement (Wave 2 C6) | `exit.require_settlement_ack` | Exit close requires settlement **ack** or audited **waiver**; never treats finalize as paid/clearance |
| `employment_change.salary_to_payroll_contract` | employment_change ↔ payroll contracts | `employment_change.link_comp_contracts=true` | Salary case creates/links compensation contract version in same TX or linked IDs |
| `clearance.identity_revoke` | clearance ↔ auth/IdP adapter | `clearance.idp_revoke=true` | Required IT item opens identity ticket; app session revoke remains baseline |
| `ess.letter_fulfillment` | ESS ↔ documents archive | `ess.letters.fulfill=true` | Approved letter order generates PDF + archives |
| `lifecycle.workflow_approvals` | lifecycle/clearance ↔ Phase A | `lifecycle.approval_policy_id` | N-step + delegation; else single-step domain decide |
| `clearance.hr_tasks` | clearance ↔ workflow tasks | always-on when clearance entitled | Task types for required items + SLA |

### 3.3 ENHANCEMENT WHEN ENABLED

| Base | Enhancement | Effect |
|---|---|---|
| Resignation | Leave / Shifts / Attendance modules | Richer impact preview counts (still not clearance) |
| Clearance | Assets / IT inventory integrations | Auto-seed checklist items |
| Exit interview | Analytics | Wave 5 themes/sentiment facts |
| Letters | Documents module | Stronger archive/retention UX |
| Employment change | Payroll | Live comp preview (Payroll remains money authority) |

### 3.4 Modularity proofs required

1. **Offboarding without Payroll** — clearance + exit close via clearance-only policy (settlement contract off)  
2. **Payroll settlement without Offboarding** — Wave 2 path still works from lifecycle inputs packet  
3. **Employee App resignation** with Letters/Dependents/Clearance disabled — resign path alone  
4. **Letters-only** tenant — fulfill ESS letter orders without exit modules  
5. Disabled modules disappear cleanly from all surfaces  

---

## 4. Entities and state machines

### 4.1 Reuse (do not duplicate)

#### Employment lifecycle (E360 — EXTEND)

```text
pending_start → active → notice_period | suspended → terminated
```

#### Lifecycle request (E360 — EXTEND)

```text
pending → approved | rejected | cancelled | executed | expired
```

#### Settlement packet (E360 inputs-only — unchanged money boundary)

```text
draft → handed_to_payroll → closed | cancelled
```

#### Wave 2 settlement run (FROZEN — consume only)

```text
inputs_ready → calculated → approved → finalized (| superseded)
```

Honesty locked: `finalized ≠ paid`, `finalized ≠ clearance`.

#### Phase A

- `approval_instance` + `delegation_grant`
- `hr_tasks` + SLA (`workflow_task_sla`)

### 4.2 NEW / EXTEND in Wave 3

#### `employment_change_case`

```text
draft → pending_approval → approved | rejected | cancelled → applied → (compensated_link_optional)
```

Types: `promotion` | `transfer` | `manager_change` | `position_change` | `salary_change` | `secondment` | `secondment_return`

- Applied mutates canonical assignment / org history (append-only)  
- `salary_change` optionally links Payroll compensation contract version (`employment_change.salary_to_payroll_contract`)  
- Secondment requires planned end / return path  

#### `ess_letter_order` (fulfillment)

```text
pending → in_fulfillment → issued | cancelled | failed
```

- Issued = PDF generated + archived on employee documents  
- Types: employment letter, service certificate (align Art. 54 track; do not invent second certificate SoT)  

#### `dependent`

- CRUD entity with audit; emergency contacts remain profile path unless migrated intentionally  
- Insurance products stay Wave 6  

#### `offboarding_case` (NEW commercial module key: `offboarding` / `clearance`)

```text
open → in_progress → blocked | ready_to_close → closed | cancelled
```

#### `clearance_item`

```text
pending → in_progress → completed | waived | escalated | cancelled
```

Item classes (illustrative): `handover` | `asset_return` | `it_access` | `dept_clearance` | `manager_clearance` | `hr_clearance` | `custom`

- **required** vs **optional** per company Setup template  
- **dependencies** between items (e.g. asset before IT close)  
- **waive** requires permission + reason + audit  
- **escalate** creates `hr_tasks` + optional N-step  

#### Exit close gate

```text
exit_close_eligible = required_clearance_satisfied
  AND (settlement_contract_off OR settlement_acked OR settlement_waived)
```

- `required_clearance_satisfied` = all required items `completed|waived`  
- Settlement ack references Wave 2 settlement id / packet id — **does not** claim paid  

#### `exit_interview`

```text
not_started → in_progress → submitted | skipped_waived
```

#### Rehire / alumni

- Flags + links on canonical employment/person — not a parallel alumni database  

---

## 5. Module catalog / Setup Console

### 5.1 Commercial modules

| module_key | Wave 3 Setup ownership |
|---|---|
| `employees` / E360 lifecycle | Case classes, notice-hint policy, dual-control, counsel gates (existing packs) |
| `employment_changes` (or lifecycle sub-policy) | Allowed change types; salary↔payroll link; secondment rules |
| `employee_app` / ESS | Resignation enablement; letter types; dependents |
| `documents` | Letter archive / retention floor |
| `offboarding` | Full exit product: notice/handoff templates; **clearance** sub-workflow (required/optional/waive/escalate); assets; access revoke; exit interview; settlement-ack contract; close; rehire/alumni |
| `payroll` | **Read-only consumption** of Wave 2 settlement settings — do not reopen Wave 2 money rails |

### 5.2 Company settings (illustrative — finalize in design review)

| Setting | Default | Notes |
|---|---|---|
| `employment_change.enabled_types` | promotion,transfer,manager_change | Salary/secondment opt-in |
| `employment_change.link_comp_contracts` | false | OPTIONAL INTEGRATION |
| `ess.resignation_enabled` | false | Canary only |
| `ess.letters.fulfill` | false until entitled | Orders stay pending if off |
| `ess.dependents_enabled` | false | |
| `offboarding.enabled` | false | |
| `offboarding.template_id` | null | Required/optional item set |
| `offboarding.allow_waive` | true (HR only) | Audited |
| `exit.require_settlement_ack` | false | OPTIONAL INTEGRATION to Wave 2 |
| `exit.require_exit_interview` | false | May be required/optional/waivable |
| `lifecycle.approval_policy_id` | null | Falls back to dual-control domain decide |
| `clearance.idp_revoke` | false | OPTIONAL identity integration |

Setup Console owns these policies (not env-only). Runtime flags remain fail-closed canary gates.

---

## 6. RBAC / confidentiality

| Permission (illustrative) | Surface |
|---|---|
| `employment_change.request` / `approve` / `apply` | HR / Manager (scoped) |
| `ess.resign` | Employee (self) |
| `lifecycle.terminate` / `decide` | HR (+ dual-control) |
| `offboarding.manage` / `clearance.complete` / `clearance.waive` | HR / Manager / Dept owners |
| `letters.fulfill` | HR |
| `dependents.verify` | HR |
| `exit_interview.conduct` | HR |
| `rehire.mark_eligible` | HR |
| Confidentiality | Disciplinary / counsel / compensation salary cases — need-to-know; manager scope ∩ allowlist; no self-approval as final authority |

SoD: requester ≠ final approver for resignation/termination/salary change when policy requires distinct approver (Phase A SoD patterns).

---

## 7. Workflows by persona

### 7.1 HR Web

- Employment change queue (approve/apply)  
- Lifecycle / termination / EOC console (extend E360; do not fork)  
- Clearance board (case + items + waive/escalate)  
- Letter fulfillment queue  
- Exit interview + settlement handoff status (ack/waiver)  
- Rehire eligibility  

### 7.2 Manager (HR Mobile + Web)

- Nominate/request transfer/promotion (scoped)  
- Ack resignation; complete manager clearance / handover items  
- Cannot self-approve own change or own resignation decision as final authority  

### 7.3 Employee App

- Resign (when entitled)  
- Track clearance items assigned to employee  
- Request letters; maintain dependents/emergency contacts  
- Submit exit interview (when required)  
- View employment letters once issued  

### 7.4 Assistant

- Wave 3 MVP **LOCKED**: **read / explain / deep-link / remind only** — mutations OUT  
- Lifecycle mutations require a separate later confirmation/security charter  
- Must not invent workflow state (W3-X05)  

---

## 8. Surfaces matrix

| Capability | HR Web | HR Mobile | Employee App | Assistant |
|---|---|---|---|---|
| Employment changes | Strong | Thin/Strong queue | Thin ack | Read |
| Letters fulfill | Strong | Thin | Request/download | Notify/Remind |
| Dependents | Strong | — | Strong | — |
| Resignation | Strong | Thin | Strong | Read/Remind |
| Termination/EOC | Strong | Thin | — | Read |
| Offboarding (clearance sub-workflow) | Strong | Strong | Strong (own items) | Remind |
| Exit interview | Strong | — | Thin | Remind |
| Settlement handoff status | Strong | Thin | Thin | Read |
| Rehire/alumni | Strong | — | — | Read |

Assistant mutations are OUT of Wave 3 MVP.

---

## 9. Kuwait-specific boundaries (honesty)

Document / orchestrate; **do not invent law in software**:

| Topic | Boundary |
|---|---|
| Notice hints (Art. 44) | Hints only when pack allows; never auto-set legal dates as authority; default show-hints false |
| Case classification | Fail-closed on contract_type / pay_frequency / probation / case_class — never inferred |
| Exceptional/summary paths | Manual escalation; software does not decide lawfulness |
| Art. 54 service certificate | Track + fulfill; align E360 certificate row with letter fulfillment — one truth |
| Retention (Art. 80 / 144) | Retention floor; no auto-purge of personnel files |
| EOSB / notice pay / encashment money | **Payroll-only** via Wave 2 settlement / worksheets; lifecycle passes **inputs** |
| Settlement vs clearance vs paid | Three distinct truths — never collapsed |
| Jurisdiction packs | Unsupported packs fail closed; `KW_PRIVATE_SECTOR` is the verified baseline |

---

## 10. Approvals, tasks, SLA (reuse Phase A)

| Subject | Task / approval |
|---|---|
| `employment_change_approval` | N-step optional; SoD |
| `lifecycle_resignation_decide` | Dual-control + optional N-step |
| `lifecycle_termination_decide` | Dual-control + counsel checklist when pack requires |
| `clearance_item_pending` | Assignee task + SLA |
| `clearance_waive_approval` | Higher privilege |
| `letter_fulfillment` | HR queue task |
| `settlement_ack_required` | HR task when exit contract on |
| `exit_interview_pending` | HR/employee task |

One inbox SoT: `hr_tasks`. Do not create a parallel clearance inbox.

---

## 11. Analytics / audit facts (Wave 5 prep)

Emit append-only facts (no executive suite UI in Wave 3):

| Fact | Payload (min) |
|---|---|
| `employment_change_applied` | case_id, type, employee_key |
| `letter_issued` | order_id, letter_type |
| `dependent_changed` | dependent_id, action |
| `resignation_submitted` | case_id |
| `termination_executed` | case_id, case_class |
| `clearance_item_completed` | item_id, class |
| `clearance_item_waived` | item_id, actor |
| `offboarding_closed` | case_id |
| `exit_interview_submitted` | interview_id |
| `settlement_handoff_acked` | settlement_id / packet_id |
| `settlement_handoff_waived` | reason |
| `rehire_eligibility_set` | person_id, eligible |

Every transition: actor, before/after, company_code, reason where required.

---

## 12. Migrations

| From | To | Rule |
|---|---|---|
| Org Wave 4 assignment changes | `employment_change_case` wrapper | Backfill links; do not rewrite history rows |
| ESS letter orders `pending` | Fulfillment SM | Existing orders remain pending until fulfill enabled; no silent PDF invent |
| E360 service_certificate track | Align with issued letter | Same certificate truth; no second ledger |
| Impact preview | Unchanged | Never migrated into clearance items automatically without template mapping |
| Onboarding asset_handover | Optional seed map | Explicit template mapping only |
| Wave 2 settlement rows | Handoff references | Reference IDs only; no status rewrite of finalized settlements |

---

## 13. Rollout flags (fail-closed)

Pattern: `WATHEFNI_<FEATURE>[_C#]` + `_COMPANIES` (empty = nobody) + optional `_KILL`.

| Flag (proposed) | Default | Notes |
|---|---|---|
| `WATHEFNI_EMPLOYMENT_CHANGE_C1` | off | Slice C1 |
| `WATHEFNI_ESS_LETTERS_DEPENDENTS_C2` | off | Slice C2 |
| `WATHEFNI_RESIGNATION_ESS_C3` | off | Slice C3 |
| `WATHEFNI_OFFBOARDING_C4` | off | Slice C4 — commercial module `offboarding` |
| `WATHEFNI_EXIT_CLOSE_C5` | off | Slice C5 (close + settlement handoff + rehire) |
| `WATHEFNI_LIFECYCLE_PRODUCT_C6` | off | Product acceptance + final synthetic chain prove |
| `WATHEFNI_REAL_TERMINATION_CANARY` | off | Post-C6 only; single named company/case |
| Per-slice `_COMPANIES` | empty | Nobody until canary listed |
| `WATHEFNI_OFFBOARDING_KILL` | off | Immediate block on new exit closes / item completes when on |

Production systemd must **not** globally enable these. Process-scoped prove only until owner unlock.

---

## 14. Freeze amendments (required before/with slices)

| Prior freeze | Wave 3 amendment intent |
|---|---|
| `ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` (+ cursor rule) | Employment-change cases; resign-from-ESS; controlled real-path; exit-close gates |
| `ops/SETTLEMENT_OT_C6_FREEZE_AMENDMENT.md` | Document exit ack/waiver contract **without** changing finalize≠paid/clearance |
| `ops/WAVE2_PRODUCT_FREEZE.md` | Wave 3 owns clearance/exit-close; Wave 2 stays frozen |
| ESS / bank ESS posture | Letter fulfillment + dependents; bank ESS remains its own hardened module |
| Onboarding freezes | Explicit “≠ exit clearance” mapping note |

Each slice ships: qualify script + evidence + `*_FULL_PASS` stamp + freeze amendment. Stop for owner review between slices.

---

## 15. Serial build order + safe parallelism

| Phase | Focus | Exit stamp |
|---|---|---|
| **C0** | Charter review + freeze-amendment list agreed | **APPROVED** — `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED` |
| **C1** | Employment change cases (promotion / transfer / salary link / secondment) | **ACCEPTED / FROZEN** `EMPLOYMENT_CHANGE_FULL_PASS` · evidence `ops/evidence/employment-change-c1-20260811T205148Z` |
| **C2** | ESS letter fulfillment + dependents | **ACCEPTED / FROZEN** `ESS_LETTERS_DEPENDENTS_FULL_PASS` · evidence `ops/evidence/ess-letters-dependents-c2-20260811T205906Z` |
| **C3** | Resignation ESS → lifecycle + notice reuse; manager/HR termination/EOC **synthetic** path | **ACCEPTED / FROZEN** `RESIGNATION_TERMINATION_FULL_PASS` · evidence `ops/evidence/exit-intent-c3-20260811T211012Z` |
| **C4** | Offboarding module (`offboarding`) — clearance sub-workflow, assets, access, tasks | **ACCEPTED / FROZEN** `OFFBOARDING_FULL_PASS` · evidence `ops/evidence/offboarding-c4-20260811T211617Z` |
| **C5** | Exit close + exit interview + settlement ack/waiver (OPTIONAL) + rehire/alumni | **ACCEPTED / FROZEN** `EXIT_CLOSE_HANDOFF_FULL_PASS` · evidence `ops/evidence/exit-close-c5-20260811T212753Z` |
| **C6** | Surfaces + Setup + modularity + **complete synthetic journey prove** → product acceptance | **ACCEPTED / FROZEN** `WAVE3_PRODUCT_FULL_PASS` · evidence `ops/evidence/wave3-product-acceptance-20260811T213549Z` |
| **C6+** | Explicit named canary real-termination unlock | Owner-gated; remains **locked** until owner names company/case; **not** auto-enabled by C6; no broad enable |

**Synthetic journey (must be green before any real termination unlock):**  
`initiate → approvals/SoD → notice → offboarding → required clearance → asset/IT/access actions → settlement handoff → close`

**Parallelism:** C2 may overlap late C1 after change-case contracts stable; C3 resign may proceed without full Offboarding (honest handoff); **C4 Offboarding is critical path before C5 close**; C5 after C4 accepted; C6 after C5; real-termination only after C6 synthetic chain green.

---

## 16. Acceptance tests (charter-level)

| ID | Test |
|---|---|
| W3-E01 | Promotion/transfer/salary-change cases mutate canonical employment + append-only history |
| W3-E02 | Salary change links Payroll contract when OPTIONAL contract on; payroll independence remains when off |
| W3-E03 | Secondment applies with return/end path |
| W3-L01 | ESS letter order fulfills to issued PDF + archive; pending orders do not silently invent PDFs when fulfill off |
| W3-L02 | Dependents CRUD + audit; disabled module disappears |
| W3-R01 | Employee resign in App creates dual-control lifecycle case + notice_period path |
| W3-R02 | Manager/HR termination/EOC SoD; self-approve forbidden |
| W3-C01 | Clearance required items block exit close |
| W3-C02 | Waive/escalate audited; optional items do not block |
| W3-C03 | Offboarding works with Payroll module/settlement contract **off** |
| W3-X01 | Exit close requires settlement ack/waiver only when contract on; finalize still ≠ paid/clearance |
| W3-X02 | Exit interview stored; skip/waive policy honored |
| W3-X03 | Rehire eligibility + prior employment visible |
| W3-M01 | Modularity matrix: alone + combinations; resign-only (no Offboarding); Offboarding without Payroll; letters-only; full suite; all disabled |
| W3-X04 | EN/AR+RTL + tenant isolation + manager scope + confidentiality |
| W3-X05 | Channels/Assistant do not invent workflow state |

---

## 17. Wave 3 acceptance gate (roadmap §5.2)

- [ ] Promotion/transfer/salary-change cases mutate canonical employment + history  
- [ ] Employee can resign in app; HR/manager path dual-controlled  
- [ ] Clearance checklist blocks exit close; assets/IT tracked; waive/escalate audited  
- [ ] Letters fulfill from ESS orders  
- [ ] Settlement handoff ack/waiver when contract on; money still Payroll-owned; finalized ≠ clearance/paid  
- [ ] Offboarding works without Wathefni Payroll  
- [ ] HR Mobile has lifecycle/clearance queues for entitled actions  
- [ ] Modularity matrix + Setup ownership proven  
- [ ] Wave 1 + Wave 2 freezes regress green  

---

## 18. Rollback

```text
WATHEFNI_OFFBOARDING_KILL=on          # immediate: block new exit closes / completions
WATHEFNI_*_C#=off                     # per-slice runtime off
Clear corresponding *_COMPANIES
disable company Setup entitlements (offboarding / resign / letters fulfill)
In-flight cases: remain auditable; no silent purge
Wave 2 sealed settlements: immutable; handoff refs retained
```

Per-slice rollback guidance required in each freeze amendment.

---

## 19. Owner review checklist (LOCKED 2026-08-11)

| # | Decision | Status |
|---|---|---|
| 1 | Serial phases C0–C6 (+ C6+ real canary) and pass stamp names | **Locked** — see §15 |
| 2 | Amend E360 + C6 settlement coupling freezes individually per slice | **Locked** |
| 3 | Canary only — no broad enable | **Locked** |
| 4 | Offboarding without Payroll is mandatory modularity proof | **Locked** |
| 5 | Settlement ack/waiver is OPTIONAL INTEGRATION; never equals paid/clearance | **Locked** |
| 6 | Assistant mutations for Wave 3 | **Locked OUT** — read / explain / deep-link / remind only |
| 7 | Real non-synthetic termination | **Locked dark** until complete synthetic journey green; then one named canary only |
| 8 | Commercial module key | **Locked = `offboarding`**; clearance is a sub-workflow inside it |

```text
WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED
date: 2026-08-11
signer: owner
```

Implementation may proceed slice-by-slice (**C1 first**). Stop after each `*_FULL_PASS` for review before the next slice.

---

## 20. Related documents

| Doc | Role |
|---|---|
| `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` | Parent execution authority (§5) |
| `ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md` | Prior charter (frozen Wave 2) |
| `ops/WAVE2_PRODUCT_FREEZE.md` / `WAVE2_PRODUCT_FULL_PASS.md` | Wave 2 freeze + safe debt |
| `ops/SETTLEMENT_OT_C6_FREEZE_AMENDMENT.md` | Settlement ≠ clearance/paid |
| `ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` | E360 lifecycle freeze to amend |
| `ops/WAVE1_PRODUCT_FREEZE.md` | Wave 1 boundary |
| `wathefni-orchestrator/employee_lifecycle_wave3c.py` | Lifecycle EXTEND base |
| `wathefni-orchestrator/payroll_settlement_ot_c6.py` | Settlement consume-only |
| `wathefni-orchestrator/employee_selfservice_wave5.py` | ESS / letter orders EXTEND |
| `wathefni-orchestrator/employee_org_wave4.py` | Org change EXTEND base |
