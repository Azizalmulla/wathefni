# Wathefni HCM Execution Roadmap

**Status:** Official execution authority (approved 2026-08-11; modularity amendment applied)  
**Source of truth:** HCM capability audit — 111 capabilities (Complete 10 / Partial 57 / Missing 44)  
**Companion canvas:** Cursor canvas `hcm-execution-roadmap.canvas.tsx`  
**Build charter (Phase A + Wave 1):** `ops/WATHEFNI_HCM_PHASE_A_WAVE1_BUILD_CHARTER.md` — Wave 1 product **ACCEPTED / FROZEN** (`WAVE1_PRODUCT_FULL_PASS`)  
**Build charter (Wave 2 — Workforce Truth):** `ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md` — **`WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`** (2026-08-11); implement C-slices only, stop for review between stamps  
**Date:** 2026-08-11  
**Product posture today:** Kuwait-first hire → people-ops → payroll scaffolding — **not** a complete HCM suite. Wave 1 Hire→Ready frozen on WATHEFNI canary only.

---

## 0. Non-negotiable product rules

1. **Depth over checkboxes.** Every capability ships with: canonical entity + state machine, permissions, HR/manager/employee workflows, analytics hooks, and cross-surface behavior (Web / HR Mobile / Employee App / Assistant / channels).
2. **Pages ≠ done.** Freeze flags, synthetic-only, empty allowlists, and `enforced=false` are the real product boundary.
3. **Canonical across channels.** WhatsApp / Teams / email / SMS / Assistant must call the same authority as Web/Mobile — never invent parallel state.
4. **Kuwait-first.** Civil ID, residency, work permit, bilingual EN/AR+RTL, WPS/bank realities, and Kuwait leave/EOS norms constrain design — not afterthoughts.
5. **Do not market “complete HCM”** until Wave 1–3 gates + Performance core (Wave 4 slice) + KPI spine (Wave 5 slice) pass. See §9.
6. **Fully modular / composable (amendment).** Every module must work independently when enabled; become more powerful when complementary modules are enabled; declare only true hard dependencies; otherwise use optional capability contracts. Disabled modules disappear cleanly from Web, HR Mobile, Employee App, and Assistant — **no empty shells** (no Grow/Care/Plan with zero children). A 2–3 module tenant must still feel intentional and premium. Shared employee/org/workflow records remain canonical — no module-specific duplicate truth.
7. **Navigation is dynamic IA.** Proposed nav groupings in this roadmap are conceptual only. Final nav composes from tenant entitlements + permissions + enabled capabilities.

### 0.1 Dependency classification vocabulary

| Class | Meaning |
|---|---|
| **HARD DEPENDENCY** | Module B cannot be enabled/meaningfully used without Module A. Catalog `depends_on` only for these. |
| **OPTIONAL INTEGRATION** | Module B works alone; when Module A is also enabled, a defined contract connects them (may be company-configurable on/off). |
| **ENHANCEMENT WHEN ENABLED** | Module B works alone; when Module A is enabled, UX/analytics/automation get richer without changing B’s core contract. |

---

## 1. Cross-cutting platform (every wave)

These are **not** a separate “later” workstream. Each wave’s acceptance gate includes the subset marked **Required**.

| Platform capability | Required from | Extend vs new | Notes |
|---|---|---|---|
| Configurable multi-step approvals | Wave 1 (reqs, preboard gates) | **NEW** `workflow_approvals` authority | Today: domain dual-control only (offers, leave decide, lifecycle). Building N-step logic inside each module = debt. |
| Delegation / substitution | Wave 1 (approvers) | **NEW** on approvals | Manager OOO must not block hire-to-ready or leave. |
| Tasks / Action Inbox | Wave 1 | **EXTEND** `hr_tasks` + inbox | Unify ontology: requisition, preboard, probation, clearance, ER… |
| Reminders / escalations / SLAs | Wave 1 | **EXTEND** notification + onboarding/compliance ladders → **NEW** SLA policy | Per-entity SLA defs, not hard-coded only in onboarding. |
| Audit history | Wave 1 | **EXTEND** existing audit patterns | Universal audit browser by Wave 3. |
| Company configuration / tenant modules | Wave 1 | **EXTEND** `module_catalog` + Setup Console | New modules must register here. |
| RBAC + manager scope | Wave 1 | **EXTEND** permissions + scope SQL | Confidential scopes for ER (Wave 6). |
| ESS / MSS | Wave 1 (employee preboard tasks) | **EXTEND** employee_app + ESS; unlock allowlists carefully | Broad ESS is a Wave 1–3 gate, not perpetual canary. |
| EN/AR + RTL | Wave 1 | **EXTEND** i18n contracts | Every new surface ships bilingual. |
| HR Web | Wave 1 | **EXTEND** dashboard PostHire / PreHire | Primary operator surface. |
| HR Mobile | Wave 1 (readiness, queues) | **EXTEND** employee-mobile `/hr` | Mutate parity for wave-critical actions — not web-only forever. |
| Employee App | Wave 1 | **EXTEND** `/app/*` | Preboard/onboard/probation employee tasks. |
| Assistant | Wave 1 (read) → Wave 2 (confirm-mutate) | **EXTEND** capability catalog | Prod `ASSISTANT_MUTATIONS=0` today — unlock only with confirm UX. |
| Channels (WA/Teams/email/SMS) | Wave 1 | **EXTEND** Alerts & Delivery | Same APIs; delivery only. |
| Integrations | Wave 2 (BioTime, bank/WPS) | **EXTEND** adapters | Identity provisioning later (Wave 3 clearance). |

