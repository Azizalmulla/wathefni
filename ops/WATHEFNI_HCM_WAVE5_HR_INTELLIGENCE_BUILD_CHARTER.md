# Wave 5 — HR Intelligence Build Charter

**Status:** APPROVED — `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED` (owner 2026-08-12; binding locks §0.7–§0.8)  
**Execution authority parent:** `ops/WATHEFNI_HCM_EXECUTION_ROADMAP.md` §7  
**Prior gate:** `WAVE4_PRODUCT_FULL_PASS` **ACCEPTED** 2026-08-12 — Wave 4 remains frozen (`ops/WAVE4_PRODUCT_FREEZE.md`)  
**Wave 3 freeze:** `WAVE3_PRODUCT_FULL_PASS` ACCEPTED — Employee Lifecycle remains frozen  
**Wave 2 freeze:** `WAVE2_PRODUCT_FULL_PASS` ACCEPTED — Workforce Truth remains frozen  
**Wave 1 freeze:** `WAVE1_PRODUCT_FULL_PASS` ACCEPTED — Hire→Ready remains frozen (WATHEFNI-canary)  
**Audit SoT:** 111-capability HCM gap audit + roadmap §7  
**Charter date:** 2026-08-12 · **Approved:** 2026-08-12  
**Scope:** Wave 5 — HR Intelligence (KPI Registry → fact spine → workforce/lifecycle/recruiting/time/payroll/performance/talent metrics → segmentation/trends/drill/export → surfaces)  
**Implementation gate:** Open for **C1 KPI Registry + Intelligence fact/query spine only**; stop after each C-slice stamp for owner review. Binding locks §0.7–§0.8 in force.

---

## 0. Charter principles (non-negotiable)

### 0.1 Product honesty

Wave 5 builds Wathefni’s **canonical HR intelligence layer** over facts already produced by Waves 1–4.

The system must answer:

> **What does this number mean, exactly where did it come from, who is included, how was it calculated, and can I drill back to the underlying authorized records?**

This is **not** a dashboard-card project. No metric exists merely because someone wants a KPI tile.

| Forbidden | Required instead |
|---|---|
| KPI tiles without published definitions | Versioned KPI Registry entry before any production card |
| Decorative percentages / demo numbers | Deterministic calculation from canonical facts |
| Shadow employee / payroll / performance / talent truth | Consume domain SoT; analytics owns definitions/query only |
| Vague `headcount = employees.count()` | Explicit heads/FTE + inclusion/exclusion + as-of semantics |
| Silent `0%` when undefined | Explicit `not_applicable` / `insufficient_data` (or governed equivalent) |
| Universal `employee_score` / `talent_score` / opaque ranking | Decision-specific governed metrics only |
| AI-invented metrics | Assistant explains Registry KPIs only; refuses undefined metrics |
| Mixing ops queues into strategic analytics | Attention/work queues ≠ HR Intelligence |

Every published metric must have:

`definition → canonical facts → calculation → time semantics → segmentation → permissions → trend → drill-down → export`

### 0.2 Modularity (same as Waves 1–4)

| Rule | Requirement |
|---|---|
| KPI enablement independent | Company may publish a subset of Registry KPIs |
| Domain-off honesty | If source domain/module is off or facts insufficient → metric **unavailable**, not faked |
| Clean disappearance | Disabled analytics / unpublished KPIs vanish — no empty Intelligence shells |
| Ops vs Intelligence | Operational attention (“12 leave requests need action”) stays separate from Intelligence (“leave utilization 64%”) |
| Commercial key | Platform module key = **`analytics`** (no duplicate); internal namespace **`hr_intelligence`** allowed; domain modules remain their own entitlements |
| No reopen | Do **not** reopen Waves 1–4 for analytics convenience / safe debt |

### 0.3 Dependency classes

| Class | Definition |
|---|---|
| **HARD DEPENDENCY** | KPI/slice cannot publish without named domain authority + fact contract |
| **OPTIONAL INTEGRATION** | KPI works from core facts; optional domain improves richness when enabled |
| **ENHANCEMENT WHEN ENABLED** | Core Intelligence works; extra dimensions/facts enrich when present |

### 0.4 Dynamic navigation

Runtime nav = `enabled company modules ∩ published KPIs ∩ permission grants ∩ surface capability matrix`.  
Zero visible Intelligence children → omit the group entirely (no empty Analytics shell).

### 0.5 Prior freeze boundaries (do not reopen)

| Freeze | Rule for Wave 5 |
|---|---|
| Wave 1 Hire→Ready | Consume facts only; do not reopen |
| Wave 2 Workforce Truth | Consume attendance/leave/shifts/payroll facts; money KPIs require authoritative payroll |
| Wave 3 Employee Lifecycle | Consume lifecycle/exit facts; real termination remains locked |
| Wave 4 Performance + Talent | Consume emitted facts/decisions only; never infer HiPo/succession/potential |
| Recruiting `talent_pool` | Remains candidate-only; never confused with post-hire Talent population KPIs |
| Real termination | `WATHEFNI_REAL_TERMINATION_CANARY=off` until separate owner unlock |

### 0.6 Out of scope for this charter

