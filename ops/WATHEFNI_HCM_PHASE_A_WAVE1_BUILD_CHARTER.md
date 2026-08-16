# Phase A + Wave 1 Build Charter

**Status:** APPROVED — signed 2026-08-11 (provisional `pending_start` semantics locked)  
**Execution authority parent:** `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` (modularity amendment applied)  
**Audit SoT:** 111-capability HCM gap audit  
**Charter date:** 2026-08-11  
**Scope:** Phase A (shared foundations) + Wave 1 (Hire → Ready), modular/composable  
**Implementation gate:** Phase A slice 1 (`workflow_approvals` schema + authority behind flags) may proceed; Requisitions/Preboarding UI not started until Phase A slice 1 review PASS.

---

## 0. Charter principles (non-negotiable)

### 0.1 Modularity

| Rule | Requirement |
|---|---|
| Independent enablement | Every new/extended module works alone when enabled |
| Composability | Complementary modules enrich via contracts — not silent hard wiring |
| Hard deps only when true | Catalog `depends_on` only for HARD DEPENDENCY |
| Clean disappearance | Disabled modules vanish from HR Web, HR Mobile, Employee App, Assistant — no empty nav shells |
| Premium small suites | 2–3 module tenants still get intentional IA and complete workflows |
| Full-suite richness | Entitled multi-module tenants get connected hire→ready experience |
| Canonical truth | Shared `employees` / employment / org / workflow records — no per-module duplicate SoT |

### 0.2 Dependency classes (use everywhere below)

| Class | Definition |
|---|---|
| **HARD DEPENDENCY** | Cannot enable or operate Module B without A |
| **OPTIONAL INTEGRATION** | B works alone; when A enabled, a versioned contract connects them (company may configure) |
| **ENHANCEMENT WHEN ENABLED** | B works alone; A present improves UX/automation/analytics only |

### 0.3 Dynamic navigation (not frozen IA)

Roadmap groupings (Hire / Ready / Grow / …) are **conceptual**. Runtime nav =  
`enabled company modules ∩ permission grants ∩ surface capability matrix`.  
If a conceptual group has zero visible children → **omit the group entirely**.

### 0.4 Out of scope for this charter

Wave 2–6 capabilities, background-check vendor product, full letter PDF fulfillment (Wave 3), strategic KPI suite (Wave 5), Benefits/ER/L&D, global SEED=on / punch ingest / payroll money unlocks.

---

## 1. Exact scope

### 1.1 Phase A — Shared foundations (required by Wave 1)

| Workstream | Deliverable |
|---|---|
| A1 | `workflow_approvals` — multi-step approval engine + SoD |
| A2 | Delegation / substitution on approvals |
| A3 | Unified task ontology extension (`hr_tasks` + inbox consumers) |
| A4 | SLA / reminder policy object + breach → task/notification |
| A5 | Module catalog + Setup Console entitlements for new modules + capability contracts registry |
| A6 | Offer → employment → onboarding **truth synchronization** (joining date, probation terms; seed policy hooks) — as **optional integrations**, not forced coupling |

### 1.2 Wave 1 — Hire → Ready (after Phase A contracts land)

| Workstream | Deliverable |
|---|---|
| W1.1 | `requisitions` module — manpower/headcount request + approval |
| W1.2 | OPTIONAL job-publish gate when `requisitions` ∧ `pre_hiring` |
| W1.3 | `preboarding` module — readiness program (standalone + offer/onboarding integrations) |
| W1.4 | Joining-date canonical write paths (hire / manual / offer-accept when offers on) |
| W1.5 | Automatic onboarding start when `onboarding` entitled (config + hire hook) |
| W1.6 | `probation` module — 30/60/90 milestones + confirm/extend/fail |
| W1.7 | Surfaces: HR Web, HR Mobile, Employee App, Assistant (read), channels (notify) |
| W1.8 | EN/AR, RBAC/manager scope, analytics/audit hooks, flags, freeze amendments, tests, rollback |

### 1.3 Explicit non-goals (this charter)