### Technical debt if ignored

| Current architecture | Risk if we build on top blindly |
|---|---|
| Dual-control copied per domain | N incompatible approval engines; cannot share delegation/SLA |
| `WATHEFNI_ONBOARDING_SEED=off` + manual start | “Hire-to-ready” marketing while employees have no checklist |
| Offer `proposed_start_date` / `probation_days` not written to employment | Parallel truths; probation KPIs lie |
| Leave `enforced=false` + observe-only ledger | Balance UI that does not govern requests |
| Attendance capture ingest off | Exception boards without punches |
| Payroll synthetic / `payment_processing=disabled` | Payslip UI without money authority |
| Wave2 employee shadows non-authoritative | Lifecycle events dual-write confusion |
| Analytics Attention forbidding headcount | Fake “Analytics” product without workforce KPIs |
| “Talent pool” naming for candidates | Product language collision with Wave 4 Talent |
| Assessment “calibration” naming | Collision with performance calibration |
| Empty manager allowlists (shifts/leave) | MSS features that never reach managers |
| No Postgres RLS (app tenancy only) | Acceptable short-term; document; do not weaken checks |

---

## 2. Extend vs new module map

| Capability area | Decision | Module key (proposed) | Dependency class |
|---|---|---|---|
| Requisitions / headcount approval | **NEW** | `requisitions` | **HARD:** none (beyond core company/RBAC). **OPTIONAL:** `pre_hiring` (job publish gate). |
| Preboarding | **NEW** | `preboarding` | **HARD:** canonical employee/employment. **OPTIONAL:** `employment_offers`, `pre_hiring`, `onboarding`. |
| Onboarding auto-start + joining date sync | **EXTEND** | `onboarding` + hire + offers | **OPTIONAL INTEGRATION** between modules — never force Recruiting if only Onboarding enabled |
| 30/60/90 + probation confirmation | **NEW** | `probation` | **HARD:** employment record. **OPTIONAL:** `onboarding`, `employment_offers` (term sync) |
| Approval engine | **NEW** platform | `workflow_approvals` (platform capability, not a sold HCM module) | Consumed by modules via contract |
| Attendance capture | **EXTEND** | `attendance` | Schema exists; ingest off |
| Leave enforcement | **EXTEND** | `leave` | Ledger exists; writers/enforcement off |
| Shifts production MSS | **EXTEND** | `shifts` | Deep product; unlock allowlists + gates |
| Payroll money authority | **EXTEND** | `payroll` | Deep scaffolding; unlock Mode A/B honestly |
| Promotions / transfers / changes | **EXTEND** | Employees 360 / org + **NEW** case types | Org history exists; promotion event missing |
| ESS requests breadth | **EXTEND** | ESS / employee_app | Letter orders need fulfillment |
| Clearance / assets / access | **NEW** | `offboarding` (or `clearance`) | Lifecycle impact preview ≠ product |
| Performance | **NEW** | `performance` | Entire domain missing |
| Talent / succession | **NEW** | `talent` | Distinct from recruiting talent_pool |
| HR Intelligence KPIs | **EXTEND → reshape** | `analytics` | Replace vanity ban with canonical KPI registry |
| L&D / Benefits / ER / Engagement / Comp planning / Workforce planning | **NEW** (Wave 6) | `learning`, `benefits`, `employee_relations`, `engagement`, `comp_planning`, `workforce_planning` | Do not fake inside existing modules |

---

## 3. Wave 1 — Hire → Ready

**Goal:** An approved headcount becomes a day-1-ready employee with probation under management — without manual glue.

**Depends on (existing):** `pre_hiring`, `employment_offers`, `hire_operations`, `onboarding`, `compliance`, notifications, RBAC  
**Platform slice required:** multi-step approvals, tasks, reminders/SLA, ESS employee tasks, EN/AR, Web + Mobile + App

### 3.1 Capability matrix

