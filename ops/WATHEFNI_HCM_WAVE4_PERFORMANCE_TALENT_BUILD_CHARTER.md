# Wave 4 — Performance + Talent Build Charter

**Status:** APPROVED — `WAVE4_PERFORMANCE_TALENT_CHARTER: APPROVED` (owner 2026-08-12; binding product locks §0.8)  
**Execution authority parent:** `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` §6  
**Prior gate:** `WAVE3_PRODUCT_FULL_PASS` **ACCEPTED** 2026-08-12 — Wave 3 remains frozen (`ops/WAVE3_PRODUCT_FREEZE.md`)  
**Wave 2 freeze:** `WAVE2_PRODUCT_FULL_PASS` ACCEPTED — Workforce Truth remains frozen  
**Wave 1 freeze:** `WAVE1_PRODUCT_FULL_PASS` ACCEPTED — Hire→Ready remains frozen  
**Audit SoT:** 111-capability HCM gap audit + roadmap §6  
**Charter date:** 2026-08-12 · **Approved:** 2026-08-12  
**Scope:** Wave 4 — Performance + Talent (OKRs/goals/KPIs → reviews/calibration → development → talent mapping → succession/mobility)  
**Implementation gate:** **C1–C7 ACCEPTED/FROZEN** (`WAVE4_PRODUCT_FULL_PASS` ACCEPTED 2026-08-12). Binding locks §0.8 remain in force. Wave 5 = charter/design only until `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED` — **no Wave 5 implementation yet**.

---

## 0. Charter principles (non-negotiable)

### 0.1 Product honesty

Wave 4 builds a **genuine post-hire performance and talent system**, not generic review forms.

| Forbidden | Required instead |
|---|---|
| Fake KPI dashboards without defined formulas | Versioned goal/KPI definitions + calculation semantics before any card |
| “Talent pool” meaning recruiting candidate pool | Post-hire module key = `talent`; recruiting stays `talent_pool` (candidate-only) |
| Calibration confused with assessment norms | Performance **calibration** ≠ pre-hire assessment **norms** (UI rename already required by roadmap) |
| 9-box labels without canonical performance × potential inputs | 9-box only when both axes are populated from owned authorities |
| Review forms that leave no durable development truth | Reviews produce ratings, acknowledgements, and development actions (tasks/plans) |

### 0.2 Modularity (same as Waves 1–3)

| Rule | Requirement |
|---|---|
| Independent enablement | Performance works **without** Talent |
| Goals without cycles | Goals/KPIs work without formal review cycles |
| Competencies independent | Competency library + ratings can enable without full cycle suite where configured |
| Succession without 9-box | Succession plans work from critical roles + successor readiness without 9-box |
| Talent optional on Performance | Talent may consume Performance outcomes; **must not** require them universally |
| Mobility optional on Recruiting | Internal mobility integrates with Jobs/Recruiting via OPTIONAL contract — never hard-wired |
| Clean disappearance | Disabled modules/capabilities vanish from HR Web, HR Mobile, Employee App, Assistant — no empty shells |
| Canonical truth | Shared `employees` / employment / org / manager scope / `hr_tasks` / approvals — **no shadow employee or parallel talent person model** |

### 0.3 Dependency classes

| Class | Definition |
|---|---|
| **HARD DEPENDENCY** | Cannot enable or operate Module B without A |
| **OPTIONAL INTEGRATION** | B works alone; when A enabled, a versioned contract connects them (company-configurable) |
| **ENHANCEMENT WHEN ENABLED** | B works alone; A present improves UX/automation/analytics only |

### 0.4 Dynamic navigation

Runtime nav = `enabled company modules ∩ permission grants ∩ surface capability matrix`.  
Zero visible children → omit the group entirely (no “Grow/Performance” empty shell).

### 0.5 Prior freeze boundaries (do not reopen)

| Freeze | Rule for Wave 4 |
|---|---|
| Wave 1 Hire→Ready | Do **not** reopen for Wave 1 safe debt |
| Wave 2 Workforce Truth | Do **not** reopen for Wave 2 safe debt |
| Wave 3 Employee Lifecycle | Do **not** reopen for Wave 3 safe debt; real termination remains locked |
| Real termination | `WATHEFNI_REAL_TERMINATION_CANARY=off` until owner **explicitly names** a real canary company/case (separate from Wave 4) |
| Recruiting `talent_pool` | Remains **candidate-only**; never renamed or aliased to post-hire Talent |
| Pre-hire assessment “calibration” | UI/docs must say **assessment norms**; Wave 4 owns **performance calibration** |

### 0.6 Out of scope for this charter

- Wave 5 executive KPI suite UI (Wave 4 **emits facts + definitions** only)
- Wave 6 L&D LMS / Benefits / ER / Engagement products (development **actions** may create tasks; full L&D catalog is Wave 6)
- Comp planning / merit cycles (Wave 6) — may **read** performance ratings later via OPTIONAL contract; not built here
- Treating OKRs as “generic goals renamed” (OKRs are first-class — see §0.8.1)
- Assistant mutations (unless separately chartered) — Wave 4 MVP = read / explain / deep-link / remind only
- Broad enable of Performance/Talent beyond named canaries without owner gates
- Shadow employee profiles, duplicate org trees, or per-module person IDs
- Enabling real termination as part of Wave 4 work
- Modeling Talent SoT as 9-box cell labels
- Silent AI writes of potential / HiPo / ratings / succession / employment decisions

### 0.7 Owner decisions (LOCKED 2026-08-12)