- Forcing Recruiting to enable Preboarding (or vice versa)
- Forcing job publish to require requisitions when only `pre_hiring` is enabled
- Building empty Grow/Care/Plan shells
- Unlocking attendance ingest, leave enforcement, or payroll money
- Assistant mutations on by default (`ASSISTANT_MUTATIONS` remains 0 unless separate confirm charter)

---

## 2. Dependency matrix (Phase A + Wave 1)

### 2.1 Platform / Phase A

| Capability | Relates to | Class | Notes |
|---|---|---|---|
| `workflow_approvals` | Company + RBAC | HARD: core authz only | Not a sold HCM module; platform capability |
| Delegation | `workflow_approvals` | HARD | Sub-feature of approvals |
| Unified tasks | Existing `hr_tasks` | HARD: task store | New types are additive |
| SLA / reminders | Tasks + notification delivery | HARD: notification bus | Policy is new; delivery EXTEND |
| Module catalog entries | `module_catalog` + `company_modules` | HARD: catalog infra | |
| Capability contracts registry | Catalog | HARD: catalog infra | Declares OPTIONAL/ENHANCEMENT links |
| Offer→employment sync | `employment_offers` | OPTIONAL INTEGRATION | Runs only if offers module enabled + event fires |
| Hire→employment field write | Hire path (always when hiring) | HARD: hire operation exists | Joining/probation fields on employment are Core HR |
| Hire→onboarding seed | `onboarding` | OPTIONAL INTEGRATION | Only if onboarding entitled + company seed policy on |
| Employment→onboarding planned_start | `onboarding` | OPTIONAL INTEGRATION | Sync when assignment exists |

### 2.2 Wave 1 modules

| Module / capability | Relates to | Class | Notes |
|---|---|---|---|
| `requisitions` | Core company/RBAC/org units | HARD | Works without Recruiting |
| `requisitions` ↔ `pre_hiring` | Job create/publish gate | OPTIONAL INTEGRATION | Company setting: `jobs_require_approved_requisition` default **on** when both enabled; **off** if only pre_hiring |
| `requisitions` ↔ org/positions | Position link | ENHANCEMENT WHEN ENABLED | Req can exist with free-text role if positions absent |
| `preboarding` | Canonical employee/employment | HARD | Must attach to a person/employment (or pre-hire provisional employee record — see §3) |
| `preboarding` ↔ `employment_offers` | Auto-create program on accept | OPTIONAL INTEGRATION | Manual/HR-created preboard when offers off |
| `preboarding` ↔ `pre_hiring` / candidates | Link application_id | ENHANCEMENT WHEN ENABLED | Traceability only |
| `preboarding` ↔ `onboarding` | Handoff / dedupe items | OPTIONAL INTEGRATION | Preboard alone can complete “ready”; onboard alone unchanged |
| `preboarding` ↔ `compliance` / docs | Doc upload/review | OPTIONAL INTEGRATION | Prefer shared doc APIs when compliance on; else embedded upload contract |
| Joining-date truth | Employment record | HARD (Core HR field) | Writers: manual HR, hire TX, offer-accept (optional) |
| Onboarding auto-start | `onboarding` module | HARD to use feature: onboarding enabled | Feature is config inside onboarding, not a separate module |
| Onboarding auto-start ↔ hire | Hire TX | OPTIONAL INTEGRATION | If onboarding off, hire still succeeds |
| `probation` | Employment | HARD | |
| `probation` ↔ `onboarding` | Start milestones after onboard complete | OPTIONAL INTEGRATION | Also allow start-from-hire+N days without onboarding |
| `probation` ↔ `employment_offers` | probation_days sync | OPTIONAL INTEGRATION | Manual probation dates when offers off |
| `probation` ↔ lifecycle | Fail → termination case | OPTIONAL INTEGRATION | Fail can stop at “failed” status if lifecycle module/path unavailable; when lifecycle available, open case |
| Approvals used by requisitions/probation | `workflow_approvals` | HARD for N-step | Single-step fallback if platform approvals not yet migrated for that entity type (charter requires A1 before W1.1 N-step) |
| Tasks for all Wave 1 entities | Task ontology | HARD | |
| SLA on Wave 1 entities | SLA policy | ENHANCEMENT WHEN ENABLED | Default templates ship; company may disable |