| Capability | Dependency | Canonical entities / state machines | Backend authority | HR workflow | Manager workflow | Employee workflow | Surfaces (Web / HR Mob / App / Asst) | Kuwait requirements | Migration impact | Acceptance gate |
|---|---|---|---|---|---|---|---|---|---|---|
| Manpower requisition | Org units, positions, approvals engine | `requisition`: `draft→pending_approval→approved→open→filled\|cancelled`; links `position_id`, `approved_headcount`, `budget_ref` | NEW `requisitions` service; job publish **requires** approved req (or explicit override grant) | Create, route, approve, close/fill | Request headcount; approve if designated | — | Strong / Thin queue / None / Read+confirm | Budget/headcount language EN/AR; company policy pack | Backfill: existing open jobs get synthetic “legacy_unrequisitioned” flag, not silent rewrite | Cannot publish job without approved req (except grant-only override); audit trail; SoD |
| Headcount / budget approval | Requisition + approvals | Approval steps on requisition (N-step) | `workflow_approvals` | Configure chain; decide | Approve/reject/delegate | — | Strong / Thin / None / Confirm | Dual-control for owner companies | Migrate offer-style SoD patterns into shared engine | ≥2-step chain proven; replay/idempotent decisions |
| Preboarding program | Accepted offer (or hire pending_start) | `preboard_assignment`: `not_started→in_progress→ready\|blocked→converted`; items with owners | NEW `preboarding`; hire/onboarding cannot claim “ready” without gate when module on | Define template; monitor readiness | Complete manager items; see blockers | Upload docs, bank, forms pre-join | Strong / Strong / Strong / Read+remind | Civil ID/passport/residency/work permit prep items; bilingual welcome | Existing hires: optional backfill only if `pending_start` | Readiness dashboard; blocked≠ready; WhatsApp/email reminders fire |
| Joining-date sync | Offer + employment + preboard | Single `joining_date` authority written to employment + preboard + onboarding `planned_start_date` | EXTEND offer accept / hire TX | Set/change with audit | View | View | Strong / Thin / Thin / Read | Align with Civil ID/residency timing | One-time reconcile offer.proposed_start_date → employment | Offer accept updates employment; UI shows one date |
| Onboarding auto-start | Hire TX + seed policy | On hire (or preboard convert): create assignment from template | EXTEND `hire_operations` + `onboarding_seed_enabled` → **on for entitled companies** | Template admin; waive/accept | Own items | Complete items | Strong / Strong / Strong / Status | Kuwait template v2 remains default | SEED=on only with company entitlement; rollback flag | Hire creates onboarding assignment in TX; no orphan employees without plan when module on |
| Preboard → onboard handoff | Preboard ready + hire | Convert preboard items → onboard or close; no duplicate Civil ID tasks | NEW handoff rules in completion contract | Resolve conflicts | — | Continue tasks | Strong / Strong / Strong / — | Doc types PACI/MOI/PAM guidance unchanged | Deduplicate item keys across phases | Completion contract single authority remains |
| 30/60/90 plans | Onboarding complete or hire+N days | `probation_plan` + `milestone` (`pending→completed\|skipped\|overdue`) | NEW `probation` | Configure plan template | Complete check-ins | Ack / self-reflection (optional) | Strong / Thin / Thin / Remind | Align milestones to probation_end_date | Backfill milestones for employees with probation_end_date | Milestones create tasks; overdue escalates |
| Probation tracking | Employment probation_* fields | `probation_case`: `active→under_review→confirmed\|extended\|failed` | NEW; write offer.probation_days → employment on hire | Open review; decide | Recommend; check-in | View status; feedback form | Strong / Thin / Thin / Read | Kuwait probation norms via policy pack (not legal advice) | Backfill active probation from employment dates | Terminal decision required before probation_end; extension writes new end date |
| Probation confirmation / fail | Probation case | Decision + letter packet + lifecycle hook (fail→notice/terminate path) | NEW + EXTEND lifecycle | Confirm/extend/fail with SoD | Submit recommendation | Receive outcome | Strong / None / Thin / — | Counsel checklist if fail→terminate | Failed probation uses lifecycle dual-control | Confirmed clears probation_status; fail opens lifecycle case |
| Tasks / reminders / SLA (Wave 1 slice) | Platform | Task types: requisition, preboard_item, probation_milestone | EXTEND hr_tasks + SLA policy | Triage inbox | Manager inbox | Employee inbox | Strong / Strong / Strong / Notify | EN/AR templates | — | SLA breach creates escalation task |
| Background check gate (optional P1 in Wave 1.1) | Offer/hire | `bg_check`: `not_required→ordered→clear\|fail` | NEW thin or partner stub | Order/record | — | Consent | Strong / None / Thin / — | Consent language KW | — | Hire blocked when required & not clear |

### 3.2 Wave 1 acceptance gate (customer-ready hire-to-ready)

**Stamp:** `WAVE1_PRODUCT_FULL_PASS` **ACCEPTED** by owner 2026-08-11 — `ops/WAVE1_PRODUCT_FULL_PASS.md` · freeze `ops/WAVE1_PRODUCT_FREEZE.md`  
**Canary:** WATHEFNI company-scoped only — **do not broadly enable Wave 1 beyond WATHEFNI yet.** Visual canary fixtures kept until owner visual review, then cleanup only.  
**Next:** Owner sign-off of Wave 6 `WAVE6_PRODUCT_FULL_PASS` — freeze Wave 6; do not begin additional HCM domains automatically. C1–C7 ACCEPTED/frozen. Charter **`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`**. Wave 5 ACCEPTED/frozen. Global Wave 5 + Wave 6 capabilities remain off / company-gated; FULL_PASS ≠ broad rollout. Wave 4–1 freezes remain in force. Real termination remains locked. Wave 1 stays WATHEFNI-canary only.