| # | Decision | Locked |
|---|---|---|
| 1 | Commercial module keys = **`performance`** + **`talent`** (distinct entitlements) | **Locked** |
| 2 | Assistant mutations = **OUT** of Wave 4 MVP (read / explain / deep-link / remind only) | **Locked** |
| 3 | 9-box default **OFF**; 9-box is a **view/projection**, never Talent SoT | **Locked** |
| 4 | Calibration may change **final** outcome; never erase original submitted ratings/rationale | **Locked** |
| 5 | Alignment scopes: company / department / team / individual; linked goals without forced rigid cascade | **Locked** |
| 6 | Serial slices C0–C7 and pass stamp names | **Locked** — see §17 |
| 7 | Canary posture: company-scoped flags; empty allowlist = nobody | **Locked** |
| 8 | Binding product locks §0.8 | **Locked** |

### 0.8 Binding product locks (owner 2026-08-12)

#### 0.8.1 OKRs are first-class — not generic goals renamed

Wathefni Performance **must** explicitly support:

- **Objectives**
- multiple **Key Results** per Objective
- measurable KR target / baseline / current value
- KR progress → Objective roll-up
- weights where configured
- company / department / team / individual alignment
- linked/aligned goals **without** forcing a rigid cascade
- versioned target changes with audit

Generic KPIs, milestone goals, and development goals may coexist, but OKRs have **their own canonical semantics**.

**Do not conflate:** Objective · Key Result · KPI · Competency · Development Action.

#### 0.8.2 KPI math must be defined, not decorative

Every measurable goal/KPI needs an explicit **calculation contract**:

| Field | Requirement |
|---|---|
| measure / unit | Required |
| baseline | Required (or explicit N/A for milestone type) |
| target | Required |
| direction | `higher_is_better` \| `lower_is_better` \| `target_range` \| `milestone` |
| source | `manual` \| `wathefni_canonical_fact` \| `integration` |
| progress calculation | Versioned formula — never free-typed dashboard % |
| weighting | Where configured |
| period | Required |
| owner | Canonical employee / org owner |

No arbitrary percentage typed into a dashboard pretending to be KPI progress. Unknown/missing current value → `not_started` / `unknown`, **not** 100%.

#### 0.8.3 Review cycles snapshot their rules

Once a review cycle launches, **snapshot**: template · competency framework/version · rating scale · weights · reviewer assignments · visibility/reveal rules.

Later Setup changes must **not** silently alter an in-flight or completed review.

Preserve separately: **self rating → manager rating → calibrated/final rating**.

Calibration may change the final outcome but must **never erase** the original submitted ratings or rationale.

#### 0.8.4 360 confidentiality must be real

When 360/multi-rater feedback is enabled:

- company-configurable anonymity
- **minimum respondent threshold** before anonymous aggregates are revealed
- confidential comments separately governed
- manager/HR permissions explicit

Do **not** create fake anonymity where a manager can trivially identify one respondent.

#### 0.8.5 Talent must NOT depend universally on Performance

Talent works independently. Performance outcomes are an **OPTIONAL** input.

Potential, readiness, skills, aspirations, and succession assessments can exist through their own governed evidence/process when Performance is disabled.

#### 0.8.6 9-box is a view, never the Talent source of truth

Do **not** model an employee as simply `box=top_right`.

Store canonical dimensions/evidence separately:

- performance evidence
- potential assessment
- readiness
- competencies / skills
- strengths
- development areas
- career aspirations / preferences
- mobility willingness (where employee-provided)
- succession nominations / readiness

Then 9-box is an **optional configurable projection** over selected performance × potential inputs.

Companies configure thresholds/scales. Changing a 9-box configuration must **not** rewrite historical talent assessments.

#### 0.8.7 Talent Mapping is workforce-intelligence — not a static 9-box

Architect the canonical model so Wathefni can dynamically answer (C1–C7 need not ship every intelligence feature now, but **must not trap Talent inside 9-box rows**):

- strongest successors for a critical role
- ready now / soon / later
- capability gaps blocking readiness
- employees with similar skills to a target role
- succession coverage gaps
- team concentrations/gaps in skills/potential
- development actions that would improve readiness
- evolution of performance / potential / readiness over time

#### 0.8.8 Succession is role-based and multi-successor

Support: critical role designation · succession plan per role/position · **multiple** successor candidates · readiness (`ready_now` / `<1y` / `1–2y` / `longer_term` or configurable equivalent) · development gaps/actions · nomination rationale · history.

Succession **must work without 9-box**.

#### 0.8.9 Development truth survives review cycles

Reviews/check-ins may create development actions/plans, but those become **durable canonical development records**.

A completed annual review must not bury all development commitments inside an old form.

Later L&D may optionally fulfill development actions through courses/programs **without** Performance depending on L&D.

#### 0.8.10 Internal mobility remains optional Recruiting integration

Talent may identify/recommend internal opportunities. Recruiting/Jobs may consume via OPTIONAL contract.

Do **not** create duplicate candidates/person identities — an internal applicant remains linked to the canonical employee/person.

#### 0.8.11 AI / intelligence boundary

Assistant mutations remain **OUT**.

Future AI recommendations may rank/explain successors, development gaps, mobility matches, talent patterns — but AI output must be **advisory + explainable**, never silently write potential, HiPo, final ratings, succession readiness, or employment decisions.

#### 0.8.12 Bias / confidentiality boundary

Talent/performance decisions are sensitive HR records.

Require explicit permissions for: raw 360 feedback · potential assessments · HiPo designation · succession plans · calibration.

Never infer protected/personal attributes as evidence for potential or talent decisions.

---

## 1. Exact scope

**Goal:** Managers and employees run **goals, continuous feedback, and review cycles** with durable ratings and development actions; HR can run **calibration and succession** without CV-keyword theater.