---

## 3. Canonical entities and state machines

### 3.1 Phase A

#### `approval_policy` / `approval_instance` / `approval_step`

```text
approval_instance:
  draft → pending → (step*) → approved | rejected | cancelled | expired
step:
  pending → approved | rejected | skipped | delegated
```

- Policy binds to `subject_type` (requisition, probation_decision, …) + company
- SoD: optional `forbid_self_approval`
- Idempotent decide with `decision_id` / version

#### `delegation_grant`

```text
scheduled → active → revoked | expired
```

- `delegator_user_id`, `delegate_user_id`, scope (all approvals | subject_types[]), window

#### Task ontology (extend `hr_tasks` or successor)

New `task_type` values (additive):

| task_type | subject |
|---|---|
| `requisition_approval` | requisition_id |
| `preboard_item` | preboard_item_id |
| `preboard_readiness` | preboard_assignment_id |
| `probation_milestone` | milestone_id |
| `probation_decision` | probation_case_id |
| `sla_breach` | any subject |

Status reuse existing task SM where possible; do not fork a second inbox SoT.

#### `sla_policy` / `sla_clock`

```text
clock: running → breached | satisfied | cancelled
```

- `subject_type`, `priority`, `due_in`, `escalate_to` (role | user | task_type)
- Breach emits notification + `sla_breach` task

#### Capability contract registry (catalog metadata)

Machine-readable declarations, e.g.:

```text
contract_id: requisitions.gate_job_publish
class: OPTIONAL_INTEGRATION
requires_modules: [requisitions, pre_hiring]
company_setting: jobs_require_approved_requisition
```

### 3.2 Wave 1

#### `requisition`

```text
draft → pending_approval → approved → open → filled | cancelled
         ↘ rejected → draft (revise)
```

Fields (min): company_code, title_en/ar, department/org_unit, headcount, target_hire_date, budget_ref?, position_id?, created_by, approval_instance_id  
**No HARD link to job_id** — jobs link optionally when both modules on.

#### `preboard_assignment` + `preboard_item`

```text
assignment: not_started → in_progress → ready | blocked → converted | cancelled
item: pending → in_progress → done | waived | blocked
```

**HARD attachment:** must reference canonical identity:

| Mode | Attachment |
|---|---|
| Employee exists | `employee_key` + employment |
| Pre-hire only (offers/candidates optional) | Create **provisional employment** `lifecycle_state=pending_start` on canonical employees path — shared SoT, not a preboard-only person table |

Items: owner (hr|manager|employee|it|other), due_at, depends_on[], doc refs via shared document API when available.

#### Provisional `pending_start` employment (LOCKED)

Provisional employment used by Preboarding is **canonical employment truth for a future joiner**, not an active employee. Invariants:

| # | Invariant |
|---|---|
| P1 | Canonical SoT on shared employees/employment path — never a preboard-only person duplicate |
| P2 | Not an active employee; UI/manager/org visibility must distinguish **joining** vs **active** |
| P3 | Excluded from **active headcount** unless a KPI explicitly defines pending starters separately |
| P4 | Excluded from payroll, attendance, leave balances, shifts, and normal post-hire workflows |
| P5 | Must **not** automatically receive normal Employee App capabilities; only preboarding-specific access/tasks when entitled |
| P6 | Cancelled / no-show / withdrawn hires must **close** the provisional employment cleanly with audit history |
| P7 | Actual start/hire **converts the same canonical record forward** — no duplicate employee/employment truth |
| P8 | Joining-date changes update the same authority and propagate to enabled integrations |
| P9 | Tenant/RBAC isolation applies **before** activation exactly as after activation |

#### Joining-date truth

Canonical field: `employment.joining_date` (or existing planned_start equivalent — **single field name chosen in implementation design review; no dual SoT**).