- [x] Job publish requires approved requisition (or audited override)
- [x] Accepted offer creates/updates joining date + probation terms on employment
- [x] Preboarding readiness visible; blocked items prevent “ready”
- [x] Hire auto-starts onboarding for entitled company (SEED path proven)
- [x] 30/60/90 milestones + probation confirm/extend/fail work end-to-end
- [x] HR Web + HR Mobile + Employee App + canonical `hr_tasks` for Wave 1 events *(live channel reminder fan-out remains safe debt / Phase A audit_only)*
- [x] EN/AR + permissions + tenant isolation + audit
- [x] No dual joining dates; no orphan hires without onboarding when module on

**First customer-ready milestone = Wave 1 gate + existing recruiting/onboarding depth (already strong) under entitled company.**

---

## 4. Wave 2 — Workforce Truth

**Goal:** Time and pay numbers are authoritative enough to run a real payroll cycle — not synthetic demos.

**Depends on:** Wave 1 employment truth; existing `attendance`, `shifts`, `leave`, `payroll` scaffolding  
**Platform slice:** approvals for OT/leave chains; Assistant confirm-mutate optional; BioTime/bank integrations  
**Build charter:** `ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md` (**APPROVED** 2026-08-11) — **`WAVE2_PRODUCT_FULL_PASS` ACCEPTED; Wave 2 frozen**

### 4.1 Capability matrix

| Capability | Dependency | Entities / SM | Backend authority | HR | Manager | Employee | Surfaces | Kuwait | Migration | Acceptance gate |
|---|---|---|---|---|---|---|---|---|---|---|
| Real attendance capture | Devices/adapter | `attendance_punches` append-only; day projections | EXTEND; turn ingest **on** per company entitlement | Monitor exceptions | Approve corrections | Punch / dispute | Strong / Thin / Punch path / Read | Device timezone Asia/Kuwait; branch rules | Historical synthetic stays labeled | Punches → day projection; ingest off remains default globally |
| Lateness / absence / corrections | Punches + schedule | Exception cases already exist | EXTEND; approve→**apply** | Resolve | Approve | Dispute | Strong / Strong / Thin / Confirm | — | — | Correction apply mutates projection; mobile can finish path |
| Production shifts / MSS | Allowlists + publish | Existing shift_assignments SM | EXTEND; open manager allowlist with scope | Publish templates | Roster, open shifts, swaps | View/ack/claim/swap | Strong / Strong / Strong / Tools | Ramadan/seasonal policies | — | Non-empty manager path for entitled managers; self-decision still banned |
| Leave balance enforcement | Ledger + legal_reviewed policy | Balances binding on request | EXTEND; `enforced=true` per company after legal pack | Adjust with audit | Approve with balance view | Request against balance | Strong / Strong / Strong / Confirm | Annual/sick/unpaid KW pack signed | Observe-only companies stay flagged | Request rejected when insufficient (unless unpaid/override) |
| Multi-step leave approval | Approvals engine | Chain on leave_request | EXTEND leave + workflow_approvals | Configure | Step approve / delegate | Request | Strong / Strong / Strong / Confirm | — | — | N-step proven; delegation works |
| Carry-over / encashment hooks | Leave + payroll | Carry writers; encashment as payroll input | EXTEND leave writers; payroll packet | Run year-end | — | View | Strong / None / Thin / — | Encashment ownership stays Payroll | — | Carry executes; encashment is payroll input not E360 calc |
| Authoritative payroll run | Contracts + inputs | Period → snapshot → calculate → approve → finalize | EXTEND Mode A entitlement beyond synthetic | Run/approve/close | — | — | Strong / None / None / Read | PIFSS/EOS worksheets | Synthetic markers remain for qual tenants | Finalize seals period; attendance/leave feed inputs |
| Payslips release | Finalized run | Released payslip + PDF | EXTEND | Release | — | View/download | Strong / None / Strong / Notify | Bilingual payslip fields | — | Employee sees only released |
| Bank / WPS payment files | Finalize | Export with payment_processing policy | EXTEND; enable per company with controls | Generate/ack | — | — | Strong / None / None / — | WPS format constraints | Drafts→live with kill switch | File generated; payment_processing still company-gated |
| Final settlement (pay) | Offboarding packet + payroll | Settlement run from inputs | EXTEND payroll; E360 remains inputs-only | Process | — | Receive | Strong / None / Thin / — | EOSB ownership Payroll | — | Settlement produces payslip/payment inputs; no E360 money math |
| OT authorization | Attendance + payroll | `ot_request`: request→approve→payroll component | NEW thin on attendance/payroll | Configure rates | Approve OT | Request | Strong / Thin / Thin / Confirm | OT premiums previously unsupported — now explicit | — | Approved OT appears in payroll input |

### 4.2 Wave 2 acceptance gate

- [ ] Entitled company: punches ingested → projections → exceptions → corrections applied
- [ ] Leave balances enforce; multi-step approve + delegation
- [ ] Manager can roster within scope without empty allowlist dead-end
- [ ] Payroll finalize authoritative for entitled company; payslips released to app
- [ ] Payment file generation gated, audited, kill-switchable
- [ ] Final settlement path from lifecycle inputs → payroll
- [ ] Analytics hooks emit canonical facts (hours, leave days, pay components) for Wave 5