### 1.1 Serial core (customer-facing chain)

```text
OKRs (Objective + Key Results) + KPI / milestone / development goals
  → Explicit measure contracts + weighted progress (no decorative %)
  → Alignment links (company/dept/team/individual) without forced cascade
  → Check-ins / continuous feedback
  → Competencies / behaviors (optional capability)
  → Review cycles with rule snapshots (self → manager → calibrated/final)
  → Ratings / scoring + acknowledgements (+ real 360 confidentiality)
  → Calibration (when enabled; never erase originals)
  → Durable development actions (survive cycles)
  → Talent mapping dimensions (not 9-box SoT)
  → Optional 9-box projection + HiPo / critical roles / succession / pools
  → Internal mobility / opportunity matching (optional Recruiting link)
```

### 1.2 Workstreams

| ID | Workstream | Deliverable |
|---|---|---|
| W4.1 | OKR + Goal / KPI framework | First-class Objective/KR; coexisting KPI/milestone/development goals; measure contracts; alignment; versioned targets; progress engine |
| W4.2 | Review cycles | `review_cycle` authority; participant roster from org/manager scope; lock/close semantics |
| W4.3 | Reviews | Self / manager / additional reviewer / 360 (when configured); draft→submitted→acknowledged |
| W4.4 | Check-ins / continuous feedback | `check_in` + `feedback_note` linked to goals/employees; not a second review SoT |
| W4.5 | Competencies / behaviors | Company competency library; ratings on review or standalone competency assessment |
| W4.6 | Ratings / scoring | Owned scoring model (scale, weights, aggregation rules); immutable after cycle lock except via calibration |
| W4.7 | Calibration | Facilitated session; audited rating adjustments; distinct from assessment norms |
| W4.8 | Development actions | `development_action` / plan items → `hr_tasks`; arise from reviews/goals |
| W4.9 | Talent profile | Canonical post-hire `talent_profile` on person/employee — strengths, development areas, potential |
| W4.10 | Performance × potential / 9-box | Grid only when enabled + both axes present; HiPo identification rules company-owned |
| W4.11 | Succession | Critical roles, succession plans, successor readiness — **no HARD dep on 9-box** |
| W4.12 | Talent pools (post-hire) | Named pools distinct from recruiting `talent_pool` |
| W4.13 | Internal mobility | Opportunity matching; OPTIONAL link to Jobs/Recruiting internal apply |
| W4.14 | Surfaces + Setup | HR Web / HR Mobile / Employee App / Manager / Assistant (read-only MVP); Setup Wave 4 policies |
| W4.15 | Cross-cutting | EN/AR+RTL, RBAC/manager scope, confidentiality, Phase A approvals/tasks/SLA, analytics facts, canary flags, qualify/rollback |

### 1.3 Explicit non-goals

- Forcing Talent to require Performance ratings for all features  
- Forcing Goals to require Review cycles  
- Forcing Succession to require 9-box  
- Forcing Internal mobility to require Recruiting/Jobs modules  
- Shipping executive dashboards without Wave 5 `kpi_definition` registry  
- Renaming recruiting candidate pools to “Talent”  
- Marketing “complete HCM” after Wave 4 alone  

---

## 2. Starting posture (honest inventory)

Wave 4 is primarily **NEW** domain authority on top of stable org/manager scope:

| Area | Today (summary) | Wave 4 change |
|---|---|---|
| Performance | Missing as product domain | NEW module `performance` |
| Talent (post-hire) | Naming collision risk with recruiting `talent_pool` | NEW module `talent`; hard naming boundary |
| Pre-hire assessment | “Calibration” wording | UI/docs → **assessment norms**; do not overload |
| Org / manager scope | Waves 1–3 | Consume for roster, cascade, succession ownership |
| Phase A | Approvals + `hr_tasks` + SLA | Bind review/calibration/succession subjects — do not fork engines |
| Setup Console | Wave 1–3 cards | NEW Wave 4 policies card |
| Employee / HR mobile shells | Exist | EXTEND surfaces; no parallel apps |
| Analytics | Attention ops ≠ strategic KPIs | Emit Wave 4 facts for Wave 5 |

---

## 3. Dependency / capability contract matrix

### 3.1 HARD DEPENDENCY

| Consumer | Requires | Why |
|---|---|---|
| Goal create/assign | Canonical employee/employment (+ org unit for non-individual) | One person/org SoT |
| Review cycle launch | Company entitlement + org/manager roster source | Participants must be real employees |
| Manager review write | Manager scope ∩ cycle participants | No cross-tenant / out-of-scope writes |
| Calibration adjust | Existing review rating row in open calibration session | Adjustments are not free-floating scores |
| Succession successor link | Canonical employee_key (active or alumni per policy) | No shadow people |

### 3.2 OPTIONAL INTEGRATION (versioned contracts)

| Contract | Modules | Company setting (illustrative) | Behavior when enabled |
|---|---|---|---|
| `talent.consume_performance_ratings` | talent ↔ performance | `talent.use_performance_axis=true` | Talent grid/HiPo uses latest locked performance rating |
| `performance.goals_in_reviews` | performance internal | `review.include_goals=true` | Review form pulls active goals for period |
| `performance.competencies_in_reviews` | performance | `review.include_competencies=true` | Competency scores on review |
| `performance.workflow_approvals` | performance ↔ Phase A | `performance.approval_policy_id` | N-step for cycle open/close or rating exceptions |
| `talent.succession_from_9box` | talent | `talent.nine_box_enabled=true` | 9-box **enhances** succession nomination; succession still works if off |
| `mobility.internal_jobs` | talent ↔ pre_hiring/jobs | `talent.internal_mobility_jobs=true` | Opportunity matching can deep-link/create internal applications |
| `performance.development_tasks` | performance ↔ hr_tasks | always-on when development actions entitled | Actions create tasks + SLA |
| `comp_planning.read_ratings` | (Wave 6 later) | n/a in Wave 4 | Document future OPTIONAL only — not built |