Writers (priority): explicit HR edit (audited) > hire TX > offer accept (if offers on).  
Readers: preboard, onboarding, probation, UI — all read employment.

#### Onboarding auto-start (extend existing)

When company policy `onboarding.auto_start_on_hire=true` **and** module `onboarding` enabled:  
hire TX creates `employee_onboarding_assignments` from template (entitlement-safe; not global SEED=on).

#### `probation_case` + `probation_plan` + `milestone`

```text
case: scheduled → active → under_review → confirmed | extended | failed | cancelled
milestone: pending → completed | skipped | overdue
```

- Case binds to employment; `probation_start` / `probation_end` on employment remain SoT dates
- Extension writes new `probation_end` + audit
- Fail: set status failed; **OPTIONAL INTEGRATION** opens lifecycle termination case when available

---

## 4. Module contracts and catalog registration

### 4.1 New commercial modules (Setup Console)

| module_key | Label | suite | HARD depends_on | recommended_with |
|---|---|---|---|---|
| `requisitions` | Requisitions | pre_hire or post_hire (recommend pre_hire) | `()` | `pre_hiring`, `workflow` N/A |
| `preboarding` | Preboarding | post_hire | `()` — requires employee authority only | `employment_offers`, `onboarding`, `compliance` |
| `probation` | Probation | post_hire | `()` — requires employment | `onboarding`, `employment_offers` |

Platform `workflow_approvals` / SLA / tasks are **not** sold toggles; they ship with platform and are always available to entitled modules.

### 4.2 Company settings (Wave 1)

| Setting | Default when applicable | Meaning |
|---|---|---|
| `jobs_require_approved_requisition` | `true` if both modules on else N/A | OPTIONAL INTEGRATION |
| `preboarding.auto_create_on_offer_accept` | `true` if both on | OPTIONAL INTEGRATION |
| `preboarding.required_for_ready_mark` | `true` if preboarding on | Blocks “ready” until checklist |
| `onboarding.auto_start_on_hire` | `false` globally; entitled canary may set `true` | OPTIONAL INTEGRATION — freeze amendment |
| `probation.auto_plan_on_hire` | `true` if probation on | Creates plan from template |
| `probation.start_mode` | `hire_date` \| `onboarding_complete` | OPTIONAL INTEGRATION with onboarding |

### 4.3 Surface composition rules

```text
visible(module) = company_modules.enabled
               ∧ permission.allows
               ∧ surface.supports(module)
nav_group.show = count(visible children) > 0
assistant.tool.show = same
```

---

## 5. Migrations (schema + data)

### 5.1 Additive schema (forward-safe)

- Approval / delegation / SLA tables — `IF NOT EXISTS`
- Requisition / preboard / probation tables — `IF NOT EXISTS`
- Employment columns only if missing: ensure `joining_date` (or aliased), `probation_*` already exist — **no destructive rename in Wave 1**; add compatibility view if renaming later
- Task type enum/check constraints expanded additively
- Catalog rows inserted for new modules (disabled by default)

### 5.2 Data backfill (production-safe, opt-in)

| Backfill | Default | Notes |
|---|---|---|
| Offer.proposed_start_date → employment joining | **Off** | Script with dry-run; only rows where employment joining null |
| Offer.probation_days → employment probation dates | **Off** | Same |
| Open jobs → legacy_unrequisitioned marker | **On** when requisitions enabled | Metadata only — does not invent fake approved reqs |
| Active employments with probation_end → probation_case | **Off** | Entitled company batch |
| pending_start employees → optional preboard | **Off** | Manual HR create preferred |

### 5.3 No dual SoT

Forbid new tables that copy employee name/dept/manager. Preboard/probation store only foreign keys + phase-specific fields.

---

## 6. Permissions / RBAC / manager scope

### 6.1 Permission keys (additive)