---

## 5. Wave 3 — Employee Lifecycle

**Goal:** Job changes, employee-initiated requests, and exit are governed products — not impact-preview checklists.

**Depends on:** Wave 1 employment + Wave 2 settlement capability  
**Platform slice:** universal audit browser; identity revoke integrations; letter fulfillment  
**Build charter:** `ops/WATHEFNI_HCM_WAVE3_EMPLOYEE_LIFECYCLE_BUILD_CHARTER.md` (**APPROVED** 2026-08-11 — C1–C5 ACCEPTED/frozen; C6 `WAVE3_PRODUCT_FULL_PASS` QUALIFIED / Wave 3 frozen for owner sign-off; Assistant mutations out of MVP; real termination dark until separate C6+ owner unlock)

### 5.1 Capability matrix

| Capability | Dependency | Entities / SM | Authority | HR | Manager | Employee | Surfaces | Kuwait | Migration | Gate |
|---|---|---|---|---|---|---|---|---|---|---|
| Promotions | Org + comp contract | `employment_change_case` type=promotion | EXTEND org + payroll contract replace | Approve | Nominate | Ack | Strong / Thin / Thin / Confirm | Letter + contract update | History append-only | Promotion writes assignment + optional salary component |
| Transfers / dept / manager changes | Org units | Existing change types + case wrapper | EXTEND | Execute | Request | Ack | Strong / Thin / Thin / Confirm | — | — | History + manager scope updates |
| Secondments | Org | `secondment` with end date / dual reporting | NEW case type | Manage | Request | Ack | Strong / None / Thin / — | — | — | Auto-end job creates return assignment |
| Salary change (people event) | Payroll contracts | Case → compensation contract version | EXTEND bridge | Approve | Propose | View | Strong / None / Thin / — | — | — | People event and payroll contract same TX or linked IDs |
| ESS requests (personal, bank, letters) | ESS | Existing types + **letter fulfillment** | EXTEND; generate PDF | Approve/issue | — | Request | Strong / None / Strong / Notify | Employment letter / service certificate | Pending orders fulfilled or cancelled | Letter PDF issued + archived on employee docs |
| Dependents / emergency contacts | ESS | `dependents` entity | NEW | Verify | — | Maintain | Strong / None / Strong / — | Insurance later (Wave 6) | — | CRUD + audit |
| Resignation (employee-initiated) | Lifecycle | Case from ESS → notice_period | EXTEND lifecycle + ESS | Process | Ack | Resign | Strong / Thin / Strong / Confirm | Notice policy pack | — | Employee resign creates dual-control case |
| Termination / EOC | Lifecycle | Existing types + dual-control | EXTEND; broaden beyond synthetic | Execute | Initiate | — | Strong / Thin / None / — | Counsel pack | Controlled unlock | Real (non-synthetic) path for entitled company |
| Clearance / handover / assets | Offboarding | `clearance_checklist` item SM; asset return | NEW `offboarding`/`clearance` | Coordinate | Handover tasks | Clear items | Strong / Strong / Strong / Remind | Asset/IT items | Map onboarding asset_handover ≠ exit | Cannot close exit until required clearance done (or waived) |
| IT / access revocation | Clearance + auth | Session revoke + identity ticket | EXTEND app revoke + integration hooks | Trigger | — | — | Strong / None / None / — | — | — | App sessions dead; IdP ticket optional |
| Exit interview | Clearance | `exit_interview` form | NEW | Conduct | — | Submit | Strong / None / Thin / — | — | — | Stored; feeds analytics Wave 5 |
| Final settlement handoff | Wave 2 payroll | Inputs packet already; now mandatory before close | EXTEND | Complete | — | — | Strong / None / Thin / — | EOSB/encashment Payroll-only | — | Exit closed only after settlement ack or waiver |
| Rehire / alumni | Employment | Rehire already creates new employment; add alumni flag | EXTEND | Mark rehire-eligible | — | — | Strong / None / None / — | — | — | Prior employment visible; rehire link |

### 5.2 Wave 3 acceptance gate

- [ ] Promotion/transfer/salary-change cases mutate canonical employment + history
- [ ] Employee can resign in app; HR/manager path dual-controlled
- [ ] Clearance checklist blocks exit close; assets/IT tracked
- [ ] Letters fulfill from ESS orders
- [ ] Settlement handoff mandatory; money still Payroll-owned
- [ ] HR Mobile has lifecycle/clearance queues for entitled actions

---

## 6. Wave 4 — Performance + Talent

**Goal:** Managers and employees run goals and reviews; HR can calibrate and see succession — not CV keyword theater.