### 3.3 ENHANCEMENT WHEN ENABLED

| Base | Enhancement | Effect |
|---|---|---|
| Goals | Review cycles | Period-aligned progress snapshots on review |
| Reviews | Calibration | Post-submit distribution governance |
| Talent profile | Performance | Prefill strengths/development from review narratives |
| Succession | 9-box / HiPo | Suggest successors from grid cells |
| Internal mobility | Recruiting/Jobs | Richer opportunity inventory |
| Check-ins | Goals | Progress % suggestions (still user-confirmed) |

### 3.4 Modularity proofs required

1. **Performance without Talent** — goals + cycle + ratings + development actions  
2. **Goals without review cycles** — CRUD + progress + check-ins only  
3. **Competencies without full cycle suite** — library + standalone ratings where configured  
4. **Talent without Performance** — profile + potential + succession + pools (performance axis blank/N/A)  
5. **Succession without 9-box** — critical roles + readiness + successors  
6. **Internal mobility without Jobs module** — opportunity notes/matching list only; Jobs contract off  
7. Disabled modules disappear cleanly from all surfaces  

---

## 4. Canonical entities and state machines

### 4.1 Reuse (do not duplicate)

- `employees` / employment / org assignments / manager scope  
- Phase A: `approval_instance`, `delegation_grant`, `hr_tasks`, SLA  
- Recruiting `talent_pool` (**candidates only** — never write post-hire talent here)  

### 4.2 Performance entities

#### `measure_definition` (versioned calculation contract)

Required for every measurable KR / KPI goal: measure/unit · baseline · target · direction · source · progress formula version · weight · period · owner.

Directions: `higher_is_better` \| `lower_is_better` \| `target_range` \| `milestone`.

Sources: `manual` \| `wathefni_canonical_fact` \| `integration`.

**No dashboard card / progress % without a measure contract** (Wave 5 will enforce globally; Wave 4 must already obey).

#### `objective` (OKR — first-class)

```text
draft → active → completed | cancelled | archived
```

- Scope: `individual` \| `team` \| `department` \| `company`  
- Owns one or more Key Results  
- Progress = weighted roll-up of KR progress (configured weights)  
- **Not** a renamed generic goal  

#### `key_result` (OKR)

```text
draft → active → completed | cancelled | archived
```

- Belongs to exactly one Objective  
- Has measure contract (target/baseline/current)  
- Target changes create **versioned audit rows**  
- Progress derived from measure engine — never free-typed % as SoT  

#### `goal` (non-OKR coexist types)

```text
draft → active → completed | cancelled | archived
```

| `goal_kind` | Notes |
|---|---|
| `kpi` | Measure-contract KPI (not an Objective/KR) |
| `milestone` | Direction `milestone`; binary/fraction complete |
| `development` | Development-oriented goal; may spawn durable `development_action` later |

Do **not** store Objectives or Key Results as `goal_kind=okr` shortcuts — use `objective` / `key_result` entities.

#### `alignment_link`

- Links objectives/goals across scopes (company↔dept↔team↔individual)  
- **Alignment ≠ forced cascade score inheritance**  
- Optional rollup only when company enables explicit rollup formula  

**Calculation semantics (locked):**

- Progress from measure engine only  
- Objective attainment = Σ(weight_kr × progress_kr) / Σ(weight_kr)  
- Missing current value → `not_started` / `unknown`, never silent 100%  
- Versioned target change does not rewrite historical progress facts

#### `check_in`

```text
scheduled | open → submitted → acknowledged (optional)
```

#### `feedback_note`

- Continuous feedback; visibility rules (private to manager/HR vs shared); not a rating SoT  

#### `competency` / `competency_rating`

- Library per company; rating on review or standalone assessment instance  

#### `review_cycle`

```text
draft → open → in_progress → calibration (optional) → locked → closed | cancelled
```

**On launch, snapshot (immutable for that cycle):** template · competency framework/version · rating scale · weights · reviewer assignments · visibility/reveal rules.

Later Setup edits must not silently alter in-flight or completed cycles.

**Review-cycle authority (sole writer of cycle phase):**

- HR (or entitled Performance Admin) opens / locks / closes  
- Managers/employees cannot advance cycle phase  
- Lock freezes ratings except through open calibration session  
- Close is terminal for scoring; amendments require audited reopen policy (default: forbidden)

#### `review` (per subject employee × cycle × reviewer role)

```text
not_started → draft → submitted → acknowledged | declined_ack
```

Roles: `self` | `manager` | `additional` | `peer` | `skip_level` | `subordinate` (360 matrix company-configured)

**360 confidentiality:** anonymity config · minimum respondent threshold before aggregate reveal · confidential comments separately governed · no fake anonymity with n=1 identification.

#### `rating_score` (layered — never collapse)

Preserve separately:

1. **self rating** (+ rationale)  
2. **manager rating** (+ rationale)  
3. **calibrated / final rating** (from calibration; optional)

Calibration may update final; **must never erase** original submitted ratings or rationale (append-only adjustment ledger).

#### `calibration_session`

```text
planned → open → finalized | cancelled
```

- Facilitator (HR) + participants (managers)  
- Produces `calibration_adjustment` audit rows (before/after, reason)  
- **Not** assessment norms  