- Wave 6 L&D / Benefits / ER / Engagement / Comp planning products (may emit facts later via OPTIONAL contracts)
- Building a full data warehouse / lakehouse as a prerequisite for mid-market tenants
- Replacing Attention / Inbox operational triage with KPI cards
- Comp planning merit worksheets, workforce planning cost scenarios (Wave 6)
- Assistant mutations / AI writing KPI definitions or inventing numbers
- Broad enable of Intelligence beyond named canaries without owner gates
- Silent AI potential / HiPo / ranking / “employee health score”
- Reconstructing Talent decisions from Performance/9-box/skills
- Publishing FTE as if `1 head = 1 FTE` without authoritative FTE/standard-hours inputs
- Recurring scheduled-report delivery as a C6 HARD requirement (architecture-compatible only; may remain post-Wave-5 safe debt)

### 0.7 Owner decisions (LOCKED 2026-08-12)

| # | Decision | Locked |
|---|---|---|
| 1 | Commercial module key = **`analytics`**; internal Wave 5 namespace may use **`hr_intelligence`** — **no duplicate commercial module** | **Locked** |
| 2 | Assistant mutations = **OUT** of Wave 5 MVP (explain/query governed metrics only) | **Locked** |
| 3 | Serial stamps: C1 `HR_INTELLIGENCE_REGISTRY_FULL_PASS` · C2 `HR_INTELLIGENCE_WORKFORCE_FULL_PASS` · C3 `HR_INTELLIGENCE_RECRUITING_FULL_PASS` · C4 `HR_INTELLIGENCE_TIME_PAY_FULL_PASS` · C5 `HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS` · C6 `HR_INTELLIGENCE_SURFACES_FULL_PASS` · C7 `WAVE5_PRODUCT_FULL_PASS` | **Locked** |
| 4 | Canary posture: company-scoped flags; empty allowlist = nobody | **Locked** |
| 5 | Binding product locks §0.8 (incl. headcount / FTE / demographics / cohort) | **Locked** |
| 6 | Sensitive aggregate default **`min_cohort_n = 5`**, configurable **upward only**; complementary suppression required | **Locked** |
| 7 | Headcount: **`pending_start` excluded** (separate future-starters metric); notice-period **included until effective LWD/end**; active on leave/suspension **included** unless employment ended; contingent **not** silently mixed into employee headcount | **Locked** |
| 8 | **FTE not publishable** until authoritative FTE/standard-hours inputs exist; architecture may support FTE now but metric stays **blocked** (never assume 1 head = 1 FTE) | **Locked** |
| 9 | Demographic segmentation **off by default**; nationality may be explicitly enabled for legitimate KW workforce/compliance; other sensitive demographics require explicit policy/permission; **never** Talent/Performance scoring inputs | **Locked** |
| 10 | Attention Wave 1 retention: keep as **Ops Attention**, never rebrand as Intelligence | **Locked** |
| 11 | C6: on-demand exports + saved reportable views via shared evaluator; scheduled-report architecture compatible; recurring delivery may remain post-Wave-5 safe debt unless existing scheduler/channel reuse needs no scope expansion | **Locked** |
| 12 | Fiscal/reporting calendar ownership = Setup-owned | **Locked** |

### 0.8 Binding product locks (owner 2026-08-12)

#### 0.8.1 Versioned KPI Registry is the authority

Every governed KPI has a canonical versioned definition (`kpi_definition_id` + semantic key + effective version).  
**No production KPI card without a published Registry definition.**  
Editing a definition **versions** it; it must not silently rewrite historical reported meaning.

#### 0.8.2 Domain modules remain source of truth

Analytics owns **definitions / query / intelligence**, not operational business truth.  
May materialize/query facts for performance — domain SoT stays with owning modules.  
Commercial entitlement key remains **`analytics`**; code/tables may use `hr_intelligence_*` namespace without a second commercial module.

#### 0.8.3 Headcount semantics (binding)

No vague `employees.count()`. Binding inclusion rules for employee headcount (heads):

| Population | Headcount? | Notes |
|---|---|---|
| Active employees at as-of | **In** | Point-in-time reconstruction |
| `pending_start` / future starters | **Out** of headcount | Represented by a **separate** future-starters metric |
| Notice-period employees | **In** until effective last working day / end date | Drop after LWD/end |
| Active on leave / suspension | **In** | Unless canonical employment has ended |
| Terminated / left | **Out** after effective end | |
| Contingent / non-employee workers | **Out** of employee headcount | Never silently mixed; separate metric if introduced later |
| FTE | **Blocked** until authoritative FTE/standard-hours inputs exist | Architecture may reserve contracts; **never** publish as 1 head = 1 FTE |

Historical headcount reconstructs the workforce **as of the requested date**.

#### 0.8.4 Rates require honest denominators

Turnover, retention, absenteeism, lateness, offer acceptance, onboarding completion, succession coverage, etc. must define denominator/cohort/window.  
Zero-denominator → `not_applicable` / `insufficient_data` (never silent `0%`).

#### 0.8.5 Time is first-class

Distinguish point-in-time, event count, period sum/average, rate-over-window, cohort, rolling window.  
Later org/policy/KPI-definition changes must not silently change what a historical report meant.

#### 0.8.6 Segmentation uses canonical dimensions

Reusable dimensional/query contract — not per-KPI bespoke filter islands.  
Demographics **off by default**; nationality enablement is explicit KW-compliance path only; other sensitive demographics need explicit policy/permission; never scoring inputs for Talent/Performance.

#### 0.8.7 Drill-down is mandatory

Authorized viewers must resolve included population (and for rates: numerator, denominator, period, filters, definition version).

#### 0.8.8 Permission propagation + small-group protection