**Build charter:** `ops/WATHEFNI_HCM_WAVE4_PERFORMANCE_TALENT_BUILD_CHARTER.md` — **`WAVE4_PERFORMANCE_TALENT_CHARTER: APPROVED`** (2026-08-12; binding locks §0.8 including first-class OKRs, measure contracts, cycle snapshots, real 360 confidentiality, Talent independent of Performance, 9-box as view-only). Open for **C1 only**.  
**Depends on:** Stable org + manager scope (Wave 1–3); ratings feed Wave 5  
**Naming:** Recruiting `talent_pool` stays candidate-only; post-hire module is `talent`. Assessment “calibration” renamed in UI to “assessment norms”.

### 6.1 Capability matrix

| Capability | Dependency | Entities / SM | Authority | HR | Manager | Employee | Surfaces | Kuwait | Migration | Gate |
|---|---|---|---|---|---|---|---|---|---|---|
| Goals / KPIs | Org cascade optional | `goal`: draft→active→completed\|cancelled; period | NEW `performance` | Admin templates | Set/align | Own goals | Strong / Strong / Strong / Read | EN/AR goals | — | Goals CRUD; cascade link optional |
| Review cycles | Goals | `review_cycle` + `review` (self/manager) | NEW | Launch cycle | Write reviews | Self-review | Strong / Strong / Strong / Notify | — | — | Cycle locks; ratings stored |
| Check-ins | Goals | `check_in` notes | NEW | — | Continuous | Participate | Strong / Thin / Thin / — | — | — | Linked to goal |
| Competencies | Review | Competency library (can import assessment framework carefully) | NEW; **do not** overload pre-hire NBK framework silently | Maintain library | Rate | Self-rate | Strong / Thin / Thin / — | — | Optional import with explicit mapping | Competency scores on review |
| Development plans | Reviews/skills | `development_plan` | NEW | Oversee | Coach | Own | Strong / Thin / Strong / — | — | — | Plan items → tasks |
| Calibration | Reviews | Calibration session (performance) | NEW | Facilitate | Participate | — | Strong / None / None / — | — | Rename assessment UI “norms” | Ratings adjustable under audit |
| Career / talent profiles | Skills | Employee skill profile | NEW `talent` | View | Assess | Maintain | Strong / Thin / Strong / — | — | — | Distinct from candidate talent_pool |
| HiPo / 9-box / succession | Ratings + critical roles | `talent_review`, `succession_plan` | NEW | Run talent review | Nominate successors | — | Strong / Thin / None / — | — | — | Coverage % computable for Wave 5 |
| Internal mobility | Jobs + talent | Internal apply flag on jobs | EXTEND pre_hiring + talent | Oversee | Refer internal | Apply internal | Strong / Thin / Thin / — | — | — | Internal candidate linked to employee_key |

### 6.2 Wave 4 acceptance gate

- [ ] At least one full review cycle completed in entitled company (self+manager)
- [ ] Goals active for managers’ reports; mobile/app parity for employee/manager
- [ ] Calibration session audited; assessment “norms” rename shipped
- [ ] Succession coverage KPI inputs exist (even if Wave 5 visualizes later)
- [ ] No naming collision: Talent ≠ recruiting talent pool

---

## 7. Wave 5 — HR Intelligence

**Build charter:** `ops/WATHEFNI_HCM_WAVE5_HR_INTELLIGENCE_BUILD_CHARTER.md` — **`WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`**. **`WAVE5_PRODUCT_FULL_PASS` ACCEPTED** 2026-08-12 · evidence `ops/evidence/wave5-product-acceptance-20260812T103942Z` · freeze `ops/WAVE5_PRODUCT_FREEZE.md`. Global Wave 5 remains off / company-gated; broad production rollout separately owner-gated.

**Goal:** Every executive KPI has definition → canonical source → calculation → segmentation → trend → drill-down → permissions → export. No fake cards.

**Depends on:** Waves 1–4 facts. Attention Wave 1 remains ops triage, not a substitute.

### 7.1 KPI registry (minimum set)

| KPI | Source facts | Wave facts ready | Segmentation | Gate |
|---|---|---|---|---|
| Headcount (FTE/head) | employees + employment active | W1–3 | dept, grade, location, manager | Un-ban; publish definition |
| Hires / exits | hire_operations + lifecycle | W1–3 | reason, dept | Trend + export |
| Turnover / retention / regrettable | exits + tenure + regret flag | W3 | dept, manager | Definition signed |
| Time-to-fill / time-to-hire | requisition open → hire; offer accept | W1 | job, source | Recruiting Reports upgraded |
| Offer accept rate / source effectiveness | offers + inbound source | W1 | source, job | — |
| Onboarding completion time | completion contract | W1 | dept, template | — |
| Probation outcomes | probation_case | W1 | dept, manager | — |
| Absenteeism / lateness / OT | attendance projections | W2 | branch, dept | Rates not only counts |
| Leave utilization | leave ledger | W2 | type, dept | — |
| Workforce cost / payroll movement | payroll finalize | W2 | dept, component | Money KPI only when authoritative |
| Span of control / org composition | org assignments | W3 | — | Org chart optional |
| Goal attainment / performance distribution | performance | W4 | cycle, dept | — |
| High performers / HiPo / succession coverage | talent | W4 | critical role | — |
| HR SLA / workflow aging | tasks + approvals | W1+ | type | — |