| Permission | Module |
|---|---|
| `requisitions.read` / `create` / `edit` / `approve` / `cancel` | requisitions |
| `preboarding.read` / `manage` / `waive_item` | preboarding |
| `probation.read` / `manage` / `decide` | probation |
| `approvals.decide` / `delegate` (platform) | platform |
| Existing `jobs.publish` interacts with gate | pre_hiring |
| Existing `onboarding.manage` | onboarding |
| Existing hire permissions | hire |

SoD: `requisitions.approve` should not be identical to sole `create` for high-risk companies (configurable).

### 6.2 Manager scope

- Requisition approve: if manager step, only within org scope / designated approver
- Preboard manager items: manager of employee only
- Probation recommend/decide (manager step): manager of employee only
- HR permissions bypass scope with audit

### 6.3 Employee App grants

- Preboard items owned by employee
- Probation feedback / view own case
- No requisition employee surface in Wave 1

---

## 7. Setup Console entitlements / config

- Purchase/enable `requisitions`, `preboarding`, `probation` independently
- Readiness checks: each module lists blockers (e.g. missing approval policy template)
- Contract entitlements remain shadow-friendly per existing TC patterns until flipped
- Wizard copy EN/AR: explain OPTIONAL integrations (“Enable Offers to auto-start Preboarding on accept”)
- Module disable: hide nav/tools; **retain data**; block new mutations; in-flight approvals completable or cancel policy documented

---

## 8. Approval / delegation / SLA contracts

### 8.1 Subjects in Wave 1

| Subject | Default chain | Delegation | SLA |
|---|---|---|---|
| `requisition` | Manager → HR (company template) | Yes | Time-to-approve |
| `probation_decision` | Manager recommend → HR decide | Yes | Decision before probation_end |
| `preboard_exception_waive` (optional) | HR only | Optional | — |

### 8.2 API contract (sketch)

```text
POST /dashboard/workflow/approvals/{id}/decide
POST /dashboard/workflow/delegations
GET  /dashboard/workflow/approvals?mine=1
```

Domain modules create `approval_instance` — they do not implement step engines.

### 8.3 SLA templates shipped

- Requisition pending_approval: 3 business days → escalate HR
- Preboard item overdue: remind owner daily ×3 → escalate HR
- Probation milestone overdue: remind manager → escalate HR
- Probation decision window: T-7 / T-3 / T-0 relative to probation_end

---

## 9. Workflows by persona

### 9.1 HR

1. Configure approval templates + SLA + module settings  
2. Create/approve requisitions (or approve manager-raised)  
3. Create preboard (manual) or monitor auto-created from offer  
4. Hire / confirm joining date  
5. Monitor onboarding (if enabled)  
6. Drive probation review; confirm/extend/fail  

### 9.2 Manager

1. Raise requisition / approve step  
2. Complete preboard manager tasks  
3. Complete 30/60/90 check-ins  
4. Recommend probation outcome  

### 9.3 Employee

1. Complete preboard tasks (docs, bank readiness forms)  
2. Complete onboarding tasks (if module on)  
3. View probation status; submit feedback when asked  

---

## 10. Surfaces

| Capability | HR Web | HR Mobile | Employee App | Assistant | Channels |
|---|---|---|---|---|---|
| Approvals inbox | Strong | Strong | — | Read list; decide later charter | Push/email |
| Requisitions | Strong | Thin (queue/approve) | — | Read + confirm approve | Notify approvers |
| Preboarding | Strong | Strong | Strong | Status/remind | WA/email reminders |
| Joining date | Strong | Thin | View | Read | — |
| Onboarding auto-start | Existing + config | Existing | Existing | Status | Existing welcome |
| Probation | Strong | Thin (milestones/decide) | Thin (view/feedback) | Read/remind | Reminders |
| Dynamic nav | Compose | Compose | Compose | Tool filter | — |

**Empty shell rule:** If only `preboarding` + `probation` enabled (no recruiting), nav shows Ready/People-style entries that exist — **not** an empty Hire group.

---

## 11. EN / AR