#### `development_action` (durable — survives cycles)

```text
proposed → accepted → in_progress → done | cancelled
```

- Canonical development record — **not** buried only inside a completed review form  
- Links to review/goal/KR as source; creates `hr_tasks` when entitled  
- L&D fulfillment is OPTIONAL later — Performance does not depend on L&D  

### 4.3 Talent entities (dimension-first — not 9-box rows)

#### `talent_profile` (canonical, 1 per person/employee under company)

- strengths[], development_areas[], skills[], career_aspirations, mobility_willingness, notes, updated_by, row_version  
- Person key from canonical employee/person — **no shadow profile table of people**

#### `potential_assessment`

```text
draft → submitted → accepted | withdrawn
```

- Separate axis from performance rating; governed evidence/process even when Performance module off  

#### `readiness_assessment`

- Role- or general-readiness with gaps; feeds succession and Talent Mapping queries  

#### `nine_box_projection` (VIEW — optional)

- **Not** Talent SoT  
- Projection over selected performance evidence × potential assessment inputs + company thresholds  
- Changing 9-box config must **not** rewrite historical assessments  
- If either axis missing → projection unavailable (no decorative labels)

#### `hipo_designation`

```text
nominated → confirmed | rejected | expired
```

#### `critical_role`

- Role/position ref + criticality + succession coverage fields  

#### `succession_plan` / `successor_nomination` (multi-successor)

```text
draft → active → archived
```

- Multiple successors per plan  
- Readiness: `ready_now` \| `ready_lt_1y` \| `ready_1_2y` \| `longer_term` \| `not_ready` \| `unassessed` (or company-configured equivalent)  
- Nomination rationale + development gaps/actions + history  
- **Works without 9-box**

#### `talent_pool` (**POST-HIRE** — product name in UI: “Talent pool”; storage key must not collide)

- **Storage / API recommendation:** `performance_talent_pool` or `posthire_talent_pool` entity; UI label localized  
- Recruiting module key `talent_pool` remains candidates  
- Membership: employee_key + pool_id + reason + dates  

#### `mobility_opportunity` / `internal_interest`

```text
open → matched | applied_internal (optional) | closed
```

- Jobs link only when `mobility.internal_jobs` on  

---

## 5. Rating / scoring ownership

| Concern | Owner |
|---|---|
| Scale definition (e.g. 1–5, labels EN/AR) | Setup → Performance policy |
| Goal weight math | Performance goal engine |
| Competency aggregation | Performance competency engine |
| Overall review score composition | Company scoring policy version |
| Final score after calibration | Calibration session finalize (audited) |
| What Talent reads | Latest **locked** (or calibrated) overall score via OPTIONAL contract |
| What Wave 5 reads | Emitted facts + definition ids — no ad-hoc SQL cards |

Managers draft; HR/calibration may adjust under policy; employees acknowledge but do not unilaterally change scores.

---

## 6. Calibration authority

| Rule | Requirement |
|---|---|
| Who opens | Performance Admin / HR with `calibration.facilitate` |
| Who proposes | Managers in session scope |
| Who finalizes | Facilitator (or dual-control if Setup requires) |
| What changes | Append-only adjustments to `rating_score` with reason |
| What does not | Bulk silent rewrites; employee self-calibration; assessment-norm templates |
| Confidentiality | Distribution charts need-to-know; employee sees own post-ack outcome per policy |
| Cycle interaction | Only in `review_cycle.calibration` (or explicit calibration window); not after `closed` without reopen policy |

---

## 7. Module catalog / Setup Console

### 7.1 Commercial modules

| module_key | Wave 4 Setup ownership |
|---|---|
| `performance` | Goals, cycles, reviews, check-ins, competencies, scoring, calibration, development actions |
| `talent` | Talent profile, potential, 9-box, HiPo, succession, post-hire pools, mobility |
| `pre_hiring` / jobs | **Read-only OPTIONAL** consumer for internal mobility — do not reopen recruiting freezes |
| Recruiting `talent_pool` | Unchanged candidate pool — Setup must show distinct labels EN/AR |

### 7.2 Company settings (illustrative)

| Setting | Default | Notes |
|---|---|---|
| `performance.enabled` | false | |
| `performance.goals_enabled` | true when module on | Can disable cycles independently |
| `performance.cycles_enabled` | false | Goals-only tenants allowed |
| `performance.competencies_enabled` | false | Independent capability |
| `performance.checkins_enabled` | false | |
| `performance.additional_reviewers_enabled` | false | |
| `performance.review_360_enabled` | false | |
| `performance.calibration_enabled` | false | |
| `performance.scoring_policy_id` | null | Versioned |
| `performance.goal_scopes` | individual | + team/dept/company opt-in |
| `talent.enabled` | false | |
| `talent.use_performance_axis` | false | OPTIONAL INTEGRATION |
| `talent.nine_box_enabled` | false | Requires both axes when on |
| `talent.succession_enabled` | false | No 9-box requirement |
| `talent.pools_enabled` | false | Post-hire pools |
| `talent.internal_mobility_jobs` | false | OPTIONAL Jobs link |
| `talent.hipo_policy_id` | null | |

Setup Console owns these policies (not env-only). Runtime flags remain fail-closed canary gates.

---

## 8. RBAC / confidentiality / roles

| Role | Typical powers |
|---|---|
| Employee | Own goals (where allowed); self-review; view own ratings after release/ack policy; own development actions; maintain self-reported strengths (policy) |
| Manager | Goals for reports; manager reviews; check-ins; nominate successors for owned critical roles; view team distribution per policy |
| Additional reviewer | Assigned reviews only |
| HR / Performance Admin | Templates, cycles, calibration, scoring policies, exceptions |
| Talent Admin | Profiles, HiPo, pools, succession coverage, critical roles |
| Assistant | Read/explain/deep-link/remind only (MVP) |