Analytics never weakens domain permissions.  
Sensitive aggregates: default **`min_cohort_n = 5`**, companies may raise (not lower) the threshold; complementary suppression/redaction required so aggregates cannot trivially expose individuals.

#### 0.8.9 Payroll/money honesty

No workforce-cost / payroll-movement KPI from draft, synthetic, preview-only, or unfinalized payroll. Fail closed when authoritative payroll unavailable.

#### 0.8.10 Performance + Talent confidentiality

Consume Wave 4 canonical outputs only. Never infer HiPo from performance or 9-box; never invent successors from skills.

#### 0.8.11 No universal employee score

Forbidden: `employee_score`, `workforce_score`, `talent_score`, opaque ranking master number.

#### 0.8.12 AI boundary

Assistant: read / explain / summarize / deep-link / compare **governed** metrics under permissions.  
**Never invent numerical metrics outside the KPI Registry.**

#### 0.8.13 Exports / scheduled reports

C6 provides on-demand exports and saved reportable views using the **shared KPI evaluator**.  
Scheduled-report architecture must remain compatible with the same authority; recurring delivery may stay post-Wave-5 safe debt unless existing scheduler/channel infrastructure can be reused without scope expansion.

---

## 1. Exact scope

**Goal:** Governed HR Intelligence that is definitionally honest, temporally reproducible, permission-safe, and drillable — for entitled companies only.

### 1.1 Serial product chain

```text
Domain facts (Waves 1–4 + platform)
  → Fact contracts / ingestion / projections
  → KPI Registry (versioned definitions)
  → Query spine (evaluate + segment + trend)
  → Drill-down population resolution
  → Surfaces (HR Web primary; Mobile thin; Assistant explain)
  → Export / report (same authority as UI)
  → Setup policies + modularity + product acceptance
```

### 1.2 Workstreams

| ID | Workstream | Deliverable |
|---|---|---|
| W5.1 | KPI Registry | Versioned definitions; publish/retire; bilingual meaning; no card without `kpi_definition_id` |
| W5.2 | Fact spine | Typed domain fact contracts; event/effective time; idempotent ingest; corrections |
| W5.3 | Query spine | Deterministic evaluation; as-of/period; segmentation; caching/materialization policy |
| W5.4 | Workforce / lifecycle KPIs | Headcount/FTE/hires/exits/turnover/retention/tenure/span |
| W5.5 | Recruiting / Hire→Ready KPIs | Time-to-fill/hire, offer accept, source effectiveness, onboarding/probation |
| W5.6 | Time / Leave / Payroll KPIs | Attendance/absenteeism/lateness/OT/leave util; money only when authoritative |
| W5.7 | Performance / Talent KPIs | Goal attainment, distributions, HiPo/succession coverage facts — explicit only |
| W5.8 | Platform ops KPIs | Workflow SLA, approval aging, task aging/completion |
| W5.9 | Drill / trend / export | Population lists; trends; CSV/PDF same formula authority; metadata retained |
| W5.10 | Surfaces + Setup | HR Web Intelligence; HR Mobile summaries; Assistant explain; Setup policies |
| W5.11 | Cross-cutting | EN/AR+RTL, RBAC/manager scope, small-group suppression, flags, qualify/rollback |

### 1.3 Explicit non-goals

- Shipping Intelligence UI before Registry + calculation authority exist
- Forcing every listed KPI to publish in C2 if facts are insufficient (mark blocked/deferred honestly)
- Enterprise BI studio on HR Mobile / Employee App
- Employee App company-wide analytics
- Hard-wiring Attention triage into Intelligence Overview
- Reopening frozen domain modules to “make analytics easier”
- Premature warehouse complexity for 30-person tenants
- Fake/demo hardcoded KPI numbers in production paths

---