- All new UI strings in dashboard + mobile i18n dictionaries  
- Requisition/preboard/probation templates bilingual (title_en/title_ar)  
- Notification templates bilingual  
- RTL layouts for new screens  
- Acceptance: EN + AR screenshots or Maestro/i18n key coverage in tests  

---

## 12. Analytics / audit hooks

### 12.1 Audit (required)

Every state transition on requisition, preboard item/assignment, probation case/milestone, approval step, joining_date change, seed/auto-start — append-only audit with actor, before/after, company_code.

### 12.2 Analytics facts (emit now, visualize Wave 5)

| Fact event | Payload keys |
|---|---|
| `requisition_approved` | requisition_id, headcount, ts |
| `preboard_ready` / `preboard_blocked` | assignment_id, employee_key, ts |
| `onboarding_auto_started` | employee_key, assignment_id |
| `joining_date_set` | employee_key, source, date |
| `probation_milestone_completed` | milestone_id, due/actual |
| `probation_confirmed` / `extended` / `failed` | case_id, ts |

No executive KPI cards in Wave 1 without definitions (Wave 5). Ops inbox counts OK.

---

## 13. Rollout flags

| Flag / entitlement | Default prod | Purpose |
|---|---|---|
| Module `requisitions` in company_modules | disabled | Opt-in |
| Module `preboarding` | disabled | Opt-in |
| Module `probation` | disabled | Opt-in |
| `onboarding.auto_start_on_hire` | **false** | Freeze-safe |
| `WATHEFNI_ONBOARDING_SEED` | remains **off** globally | Entitlement path supersedes blind global on |
| `jobs_require_approved_requisition` | true only if both modules on | |
| `workflow_approvals` platform | on for entitled companies using new subjects | Legacy offer/leave SoD unchanged until migrated |
| Feature flag `hire_ready_wave1` | off | Umbrella kill switch for new mutate routes |

---

## 14. Freeze amendments (explicit)

| Freeze / posture | Amendment request |
|---|---|
| Onboarding SEED=off | Allow **company-entitled** auto-start via `onboarding.auto_start_on_hire` without flipping global env to on for all tenants |
| Organization “no headcount plan” | Requisitions are **manpower requests**, not workforce planning forecasts — does not violate Organization Wave1 ban on forecast UI |
| Employees 360 synthetic lifecycle | Probation fail → lifecycle case only when lifecycle mutations allowed; else terminal probation status + HR task |
| Analytics no headcount | Wave 1 emits facts only; no Headcount summary card |
| Assistant mutations=0 | Wave 1 Assistant **read/remind only** |

Each amendment needs a one-page freeze note + rollback before production entitle.

---

## 15. Production-safe migration strategy

1. Deploy schema additive + catalog rows (modules disabled)  
2. Deploy Phase A APIs behind flag; no UI entry points  
3. Qualify Phase A on WATHEFNIQA / synthetic  
4. Enable Wave 1 modules for **one canary company**  
5. Dry-run backfills; apply only with operator approval  
6. Expand entitlement  
7. Never enable `onboarding.auto_start_on_hire` globally in this charter  

Rollback: disable modules + umbrella flag; schema remains; in-flight approvals cancellable via admin tool.

---

## 16. Acceptance tests

### 16.1 Phase A

| ID | Test |
|---|---|
| PA-01 | Create 2-step approval; both steps required; SoD blocks self-approve when configured |
| PA-02 | Delegation: delegatee decides; audit shows acting_as |
| PA-03 | SLA breach creates `sla_breach` task + notification |
| PA-04 | Task types appear in Web + Mobile inbox |
| PA-05 | Contract registry lists OPTIONAL integrations; disabling module hides tools |
| PA-06 | Offer accept writes joining_date + probation terms **only when offers enabled** and employment exists/created |
| PA-07 | Hire with onboarding auto-start **off** does not create assignment |
| PA-08 | Hire with onboarding auto-start **on** + module enabled creates assignment in same TX |

### 16.2 Wave 1 modularity