| Confidentiality boundary | Rule |
|---|---|
| Peer/360 feedback | Configurable anonymity; raw peer text may be HR-only |
| Calibration discussions | HR + session participants; not employee-visible |
| HiPo / succession | Need-to-know; default hidden from subject employee |
| Potential assessments | Manager/HR; employee visibility company-policy |
| Compensation-linked notes | Never leak into employee-visible review narrative without policy |

SoD: employee cannot be final approver of own overall rating exception; calibration facilitator ≠ sole unaudited writer without reason codes.

Manager scope: all manager mutations ∩ org scope SQL (reuse Waves 1–3). Tenant isolation on every entity.

---

## 9. Workflows by persona

### 9.1 HR Web

- Goal/KPI template library; cycle launch/monitor/lock  
- Review completion dashboards (operational, not fake executive KPIs)  
- Calibration workspace  
- Competency library  
- Talent profiles, 9-box (if on), HiPo, critical roles, succession coverage  
- Post-hire talent pools; mobility board  

### 9.2 Manager (Web + HR Mobile)

- Team goals / progress  
- Review queue; check-ins  
- Nominate successors; view team talent signals per permission  
- Cannot calibrate alone unless entitled  

### 9.3 Employee App

- My goals + check-ins  
- Self-review + acknowledgements  
- Development actions  
- Limited talent self-profile fields per policy  

### 9.4 Assistant

- Wave 4 MVP **recommend OUT** for mutations  
- Read / explain / deep-link / remind (due reviews, goal deadlines)  
- Must not invent scores, grid cells, or succession state  

---

## 10. Surfaces matrix

| Capability | HR Web | HR Mobile | Employee App | Manager | Assistant |
|---|---|---|---|---|---|
| Goals / KPIs | Strong | Thin/Strong | Strong | Strong | Read/Remind |
| Check-ins / feedback | Strong | Thin | Thin/Strong | Strong | Remind |
| Competencies | Strong | Thin | Thin | Thin | Read |
| Review cycles | Strong | Thin queue | Self | Strong | Remind |
| Ratings / ack | Strong | Thin | Strong | Strong | Read |
| Calibration | Strong | — | — | Thin participate | — |
| Development actions | Strong | Thin | Strong | Strong | Remind |
| Talent profile | Strong | Thin | Thin (self) | Thin | Read |
| 9-box / HiPo | Strong | Thin | — | Thin | Read |
| Succession | Strong | Thin | — | Thin nominate | Read |
| Post-hire talent pools | Strong | — | — | — | Read |
| Internal mobility | Strong | Thin | Thin interest | Thin refer | Deep-link |

---

## 11. EN / AR + RTL

- All goal titles, competency names, rating labels, cycle names, pool names ship EN+AR  
- Review forms and acknowledgements RTL-safe  
- 9-box axis labels bilingual; no English-only grid  
- Setup policy labels bilingual (mirror Wave 2/3 Setup cards)  

---

## 12. Approvals, tasks, SLA (reuse Phase A)

| Subject | Task / approval |
|---|---|
| `review_self_due` / `review_manager_due` | Employee/manager tasks + SLA |
| `review_additional_due` | Additional reviewer |
| `review_ack_required` | Employee acknowledgement |
| `calibration_session_open` | Facilitator + participants |
| `goal_checkin_due` | Optional |
| `development_action_open` | Owner task |
| `succession_nomination_pending` | HR/manager |
| `hipo_confirmation` | Talent Admin |
| `cycle_lock_approval` | Optional N-step |

One inbox SoT: `hr_tasks`. No parallel “Performance inbox” database.

---

## 13. Analytics / audit facts (Wave 5 prep)

Emit append-only facts with definition references where numeric:

| Fact | Payload (min) |
|---|---|
| `goal_activated` / `goal_progress_recorded` | goal_id, scope, progress_pct, kpi_definition_id? |
| `goal_attainment_computed` | subject_id, period, weighted_pct, formula_version |
| `review_cycle_opened` / `locked` / `closed` | cycle_id |
| `review_submitted` | review_id, role |
| `review_acknowledged` | review_id |
| `rating_finalized` | employee_key, cycle_id, overall_score, scoring_policy_version |
| `calibration_adjustment_applied` | rating_id, before, after, reason |
| `competency_rated` | competency_id, score |
| `development_action_created` | action_id, source_review_id |
| `talent_profile_updated` | person_key |
| `potential_assessed` | employee_key, level |
| `talent_grid_placed` | employee_key, x, y, cycle_id |
| `hipo_confirmed` | employee_key |
| `critical_role_defined` | role_id |
| `successor_nominated` | role_id, successor_employee_key, readiness |
| `succession_coverage_computed` | role_id, coverage_pct, formula_version |
| `posthire_pool_membership_changed` | pool_id, employee_key |
| `mobility_interest_submitted` | opportunity_id, employee_key |

**Wave 5 KPI inputs (must be computable):** goal attainment distribution; performance rating distribution; HiPo count; succession coverage %.

Every transition: actor, before/after, company_code, reason where required.

---

## 14. Migrations