### 7.2 Capability matrix (platform)

| Capability | Dependency | Entities | Authority | HR | Manager | Employee | Surfaces | Gate |
|---|---|---|---|---|---|---|---|---|
| KPI definition registry | Domain facts | `kpi_definition` versioned | NEW inside analytics | Publish defs | Scoped view | — | Strong / Thin / None / Read | Every card links to definition ID |
| Trends + segmentation + drill | Registry | Materialized facts / query layer | EXTEND analytics | Explore | Scoped | — | Strong / Thin / None / — | Drill to record list with perm check |
| Export / scheduled reports | Registry | Export jobs | EXTEND | Export | — | — | Strong / None / None / Notify | CSV/PDF; audit who exported |
| Attention ops retained | Existing | Keep Wave 1 attention | EXTEND | Triage | — | — | Strong / None / None / — | Labeled “Ops attention” ≠ strategic KPI |

### 7.3 Wave 5 acceptance gate

- [ ] Headcount KPI live with definition (freeze ban lifted intentionally)
- [ ] ≥12 KPIs from registry with trend + segment + drill + export
- [ ] No card without `kpi_definition_id`
- [ ] Manager scope enforced on all workforce KPIs
- [ ] EN/AR metric labels

---

## 8. Wave 6 — HCM Expansion

**Build charter:** `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` — **`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`** (owner 2026-08-12).  
**Prior gate:** Wave 5 ACCEPTED/frozen. **C1–C7 ACCEPTED/frozen**. **C8 QUALIFIED** `WAVE6_PRODUCT_FULL_PASS` · evidence `ops/evidence/wave6-product-acceptance-20260812T130121Z` — **STOP for owner sign-off; do not begin additional HCM domains automatically**.

**Goal:** Independent product authorities for remaining major HCM domains — not a shallow “complete HCM” checkbox suite. Prefer six well-separated modules with explicit OPTIONAL integration contracts.

| Domain | Module | Depends on | Thin-slice MVP first | Full later | Gate |
|---|---|---|---|---|---|
| Job Architecture (foundation) | `job_architecture` | Org/employment | Families + jobs + grades/levels + mapping | Full career-path graph | Shared SoT; no duplicate grade trees |
| L&D | `learning` | Tasks, employees; OPTIONAL C3 fulfill | Mandatory training + completion + expiry | LMS catalog, budgets | Works without Talent; no duplicate development_plan |
| Benefits | `benefits` | Employees; OPTIONAL dependents/payroll | Medical/insurance enrollment KW | Claims, renewals | Works without Payroll |
| Employee relations | `employee_relations` | Confidential RBAC; OPTIONAL approvals | Grievance + disciplinary sealed cases | Investigations, appeals | Manager ≠ ER visibility |
| Engagement | `engagement` | Notifications; anonymity policy | Pulse + eNPS | Recognition, action plans | Anonymity fails closed |
| Comp planning | `comp_planning` | **JA HARD**; OPTIONAL payroll/perf | Merit cycle worksheet | Pay equity | Approve ≠ silent salary change |
| Workforce planning | `workforce_planning` | **JA HARD**; OPTIONAL requisitions | Plan/scenario HC → explicit req handoff | Cost scenarios | Plan ≠ actual headcount |

**Serial stamps (proposed):** C0 charter · C1 `JOB_ARCHITECTURE_FULL_PASS` · C2 `LEARNING_DEVELOPMENT_FULL_PASS` · C3 `BENEFITS_FULL_PASS` · C4 `EMPLOYEE_RELATIONS_FULL_PASS` · C5 `ENGAGEMENT_FULL_PASS` · C6 `COMPENSATION_PLANNING_FULL_PASS` · C7 `WORKFORCE_PLANNING_FULL_PASS` · C8 `WAVE6_PRODUCT_FULL_PASS`.

---

## 9. Exact build order

### Phase A — Platform foundation (starts immediately; unblocks all waves)

1. `workflow_approvals` (N-step, SoD, delegation)  
2. Unified task ontology extension (`hr_tasks`)  
3. SLA / reminder policy object  
4. Module catalog entries + entitlements for new modules  
5. Offer→employment field sync + onboarding seed entitlement design (no silent global SEED=on)

### Phase B — Wave 1 (serial core)

1. Requisitions + job publish gate  
2. Preboarding module + readiness  
3. Hire TX: joining date, probation terms, auto-start onboarding (entitled)  
4. Probation plans 30/60/90 + confirmation SM  
5. Surface parity: Web primary, Mobile queues, App employee tasks, channel reminders  
6. **Gate: First customer-ready milestone**

### Phase C — Wave 2 (after Wave 1 gate; some parallel)

1. Attendance ingest entitlement + correction apply  
2. Leave enforcement + multi-step approve  
3. Shifts MSS allowlist unlock  
4. Payroll authoritative finalize + payslip release  
5. Payment file + final settlement  
6. **Gate: Workforce truth**

### Phase D — Wave 3