## 2. Proposed architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│ Surfaces                                                         │
│  HR Web Intelligence │ HR Mobile summaries │ Assistant explain │
│  Exports/Reports (same evaluator) │ Channels (delivery only)   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│ KPI Registry (authority)                                         │
│  kpi_definition (versioned) · publication · permission class     │
│  bilingual meaning · formula contract · time · dimensions        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│ Query / Evaluation Spine                                         │
│  resolve definition@version → facts → calculate → segment        │
│  trend · drill population · undefined semantics · freshness      │
│  small-group suppression · manager scope filter                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│ Fact / Projection Layer                                          │
│  typed fact contracts · incremental refresh · snapshots          │
│  live query OR indexed projection OR matview (by scale/KPI)      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│ Domain SoT (unchanged ownership)                                 │
│  Recruiting · Requisitions · Offers/Hire · Preboard/Onboard      │
│  Employment/Org · Attendance · Leave · Shifts · Payroll          │
│  Lifecycle · Performance · Talent · Tasks/Approvals/SLA          │
└─────────────────────────────────────────────────────────────────┘
```

**Principle:** Dashboard requests never invent formulas. UI and export call the **same evaluator** with the same `kpi_definition_id` + version + filters + time window.

---

## 3. Canonical entities / contracts

| Entity | Owner | Purpose |
|---|---|---|
| `kpi_definition` | Analytics / Registry | Versioned governed metric definition |
| `kpi_publication` | Analytics + Setup | Company enablement / published set |
| `kpi_evaluation_request` | Analytics (ephemeral or audited) | Inputs for evaluate (definition, as-of/period, filters, actor) |
| `kpi_evaluation_result` | Analytics | Value + status + metadata + freshness + definition version |
| `kpi_drill_population` | Analytics | Authorized included entity IDs for numerator/denominator |
| `analytics_fact_*` (typed families) | Analytics projections from domain | Materialized/queryable facts — **not** alternate SoT |
| `analytics_dimension_binding` | Analytics | Maps canonical org/employee attributes → segment keys |
| `analytics_refresh_run` | Analytics | Ingest/rebuild job metadata |
| `analytics_export_job` | Analytics | Export audit + retained evaluation metadata |
| Domain entities | Owning modules | Unchanged SoT (employees, payroll runs, reviews, HiPo, etc.) |

Commercial entitlement: company module `analytics` (and optionally per-KPI publication inside Setup).

---

## 4. KPI definition model (Registry)

### 4.1 Required fields (minimum)

| Field | Requirement |
|---|---|
| `kpi_definition_id` | Stable UUID / surrogate for a definition row |
| `semantic_key` | Stable product key (e.g. `workforce.headcount.active_heads`) |
| `name_en` / `name_ar` | Bilingual display name |
| `description_en` / `description_ar` | Bilingual business meaning |
| `business_meaning` | What decision the metric supports |
| `numerator` | Explicit contract |
| `denominator` | Required when rate/ratio; else null with reason |
| `formula_contract` | Versioned calculation specification |
| `unit` | count, ratio, percent, currency, days, FTE, etc. |
| `inclusion_rules` | Who/what is in |
| `exclusion_rules` | Who/what is out |
| `time_semantics` | point_in_time \| event_count \| period_sum \| period_average \| rate_over_window \| cohort \| rolling_window |
| `as_of_vs_period` | Behavior for as-of date vs closed period |
| `supported_dimensions` | Allowlist of segment keys |
| `canonical_source_facts` | Fact types / domain authorities |
| `required_domain_authority` | HARD modules/facts |
| `permission_class` | See §8 |
| `effective_version` | Monotonic version of this semantic key |
| `owner` / `approving_authority` | Product owner of the definition |
| `status` | `draft` \| `published` \| `retired` (or equivalent) |

### 4.2 Versioning rules

1. Changing numerator/denominator/inclusion/time/formula → **new effective version** (or new definition row linked by `semantic_key`).  
2. Historical evaluations store **`kpi_definition_id` + `effective_version`** (and frozen formula snapshot where needed).  
3. Retiring a KPI hides future cards; historical exports remain explainable.  
4. Company overrides (if allowed) are Setup-owned and versioned — never silent env edits.

### 4.3 Evaluation result statuses

| Status | Meaning |
|---|---|
| `ok` | Value computed |
| `not_applicable` | Denominator zero / cohort empty by definition |
| `insufficient_data` | Required facts missing/incomplete |
| `unavailable` | Domain module off / entitlement missing / money authority absent |
| `suppressed` | Small-group / confidentiality suppression |
| `forbidden` | Actor lacks permission |

---

## 5. Fact model

### 5.1 Shared spine fields (every fact)

| Field | Purpose |
|---|---|
| `company_code` | Tenant |
| `fact_type` | Typed contract key |
| `entity_type` / `entity_id` | Source record identity |
| `event_time` | When the business event occurred |
| `effective_time` / `effective_from` / `effective_to` | When it was true for as-of reconstruction |
| `recorded_at` | Ingest/system time |
| `dimensions` | Resolved segment keys (dept, location, manager, …) |
| `measures` | Typed measure payload |
| `source_authority` | Owning module / table / API |
| `source_version` | Domain row version / cycle version / policy version where applicable |
| `correction_of` / `supersedes` | Governed correction chain |
| `is_synthetic` | Must remain labeled if synthetic |

### 5.2 Typed fact families (balance shared spine + domain schemas)

Prefer **typed contracts** over one meaningless mega-JSON:

| Family | Examples (initial) | Source waves |
|---|---|---|
| `workforce_employment_fact` | active assignment, FTE weight, status, pending_start, notice, left | W1–3 |
| `org_assignment_fact` | manager, dept, location, role/grade effective ranges | W1–3 |
| `hire_event_fact` | hire date, source, requisition, offer | W1 |
| `exit_event_fact` | exit/LWD, reason, regret flag if present | W3 |
| `recruiting_pipeline_fact` | req open/fill, stage timestamps | W1 |
| `offer_event_fact` | offered/accepted/declined | W1 |
| `onboarding_progress_fact` | completion, blocked, duration | W1 |
| `probation_outcome_fact` | confirmed/extended/failed | W1 |
| `attendance_day_fact` | present/absent/late/OT projections | W2 |
| `leave_ledger_fact` | type, days, period | W2 |
| `payroll_component_fact` | finalized components only | W2 |
| `performance_goal_fact` | attainment, cycle | W4 C1 |
| `performance_outcome_fact` | distribution inputs (final locked) | W4 C2/C4 |
| `competency_development_fact` | assessments/actions | W4 C3 |
| `talent_population_fact` | profile presence | W4 C5 |
| `hipo_fact` | explicit designation only | W4 C6 |
| `succession_coverage_fact` | ready-now, successor counts, uncovered | W4 C6 |
| `workflow_sla_fact` | task/approval age, breach | Phase A / W1+ |

Wave 4 already documents a Wave 5 fact catalog (`setup_console_wave4_policies.wave5_fact_catalog` / C6 coverage facts). Wave 5 **consumes and formalizes** these — does not reinvent Talent/Performance SoT.

### 5.3 Corrections

A corrected source event updates analytics via governed ingest/rebuild **without rewriting** the domain module’s audit history.  
Analytics stores correction/supersession links; prior evaluation snapshots used for issued reports remain reproducible.

---

## 6. Temporal model

| Concept | Definition |
|---|---|
| **Event time** | When the business event happened (hire date, punch day, exit LWD) |
| **Effective time** | Interval during which a state was true (org assignment, employment status) |
| **Recorded time** | When Wathefni learned/ingested it |
| **As-of metric** | Reconstruct state at instant T using effective ranges (e.g. headcount) |
| **Period metric** | Aggregate events/states over `[start, end)` |
| **Cohort metric** | Follow a set defined at T0 through a window |
| **Rolling window** | Trailing N days/months ending at as-of |

**Reproducibility rule:** A historical report stores definition version + filters + time bounds + (where needed) fact snapshot identity / evaluation watermark. Later transfers, manager changes, org restructures, policy changes, or KPI-definition edits must not silently mutate that report’s meaning.

---

## 7. Dimensional / segmentation model

### 7.1 Common dimensions (governed allowlist)

| Dimension key | Notes |
|---|---|
| `department` | Canonical org |
| `division` / `business_unit` | Where available |
| `branch` / `location` | |
| `manager` | Manager scope aware |
| `job` / `role` | |
| `grade` / `level` | When available |
| `employment_type` | |
| `tenure_bucket` | Derived from tenure rules |
| `recruitment_source` | Recruiting KPIs |
| `leave_type` | Leave KPIs |
| `payroll_component` | Money KPIs |
| `review_cycle` | Performance KPIs |
| `critical_role` | Talent/succession KPIs |
| `nationality` | **Optional; lawful + authorized only; default off** |
| `gender` / other demographics | **Optional; lawful + authorized only; default off** |

### 7.2 Query contract

Reusable filter object:

```text
{
  kpi_definition_id, effective_version?,
  time: { mode, as_of?, period_start?, period_end?, rolling? },
  segments: [{ dimension, op, values }],
  scope: { actor, manager_scope_enforced: true }
}
```

Do not hardcode every KPI to its own custom filter dialect.

---

## 8. Permission / confidentiality model

### 8.1 Permission classes (minimum)

| Class | Examples | Rules |
|---|---|---|
| `workforce_general` | Headcount, hires, exits (non-sensitive) | Manager scope; HR broader |
| `workforce_sensitive_demo` | Gender/nationality slices | Explicit Setup enable + lawful basis + stronger perm |
| `time_leave` | Absenteeism, leave util | Domain leave/attendance perms |
| `payroll_money` | Workforce cost, component movement | Payroll entitlement + money perms; fail closed |
| `performance_aggregate` | Distributions, goal attainment aggregates | Performance module + aggregate rules |
| `performance_raw` | Individual ratings / raw 360 | Rare in Intelligence; inherit Wave 4 raw protections |
| `talent_sensitive` | Potential, HiPo, succession | Sensitive Talent perms; employee self typically denied |
| `lifecycle_confidential` | Certain exit/ER-linked facts | Confidential lifecycle perms |
| `platform_ops` | SLA/aging | HR ops scope |

### 8.2 Propagation rules

1. Analytics **intersects** domain permissions — never unions them weaker.  
2. Manager sees Intelligence only within authorized report scope.  
3. Cross-tenant denial absolute.  
4. Aggregate suppression: if cohort size &lt; company `min_cohort_n` (Setup), return `suppressed` rather than a disclosive number.  
5. Cross-tabs that isolate a single person must suppress.

### 8.3 Talent / Performance anti-inference

- Top performance ≠ HiPo  
- Top-right 9-box ≠ HiPo  
- Strong skills ≠ successor  
- AI ≠ potential assessor  
HiPo / succession / potential KPIs consume **explicit Wave 4 records only**.

---

## 9. Query / materialization strategy

| Scale / need | Strategy | Freshness communication |
|---|---|---|
| Small company / simple point-in-time | Live canonical query with indexes | Near-real-time; optional `as_of=now` |
| Medium / repeated dashboard loads | Indexed projections / partial matviews | `last_refreshed_at` on result |
| Large / heavy period rates | Incremental fact tables + cached aggregates | Periodic refresh; stale banner if watermark lag exceeds policy |
| Money KPIs | Only from finalized payroll projections | Fail closed if no sealed authority |
| Historical report re-open | Evaluation snapshot / watermark + definition version | Exact reproducibility |

**Avoid:** scanning millions of operational rows on every Overview load.  
**Avoid:** requiring a warehouse to serve a 30-person company.  
**Design for evolution:** start with Postgres + projections; allow later warehouse export without changing Registry semantics.

### 9.1 Freshness / reconciliation

| Concern | Rule |
|---|---|
| Near-real-time vs periodic | Per KPI / fact family policy |
| Last-refreshed | Exposed on results when not live |
| Source correction | Re-ingest → rebuild projections → bump watermark |
| Stale handling | Never present overdue watermark as guaranteed current |
| Rebuild | Idempotent; auditable `analytics_refresh_run` |

---

## 10. Setup ownership

Setup Console owns customer Intelligence policy (not env-only config):

| Policy area | Examples |
|---|---|
| KPI enablement / publication | Which published Registry KPIs appear for the company |
| Definition overrides | Where company-specific inclusion/FTE rules are supported (versioned) |
| Cohort / privacy thresholds | `min_cohort_n`, sensitive dimension enablement |
| Fiscal / reporting periods | Fiscal year start; custom reporting calendars |
| Workforce semantics | Heads vs FTE defaults; notice-period inclusion; pending_start inclusion |
| Segmentation availability | Which dimensions HR may use |
| Manager analytics access | On/off and scope rules |
| Sensitive analytics permissions | Payroll/Talent/Performance aggregate grants |
| Export / report policies | Who may export; retention; watermark requirements |

**Environment flags** = deployment / kill-switch only.

Proposed Setup card family: `Wave5HrIntelligencePoliciesCard` (post-approval implementation).

---

## 11. Surfaces

| Surface | Role |
|---|---|
| **HR Web** | Primary Intelligence: Overview, Registry cards, trends, compare, segment, filter, drill, definition explain, saved views, export |
| **HR Mobile** | Small decision-useful summaries only — not a BI studio |
| **Employee App** | Only separately justified personal insights; **no** company-wide analytics |
| **Assistant** | Explain/query governed metrics under same permissions; refuse undefined KPIs |
| **Channels** | Optional later delivery of reports/alerts; canonical metrics remain inside Wathefni |

### 11.1 UX architecture

Intelligence Overview supports:

- metric cards **only** from Registry publications  
- trends · comparisons · segmentation · filtering  
- drill-down · metric definition/explanation  
- saved views (where appropriate) · exports  
- later scheduled reports (same evaluator)

**Keep operational Attention / work queues separate.**  
Label clearly: Ops Attention ≠ HR Intelligence.

---

## 12. Exports / reports

| Rule | Requirement |
|---|---|
| Same authority | CSV/PDF/report use identical evaluator as UI |
| No parallel formulas | Forbidden |
| Retained metadata | `kpi_definition_id`, version, filters, period/as-of, generated_at, tenant, scope/context |
| Audit | Who exported what |
| Scheduled reports | Later slice OK; architecture must not duplicate calculations |

---

## 13. Initial KPI registry (governed contracts)

Status legend: **Ready** (facts largely exist) · **Partial** (needs definition hardening) · **Blocked/Deferred** (facts/authority insufficient or policy pending)

### 13.1 Workforce

| Semantic key (proposed) | Status | Notes |
|---|---|---|
| `workforce.headcount.active_heads` | Partial → C2 | Binding inclusion: pending_start OUT (separate future starters); notice IN until LWD; leave/suspension IN; contingent OUT |
| `workforce.fte.active` | **Blocked** | Not publishable until authoritative FTE/standard-hours inputs exist; never 1 head = 1 FTE |
| `workforce.hires.count` | Ready | Hire events |
| `workforce.exits.count` | Ready/Partial | Lifecycle exit facts; real-term still locked |
| `workforce.turnover.rate` | Partial | Honest denominator/window |
| `workforce.retention.rate` | Partial | Cohort semantics |
| `workforce.tenure.distribution` | Partial | Bucket rules |
| `workforce.span_of_control` | Partial | Org assignment effective ranges |

### 13.2 Recruiting

| Semantic key | Status | Notes |
|---|---|---|
| `recruiting.time_to_fill` | Ready/Partial | Req open → fill |
| `recruiting.time_to_hire` | Ready/Partial | Offer accept / hire |
| `recruiting.offer_acceptance_rate` | Ready | Denominator = offers extended |
| `recruiting.source_effectiveness` | Partial | Source dimension quality |

### 13.3 Hire → Ready

| Semantic key | Status | Notes |
|---|---|---|
| `hire_ready.preboarding_completion_rate` | Ready/Partial | Module-off → unavailable |
| `hire_ready.onboarding_completion_rate` | Ready/Partial | |
| `hire_ready.onboarding_completion_time` | Ready/Partial | |
| `hire_ready.probation_outcomes` | Ready | Confirmed/extended/failed |

### 13.4 Time / Leave

| Semantic key | Status | Notes |
|---|---|---|
| `time.attendance_rate` | Partial | Only where honestly definable from projections |
| `time.absenteeism_rate` | Partial | Denominator required |
| `time.lateness_rate` | Partial | |
| `time.overtime` | Partial | Authorized OT facts |
| `leave.utilization_rate` | Partial | Type + entitlement window |

### 13.5 Payroll

| Semantic key | Status | Notes |
|---|---|---|
| `payroll.workforce_cost` | HARD on authoritative finalize | Fail closed otherwise |
| `payroll.movement` | HARD on authoritative finalize | |
| `payroll.component_movement` | HARD + component perm | |

### 13.6 Performance

| Semantic key | Status | Notes |
|---|---|---|
| `performance.goal_attainment` | Ready (W4 C1 facts) | |
| `performance.review_completion` | Ready (W4 C2) | |
| `performance.outcome_distribution` | Ready (W4 C2/C4 final) | No inventing from drafts |
| `performance.competency_development` | Ready/Partial (W4 C3) | |

### 13.7 Talent

| Semantic key | Status | Notes |
|---|---|---|
| `talent.population` | Ready (W4 C5) | |
| `talent.hipo_count` | Ready (W4 C6 explicit only) | |
| `talent.succession_coverage` | Ready (W4 C6) | |
| `talent.successors_per_critical_role` | Ready | |
| `talent.ready_now_coverage` | Ready | |
| `talent.readiness_distribution` | Ready | |
| `talent.uncovered_critical_roles` | Ready | |

### 13.8 Platform Operations

| Semantic key | Status | Notes |
|---|---|---|
| `platform.workflow_sla` | Partial | Phase A SLA facts |
| `platform.approval_aging` | Partial | |
| `platform.hr_task_aging_completion` | Partial | Meaningful types only |

**Do not assume all are immediately publishable.** C-slices mark blocked/deferred honestly when facts are insufficient.

---

## 14. Cross-surface strategy (detail)

See §11. Additional rules:

- HR Mobile may show 1–3 entitled summary KPIs with deep-link to Web drill — never full segmentation studios.  
- Employee App: personal goal attainment / own leave util only if separately justified and permission-safe.  
- Assistant must cite `semantic_key` / definition version when explaining a number.

---

## 15. EN / AR / RTL

Required for:

- bilingual KPI names + descriptions/definitions  
- period/filter labels  
- chart/table labels  
- drill-down UX  
- export labels  
- proper RTL layout  

Do **not** translate only page headings while leaving metric explanations English-only.

---

## 16. Rollout flags (fail-closed; post-approval)

Pattern: `WATHEFNI_<FEATURE>[_C#]` + `_COMPANIES` (empty = nobody) + optional `_KILL`.

| Flag (proposed) | Default | Notes |
|---|---|---|
| `WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1` | off | Registry + query spine |
| `WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2` | off | Workforce/lifecycle KPIs |
| `WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3` | off | Recruiting / Hire→Ready |
| `WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4` | off | Time/Leave/Payroll |
| `WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_C5` | off | Performance/Talent KPIs |
| `WATHEFNI_HR_INTELLIGENCE_SURFACES_C6` | off | Trends/drill/export/surfaces |
| `WATHEFNI_HR_INTELLIGENCE_PRODUCT_C7` | off | Product acceptance |
| Per-slice `_COMPANIES` | empty | Nobody until canary listed |
| `WATHEFNI_ANALYTICS_KILL` | off | Immediate block on Intelligence evaluate/publish when on |

Production systemd must **not** globally enable these. Process-scoped prove only until owner unlock.  
Wave 5 starts **dark / company-gated**. No global rollout.

---

## 17. Serial build order (C0–C7)

| Phase | Focus | Exit stamp |
|---|---|---|
| **C0** | Charter / KPI semantics / fact contracts / binding locks | **APPROVED** — `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED` |
| **C1** | KPI Registry + query spine + fact ingest skeleton + undefined semantics | **ACCEPTED / FROZEN** `HR_INTELLIGENCE_REGISTRY_FULL_PASS` · evidence `ops/evidence/hr-intelligence-registry-c1-20260812T085833Z` |
| **C2** | Workforce / lifecycle core metrics (headcount honesty first) | **ACCEPTED / FROZEN** `HR_INTELLIGENCE_WORKFORCE_FULL_PASS` · evidence `ops/evidence/hr-intelligence-workforce-c2-20260812T091515Z` |
| **C3** | Recruiting / Hire→Ready metrics | **ACCEPTED / FROZEN** `HR_INTELLIGENCE_RECRUITING_FULL_PASS` · evidence `ops/evidence/hr-intelligence-recruiting-c3-20260812T093411Z` |
| **C4** | Time / Leave / Payroll metrics (money fail-closed) | **ACCEPTED / FROZEN** `HR_INTELLIGENCE_TIME_PAY_FULL_PASS` · evidence `ops/evidence/hr-intelligence-time-pay-c4-20260812T094705Z` |
| **C5** | Performance / Talent metrics (explicit Wave 4 only) | **ACCEPTED / FROZEN** `HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS` · evidence `ops/evidence/hr-intelligence-perf-talent-c5-20260812T100558Z` |
| **C6** | Segmentation / trends / drill / on-demand export / saved views / surfaces / Setup | **ACCEPTED / FROZEN** `HR_INTELLIGENCE_SURFACES_FULL_PASS` · evidence `ops/evidence/hr-intelligence-surfaces-c6-20260812T102727Z` |
| **C7** | Full product acceptance, modularity, cross-surface, regressions | **ACCEPTED / FROZEN** `WAVE5_PRODUCT_FULL_PASS` · evidence `ops/evidence/wave5-product-acceptance-20260812T103942Z` |

### 17.1 Per-slice requirements (every C1–C7)

| Item | Requirement |
|---|---|
| Scope | Narrow, stampable |
| Canonical authority | Registry + evaluator; domains remain SoT |
| Dependencies | HARD / OPTIONAL / ENHANCEMENT declared |
| Migrations | Additive; no rewrite of domain history |
| Setup ownership | Company policies where customer-facing |
| Permissions | Class + manager scope + suppression |
| Surfaces | Web primary; Mobile thin; Assistant explain |
| EN/AR | Labels + definitions |
| Flags | Fail-closed company allowlists |
| Staging/canary | Qualify script + evidence pack |
| Rollback | Flags off; history/evals retained |
| FULL_PASS stamp | Required before next slice |
| Freeze amendment | Document; do not reopen prior waves for debt |

### 17.2 Slice dependency notes

| Slice | HARD | OPTIONAL | Notes |
|---|---|---|---|
| C1 | Company + RBAC | Domain facts | Spine first; cards remain dark without published defs |
| C2 | Employment/org effective history | Lifecycle exits | Headcount unban only with Registry definition |
| C3 | Recruiting/requisitions/offers/onboarding/probation as entitled | — | Module-off → unavailable |
| C4 | Attendance/leave projections; **payroll finalize** for money | Shifts | Money KPIs fail closed |
| C5 | Wave 4 fact emits | 9-box projection facts | Never infer HiPo |
| C6 | C1 spine | Prior KPI slices | Export = same evaluator |
| C7 | C1–C6 accepted | — | Product matrix + Wave 1–4 regressions |

### 17.3 Safe parallelism (post-approval)

- C3 may proceed after C1 even if C2 still hardening FTE variants  
- C5 may start after C1 once Wave 4 facts are consumed — **must not** wait on C4 money  
- C4 money path is critical before claiming workforce-cost KPIs  
- C6 surfaces only after at least one domain KPI slice publishes real cards  
- C7 only after C1–C6 accepted  

---

## 18. Rollback strategy

| Layer | Rollback |
|---|---|
| Flags | Slice/company off; kill switch blocks evaluate/publish |
| Registry | Retire publication; definitions retained for history |
| Projections | Stop refresh; do not delete historical evaluation metadata needed for audits |
| Domains | **Never** mutated by Wave 5 rollback |
| UI | Unpublished KPIs disappear cleanly |

---

## 19. Acceptance gates (charter-level; proven by C7)

| # | Gate |
|---|---|
| 1 | Every displayed governed KPI has Registry definition/version |
| 2 | KPI result is deterministic from canonical facts |
| 3 | Exact population/drill-down can be reproduced |
| 4 | Historical as-of metrics remain reproducible |
| 5 | Definition changes do not rewrite historical reports |
| 6 | Tenant isolation |
| 7 | Manager scope |
| 8 | Sensitive payroll / talent / performance confidentiality |
| 9 | Denominator / undefined semantics (`not_applicable` / `insufficient_data`) |
| 10 | Money KPIs fail closed without authoritative payroll |
| 11 | Talent KPIs consume explicit Wave 4 decisions only |
| 12 | Segmentation uses canonical dimensions |
| 13 | UI/export use identical metric authority |
| 14 | EN/AR + RTL |
| 15 | Setup owns customer policy |
| 16 | Module-off combinations remain clean |
| 17 | Source corrections reconcile safely |
| 18 | No universal employee/Talent score |
| 19 | Assistant cannot invent metrics |
| 20 | Waves 1–4 regressions remain green |

Roadmap §7.3 gate (≥12 KPIs with trend+segment+drill+export; headcount live with definition; manager scope; EN/AR) remains the product bar for `WAVE5_PRODUCT_FULL_PASS`.

---

## 20. Freeze amendments (required before/with slices)

| Prior freeze / surface | Wave 5 amendment intent |
|---|---|
| `ops/WAVE4_PRODUCT_FREEZE.md` | Wave 5 consumes Performance/Talent facts; Wave 4 stays frozen |
| `ops/WAVE3_PRODUCT_FREEZE.md` | Lifecycle facts only; real termination untouched |
| `ops/WAVE2_PRODUCT_FREEZE.md` | Time/pay facts; money KPIs only on authoritative payroll |
| `ops/WAVE1_PRODUCT_FREEZE.md` | Hire→Ready facts; Attention remains Ops, not Intelligence |
| Analytics Attention “headcount ban” | Lifted **only** via published Registry headcount definition (intentional un-ban) |
| Module catalog | Register/extend `analytics` entitlement for Intelligence |

Each slice ships: qualify script + evidence + `*_FULL_PASS` stamp + freeze amendment. Stop for owner review between slices.

---

## 21. Global safety

- Wave 5 starts dark / company-gated  
- No global rollout  
- No mutation of Waves 1–4 canonical truth  
- No reopening frozen modules merely to simplify analytics  
- No invented KPI formulas  
- No fake data / hardcoded demo numbers in production paths  
- No UI before the underlying metric is authoritative  
- No universal employee score  
- Assistant never fabricates metrics  

---

## 22. Owner decisions — resolved

All §0.7 items are **LOCKED** as of 2026-08-12. No open charter blockers before C1.

Residual implementation choices (non-charter blockers): exact Postgres projection shapes per KPI family; when to promote live query → matview for a given tenant scale; whether recurring scheduled delivery reuses an existing scheduler in C6 without scope expansion (else post-Wave-5 safe debt).

---

## 23. Stop condition / implementation gate

**`WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`**

Implementation may proceed **serially**:

1. **C1** — ACCEPTED / FROZEN · `HR_INTELLIGENCE_REGISTRY_FULL_PASS`  
2. **C2** — ACCEPTED / FROZEN · `HR_INTELLIGENCE_WORKFORCE_FULL_PASS`  
3. **C3** — ACCEPTED / FROZEN · `HR_INTELLIGENCE_RECRUITING_FULL_PASS`  
4. **C4** — ACCEPTED / FROZEN · `HR_INTELLIGENCE_TIME_PAY_FULL_PASS`  
5. **C5** — ACCEPTED / FROZEN · `HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS`  
6. **C6** — ACCEPTED / FROZEN · `HR_INTELLIGENCE_SURFACES_FULL_PASS` · evidence `ops/evidence/hr-intelligence-surfaces-c6-20260812T102727Z`  
7. **C7** — ACCEPTED / FROZEN · `WAVE5_PRODUCT_FULL_PASS` · evidence `ops/evidence/wave5-product-acceptance-20260812T103942Z`  

Wave 5 remains frozen. Global Wave 5 remains off / company-gated.  
Wave 6 = charter only until approved: `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` (`WAVE6_HCM_EXPANSION_CHARTER: PENDING`).  
Do not skip stamps. Do not reopen Waves 1–4 for analytics convenience.