| From | To | Rule |
|---|---|---|
| Ad-hoc notes / spreadsheets | Not auto-imported | Optional admin import with explicit mapping + audit |
| Pre-hire assessment frameworks | Competency library | Explicit mapping only; never silent overload of NBK/pre-hire framework |
| Recruiting `talent_pool` members | Post-hire pools | **Forbidden automatic copy** — different populations |
| Org manager assignments | Review rosters | Snapshot at cycle open; later org moves do not silently rewrite submitted reviews |
| Historical reviews (if any) | `review` rows | Attach as imported + labeled; do not invent scores |

---

## 15. Rollout flags (fail-closed)

Pattern: `WATHEFNI_<FEATURE>[_C#]` + `_COMPANIES` (empty = nobody) + optional `_KILL`.

| Flag (proposed) | Default | Notes |
|---|---|---|
| `WATHEFNI_PERFORMANCE_GOALS_C1` | off | Goals/KPIs |
| `WATHEFNI_PERFORMANCE_REVIEWS_C2` | off | Cycles + self/manager reviews |
| `WATHEFNI_PERFORMANCE_FEEDBACK_C3` | off | Check-ins / continuous feedback / competencies slice |
| `WATHEFNI_PERFORMANCE_CALIBRATION_C4` | off | Calibration + scoring lock semantics |
| `WATHEFNI_TALENT_PROFILE_C5` | off | Profile + potential (+ optional consume performance) |
| `WATHEFNI_TALENT_SUCCESSION_C6` | off | Critical roles / succession / pools / HiPo / optional 9-box |
| `WATHEFNI_PERFORMANCE_TALENT_PRODUCT_C7` | off | Product acceptance + modularity matrix |
| Per-slice `_COMPANIES` | empty | Nobody until canary listed |
| `WATHEFNI_PERFORMANCE_KILL` | off | Immediate block on new cycle opens / rating writes when on |
| `WATHEFNI_TALENT_KILL` | off | Immediate block on succession/HiPo writes when on |

Production systemd must **not** globally enable these. Process-scoped prove only until owner unlock.

---

## 16. Freeze amendments (required before/with slices)

| Prior freeze / surface | Wave 4 amendment intent |
|---|---|
| `ops/WAVE3_PRODUCT_FREEZE.md` | Wave 4 owns Performance/Talent; Wave 3 stays frozen; real termination untouched |
| `ops/WAVE2_PRODUCT_FREEZE.md` / Wave 1 freeze | Do not reopen |
| Recruiting / pre-hire freezes | Naming boundary: candidate `talent_pool` ≠ post-hire talent; assessment norms rename if not done |
| Assessment UI copy | “Calibration” → “Assessment norms” where still present |
| Module catalog | Register `performance` + `talent` entitlements |

Each slice ships: qualify script + evidence + `*_FULL_PASS` stamp + freeze amendment. Stop for owner review between slices.

---

## 17. Serial build order + safe parallelism

| Phase | Focus | Exit stamp |
|---|---|---|
| **C0** | Charter review + binding locks §0.8 | **APPROVED** — `WAVE4_PERFORMANCE_TALENT_CHARTER: APPROVED` |
| **C1** | OKR (Objective+KR) + KPI/milestone/development goals; measure contracts; alignment; versioned targets | **ACCEPTED / FROZEN** `PERFORMANCE_GOALS_FULL_PASS` · evidence `ops/evidence/performance-goals-c1-20260811T215044Z` |
| **C2** | Review cycles + self/manager/360 + ratings + snapshots | **ACCEPTED / FROZEN** `PERFORMANCE_REVIEWS_FULL_PASS` · evidence `ops/evidence/performance-reviews-c2-20260812T063543Z` |
| **C3** | Check-ins / continuous feedback + competencies + durable development | **ACCEPTED / FROZEN** `PERFORMANCE_FEEDBACK_COMPETENCIES_FULL_PASS` · evidence `ops/evidence/performance-feedback-c3-20260812T064217Z` |
| **C4** | Ratings aggregation + calibration authority | **ACCEPTED / FROZEN** `PERFORMANCE_CALIBRATION_DEV_FULL_PASS` · evidence `ops/evidence/performance-calibration-c4-20260812T080424Z` |
| **C5** | Talent profile + potential + optional Performance consume | **ACCEPTED / FROZEN** `TALENT_PROFILE_FULL_PASS` · evidence `ops/evidence/talent-profile-c5-20260812T081339Z` |
| **C6** | Critical roles, succession, HiPo, optional 9-box, Talent Review | **ACCEPTED / FROZEN** `TALENT_SUCCESSION_MOBILITY_FULL_PASS` · evidence `ops/evidence/talent-succession-c6-20260812T081940Z` |
| **C7** | Surfaces + Setup + modularity matrix + full synthetic prove → product acceptance | **ACCEPTED / FROZEN** `WAVE4_PRODUCT_FULL_PASS` · evidence `ops/evidence/wave4-product-acceptance-20260812T083316Z` |

**Synthetic journey (must be green before broad Performance/Talent enable):**  
`OKRs+KPI goals → check-ins → cycle open (snapshot rules) → self+manager (+optional 360 with real anonymity) → ack → calibration (if on; originals preserved) → durable development actions → talent dimensions/potential/readiness → succession multi-successor (without 9-box) → optional 9-box projection/HiPo → optional mobility`

**Parallelism (safe):**

- C3 feedback/competencies may overlap late C2 after review entity stable  
- C5 Talent profile may start after C1 goals stable **without** waiting for calibration, if Performance-consume contract defaults off  
- C6 succession may proceed without 9-box; 9-box lands when C5 axes exist  
- **C4 calibration is critical path before claiming rating finality for Talent consume**  
- C7 only after C1–C6 accepted  

---

## 18. Acceptance tests (charter-level)