| ID | Test |
|---|---|
| M-01 | Company with **only** `requisitions`: full req workflow; **no** Hire/Jobs nav; **no** empty shells |
| M-02 | Company with **only** `pre_hiring`: jobs publish **without** requisition |
| M-03 | Company with both + gate on: publish blocked without approved req; override grant audited |
| M-04 | Company with **only** `preboarding`: HR creates assignment on pending_start employee; readiness works |
| M-05 | Company with preboarding + offers: accept auto-creates preboard when setting on |
| M-06 | Company with **only** `probation`: plan + confirm works without onboarding module |
| M-07 | Company with probation + onboarding: `start_mode=onboarding_complete` respected |
| M-08 | Disable `preboarding`: nav/tools gone; App/Assistant tools gone; data retained |

### 16.3 Wave 1 E2E (full-suite entitled)

| ID | Test |
|---|---|
| E2E-01 | Requisition → approve → (optional) job link → offer accept → preboard → ready → hire → onboard auto-start → 30/60/90 → confirm |
| E2E-02 | Probation extend writes new end + milestones |
| E2E-03 | Probation fail creates HR task; lifecycle case if allowed |
| E2E-04 | EN + AR paths for HR Web critical screens |
| E2E-05 | Manager scope: cannot approve out-of-scope requisition/probation |
| E2E-06 | Channel reminder fires on overdue preboard item |

### 16.4 Cross-surface

| ID | Test |
|---|---|
| XS-01 | Same requisition approve via Web and Mobile (canonical) |
| XS-02 | Employee completes preboard item in App; HR Web reflects |
| XS-03 | Assistant lists preboard status; cannot mutate |

---

## 17. Rollback plan

| Layer | Action |
|---|---|
| Runtime | Set `hire_ready_wave1=off`; disable company_modules for new modules; set `onboarding.auto_start_on_hire=false` |
| UI | Nav composition drops modules automatically |
| Approvals | Legacy offer/leave paths untouched; new subjects stop creating instances |
| Data | Retain tables; provide export; no drop |
| Backfills | Reversible only where we stored prior values in audit; document irreversible date fills |
| Comms | Canary stamp + ROLLBACK.sh pattern under `ops/evidence/` |

---

## 18. Dependency-ordered build plan + parallelism

### 18.1 Serial backbone (must respect)

```text
A1 workflow_approvals
  → A2 delegation
  → A3 task ontology types
  → A4 SLA policy (uses tasks + notify)
  → A5 catalog + contracts + settings
  → A6 truth sync hooks (offer/hire/onboarding) behind flags
  → W1.1 requisitions (uses A1–A4)
  → W1.2 optional job gate contract
  → W1.3 preboarding (uses A1–A4, employment)
  → W1.4 joining-date writers unified
  → W1.5 onboarding auto-start setting + hire hook
  → W1.6 probation
  → W1.7 surface polish + i18n
  → W1.8 qual / freeze notes / canary entitle
```

### 18.2 Safe parallel tracks

| Track | Can start after | Parallel with |
|---|---|---|
| P1 — Approvals engine + delegation | Charter approval | P2 task type design |
| P2 — Task ontology + inbox consumers (Web/Mobile) | A1 subject IDs known | P1 |
| P3 — SLA policy + notification templates EN/AR | A3 task types | P4 |
| P4 — Catalog modules + Setup Console copy + settings | Charter approval | P1–P3 |
| P5 — Employment joining/probation field audit + sync dry-run tools | Charter approval | P1–P4 (no UI) |
| P6 — Requisitions UI/API | A1+A3+A5 | Preboarding API skeleton (P7) **after** employment provisional design agreed |
| P7 — Preboarding API/UI | A3+A5+ employment attach rule | Probation data model (P8) |
| P8 — Probation API/UI | A1+A3+A5 | P7 |
| P9 — Optional contracts (job gate, offer→preboard, hire→onboard) | Both sides’ APIs exist | — |
| P10 — Employee App surfaces | Preboard/probation APIs stable | HR Mobile queues |
| P11 — Freeze amendment docs + evidence harness | Before canary entitle | Final qual |

### 18.3 Do not parallelize