1. Employment change cases (promotion/transfer/salary)  
2. ESS letter fulfillment + dependents  
3. Resignation ESS + clearance module  
4. Exit interview + settlement mandatory handoff  
5. **Gate: Lifecycle complete**

### Phase E — Wave 4

1. Performance goals + review cycle  
2. Check-ins + competencies + development  
3. Calibration + talent/succession  
4. Naming cleanup (talent_pool vs talent; assessment norms)  
5. **Gate: Performance+Talent core**

### Phase F — Wave 5

1. KPI registry + headcount unban  
2. Wire facts from W1–4  
3. Trends/segment/drill/export  
4. **Gate: HR Intelligence**

### Phase G — Wave 6 (parallelizable domains)

L&D ‖ Benefits ‖ ER ‖ Engagement ‖ Comp planning ‖ Workforce planning (after grades)

---

## 10. What can develop in parallel

| Parallel track | Can overlap with | Constraint |
|---|---|---|
| Approvals engine + task ontology | Everything | Must land before req/leave N-step |
| Preboarding UI shell | Requisition backend | Blocked on offer accept events |
| Attendance device adapter | Leave enforcement | Both needed for Wave 2 gate |
| Payroll finalize hardening | Shifts MSS unlock | Settlement needs lifecycle packet (Wave 3) for full exit |
| Performance data model | Wave 3 clearance | Reviews need stable manager scope |
| KPI registry scaffolding | Wave 1–2 | Cards stay dark until facts exist |
| L&D mandatory training | Wave 4 | After tasks/SLA stable |
| Benefits vs ER | Wave 6 | Independent after dependents + confidential RBAC |

**Do not parallelize:** requisition gate before preboard marketing; SEED=on before joining-date sync; leave enforcement before policy legal pack; money KPIs before payroll finalize; succession UI before review ratings exist.

---

## 11. Milestones

### M1 — First customer-ready (serious first company)

**= Wave 1 acceptance gate + existing strong recruiting/onboarding/compliance under entitlement**

Customer can: approve headcount → hire → preboard → onboard → probation decision, EN/AR, Web/Mobile/App, audits.  
Still say honestly: time/pay may be Partial until M2.

### M2 — Operational HR (run the company)

**= M1 + Wave 2 gate + Wave 3 gate**

Customer can: clock/schedule/leave with enforcement, pay, change jobs, resign/exit with clearance and settlement.

### M3 — Complete HCM (mid-market claim)

**= M2 + Wave 4 gate + Wave 5 gate + Wave 6 MVP slices (Benefits KW + ER cases + mandatory L&D + pulse)**

Only then: “Wathefni is a complete Kuwait-first HR/HCM platform.”

---

## 12. Conceptual navigation grouping (not frozen IA)

**Runtime rule:** compose nav from `enabled modules ∩ permissions ∩ surface support`. If a group has zero children, **omit the group** (no empty Grow/Care/Plan/Hire shells).

### HR Web (conceptual full-suite grouping)

```text
Home / Inbox
People
  Employees · Organization · Org chart · Documents/Compliance
Hire          ← only if any hire modules enabled
  Requisitions · Jobs · Candidates · Interviews · Assessments · Offers
Ready         ← only if preboarding|onboarding|probation enabled
  Preboarding · Onboarding · Probation
Time / Pay / Grow / Care / Plan / Insights / Setup
  …same rule: show only entitled children
```

### HR Mobile

Queues-first: Inbox · Ready (preboard/onboard/probation) · Time · People · Hire (mutate parity for decisions) · More (Pay read-only initially)

### Employee App

Inbox · Workday/Schedule · Leave · Documents · Pay · Goals/Performance · Learn · Benefits · Profile/Requests · Exit (resign)

### Assistant / channels

Same tools as Web/Mobile capabilities; confirm-gated mutations; delivery via WhatsApp/Teams/email/SMS through Alerts & Delivery.

---

## 13. Traceability to audit (111 capabilities)

| Wave | Primary audit domains consumed |
|---|---|
| 1 | Workforce strategy (req), Recruitment (hire bridge), Preboarding, Onboarding, Post-onboarding, Platform |
| 2 | Time, Leave, Payroll, Platform integrations |
| 3 | Core HR, Offboarding, ESS/MSS, Compliance policy ack (partial→Wave 6 benefits) |
| 4 | Performance, Talent |
| 5 | Analytics (all KPI rows) |
| 6 | L&D, Benefits, ER, Engagement, Comp planning, Workforce planning/job architecture |

Partial “Complete” recruiting/onboarding capabilities remain in maintenance; this roadmap does not reopen frozen contracts without an explicit freeze amendment.

---

## 14. Explicit non-goals (near term)

- Blind copy of full Workday financials / global localization packs  
- Government filing/verification APIs (compliance freeze honesty retained)  
- Renaming recruiting talent pool to “Talent” without a real post-hire module  
- Strategic KPI cards without registry definitions  
- Global SEED=on / punch ingest on / payment_processing on without company entitlement  

---

**Authority note:** Implementation work under this roadmap requires a separate build charter per wave with freeze amendments where production gates (SEED, ingest, enforcement, synthetic payroll) change. This document alone does not unlock production flags.