| ID | Test |
|---|---|
| W4-G01 | First-class Objective + ≥2 weighted KRs; KR progress → Objective roll-up; missing current ≠ 100% |
| W4-G02 | Measure contracts required; decorative free-typed progress % rejected |
| W4-G03 | KPI / milestone / development goals coexist; OKR not stored as goal_kind |
| W4-G04 | Alignment links without forced cascade / score inheritance |
| W4-G05 | Versioned target changes audited; scopes individual/team/dept/company |
| W4-G06 | Goals/OKRs work with cycles **disabled** and Talent **disabled** |
| W4-R01 | Cycle open snapshots roster from manager scope; self+manager review path |
| W4-R02 | Additional/360 reviewers only when configured; otherwise hidden |
| W4-R03 | Acknowledgement distinct from submission; decline-ack audited |
| W4-C01 | Check-ins + continuous feedback do not overwrite review scores |
| W4-K01 | Competencies enable independently; scores durable |
| W4-S01 | Scoring policy version applied; unknown progress ≠ 100% |
| W4-S02 | Cycle lock freezes scores; calibration adjustments append-only with reason |
| W4-S03 | Calibration ≠ assessment norms (copy + code paths distinct) |
| W4-D01 | Development actions create tasks; complete without Talent module |
| W4-T01 | Talent profile on canonical person; no shadow employee |
| W4-T02 | Talent works with Performance contract **off** (potential/succession still usable) |
| W4-T03 | 9-box forbidden unless both axes present and feature enabled |
| W4-T04 | HiPo rules company-owned; not free-text-only labels |
| W4-U01 | Succession without 9-box; coverage % computable |
| W4-U02 | Post-hire pool ≠ recruiting candidate talent_pool (API + UI) |
| W4-U03 | Internal mobility works without Jobs; Jobs link optional |
| W4-M01 | Modularity matrix: Performance-only; Goals-only; Talent-only; Succession-without-9box; full suite; all disabled |
| W4-X01 | EN/AR+RTL + tenant isolation + manager scope + confidentiality |
| W4-X02 | Assistant does not invent scores/grid/succession state |
| W4-X03 | No fake KPI card without definition/formula |

---

## 19. Wave 4 acceptance gate (roadmap §6.2 + modularity)

- [ ] At least one full review cycle completed in entitled company (self+manager)  
- [ ] Goals active for managers’ reports; Employee App + manager mobile parity for core actions  
- [ ] Calibration session audited when enabled; assessment “norms” rename shipped  
- [ ] Development actions durable from reviews  
- [ ] Talent profile + succession coverage inputs exist for Wave 5  
- [ ] 9-box only with canonical axes; off by default  
- [ ] No naming collision: Talent ≠ recruiting talent pool  
- [ ] Performance without Talent proven; Talent without Performance proven  
- [ ] Goals without cycles proven; succession without 9-box proven  
- [ ] Setup owns Wave 4 policies (not env-only)  
- [ ] Wave 1–3 freezes regress green; real termination still off  

---

## 20. Rollback

```text
WATHEFNI_PERFORMANCE_KILL=on     # block new cycle opens / rating writes
WATHEFNI_TALENT_KILL=on          # block succession/HiPo/pool writes
WATHEFNI_*_C#=off                # per-slice runtime off
Clear corresponding *_COMPANIES
Disable company Setup entitlements (performance / talent)
In-flight cycles: remain auditable; no silent purge of ratings
Locked ratings + calibration adjustments: immutable history retained
```

Per-slice rollback guidance required in each freeze amendment.

---

## 21. Owner review checklist (LOCKED 2026-08-12)

| # | Decision | Status |
|---|---|---|
| 1 | Serial phases C0–C7 and pass stamp names | **Locked** — see §17 |
| 2 | Module keys `performance` + `talent` | **Locked** |
| 3 | Assistant mutations OUT for Wave 4 MVP | **Locked** |
| 4 | OKRs first-class; KPI math contracts; no decorative % | **Locked** — §0.8.1–0.8.2 |
| 5 | Cycle rule snapshots; self→manager→final; calibration never erases originals | **Locked** — §0.8.3 |
| 6 | Real 360 confidentiality (threshold anonymity) | **Locked** — §0.8.4 |
| 7 | Talent independent of Performance; 9-box is view-only; Talent Mapping dimension-first | **Locked** — §0.8.5–0.8.7 |
| 8 | Succession multi-successor without 9-box; durable development truth | **Locked** — §0.8.8–0.8.9 |
| 9 | Optional Recruiting mobility; AI advisory-only; bias/confidentiality | **Locked** — §0.8.10–0.8.12 |
| 10 | Canary-only flags; Wave 3 frozen; real termination locked | **Locked** |

```text
WAVE4_PERFORMANCE_TALENT_CHARTER: APPROVED
date: 2026-08-12
signer: owner
binding_locks: §0.8
```

Implementation proceeds slice-by-slice (**C1 OKR/Goals/KPI first**). Stop after each `*_FULL_PASS` for review before the next slice.

---

## 22. Related documents

| Doc | Role |
|---|---|
| `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` | Parent execution authority (§6) |
| `ops/WATHEFNI_HCM_WAVE3_EMPLOYEE_LIFECYCLE_BUILD_CHARTER.md` | Prior charter (Wave 3 frozen) |
| `ops/WAVE3_PRODUCT_FULL_PASS.md` / `WAVE3_PRODUCT_FREEZE.md` | Wave 3 acceptance + freeze |
| `ops/WAVE2_PRODUCT_FREEZE.md` / `ops/WAVE1_PRODUCT_FREEZE.md` | Prior freezes |
| Recruiting / assessment product docs | Naming boundaries (`talent_pool`, assessment norms) |