- Job publish gate before requisitions exist  
- Offer→preboard auto-create before preboard assignment API  
- `onboarding.auto_start_on_hire=true` before joining-date writer unification  
- Probation fail→lifecycle before fail status works standalone  
- Canary entitle before PA-* and M-* tests green  

---

## 19. Charter acceptance (review checklist)

Reviewers sign before implementation:

- [x] Modularity rules accepted (independent modules, no empty shells, dynamic nav)  
- [x] Dependency classes accepted for every Wave 1 edge  
- [x] Provisional employment approach for pre-hire preboarding accepted (canonical SoT)  
- [x] Provisional `pending_start` semantics locked (§3.2 P1–P9)  
- [x] Freeze amendments accepted (§14)  
- [x] Parallel plan accepted  
- [x] Rollback accepted  
- [x] Charter signed — Phase A slice 1 implementation authorized; Wave 1 product UI gated on slice-1 review  

### 19.1 Acceptance / rollback checks — provisional `pending_start` (P1–P9)

These checks apply when Preboarding / hire-ready Wave 1 lands (not Phase A slice 1). Fail any ⇒ no canary entitle for Preboarding.

| ID | Acceptance check | Rollback / mitigation |
|---|---|---|
| PA-PS-01 | Provisional row is on canonical employment SoT with `lifecycle_state=pending_start` (no parallel person table) | Disable preboarding module; retain rows; no drop |
| PA-PS-02 | Active headcount KPIs exclude `pending_start` unless KPI explicitly counts pending starters | Revert KPI query; keep employment state |
| PA-PS-03 | Payroll / attendance / leave / shifts / normal post-hire workflows reject or skip `pending_start` | Feature flags off; no payroll/attendance writes for provisional |
| PA-PS-04 | Employee App grants only preboarding-scoped capabilities when entitled — not normal ESS | Revoke employee_app entitlement / capability flags |
| PA-PS-05 | Manager/org surfaces label joining vs active distinctly (EN+AR, LTR+RTL) | Hide provisional from org views via flag |
| PA-PS-06 | Cancel / no-show / withdraw closes provisional employment with immutable audit event | Re-open only via audited correction path |
| PA-PS-07 | Hire/start converts **same** employment_id forward; no second employment created for same hire | Block duplicate-create path; repair via migration playbook if violated |
| PA-PS-08 | Joining-date write updates single authority and fans out only to **enabled** integrations | Disable integration contracts; employment date remains SoT |
| PA-PS-09 | Cross-tenant access denied for provisional rows identically to active (RBAC before activation) | Fail closed; revoke offending tokens/sessions |

---

## 20. Document control

| Version | Date | Notes |
|---|---|---|
| 0.1 | 2026-08-11 | Initial charter for review; modularity amendment from roadmap approval |
| 0.2 | 2026-08-11 | Approved; locked provisional `pending_start` P1–P9 + §19.1 acceptance/rollback |
| 0.3 | 2026-08-11 | Slice 1 FULL PASS (staging DB); Slice 2 task ontology + SLA implemented behind flags |
| 0.4 | 2026-08-11 | Slice 2 invariants locked; Slice 3 catalog/contracts + truth-sync dry-run FULL PASS |
| 0.5 | 2026-08-11 | Wave 1 requisitions backend + optional job publish gate (flags; no UI) — see `ops/REQUISITIONS_WAVE1_BACKEND.md` |
| 0.6 | 2026-08-11 | Requisitions backend FROZEN; Preboarding backend + readiness + tasks/SLA FULL PASS (no UI) — see `ops/PREBOARDING_WAVE1_BACKEND.md` |
| 0.7 | 2026-08-11 | Preboarding backend FROZEN; Surface Wave FULL PASS (HR Web + HR Mobile + Employee App core) — see `ops/PREBOARDING_SURFACE_WAVE.md` |

**Progress:** Phase A Slices 1–3 FULL PASS · Requisitions + Preboarding backends FROZEN · Preboarding surfaces FULL PASS · Probation not started · truth-sync writers remain OFF.
