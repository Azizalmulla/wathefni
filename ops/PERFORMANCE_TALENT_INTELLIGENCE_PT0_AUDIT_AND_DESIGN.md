# PERFORMANCE & TALENT INTELLIGENCE DEPTH PROGRAM — PT0

**Status:** AUDIT + DESIGN COMPLETE — stop for owner review  
**Stamp requested:** none (design only; no production code)  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**Paused:** Production Readiness R7 (Mobile Keyboard / Native Safety)  
**Do not begin:** PT1 or R7 automatically  

---

## 0. Binding posture

### 0.1 What stays frozen

| Freeze | Rule for PT |
|---|---|
| Wave 4 C1–C7 Performance + Talent authorities | Do **not** design a second Performance or Talent system. Do **not** reopen C1–C6 math unless a genuine architectural blocker is proved. |
| R5B Performance surface | Adapter stays. Depth extends it; does not replace it. |
| R5C Talent surface | Adapter stays. Depth extends it; does not replace it. |
| Wave 5 C1 Registry + C5 Perf/Talent facts + C6 surfaces | Reuse. Do **not** create a second analytics engine. |
| Wave 6 JA / Learning / WFP | Consume via OPTIONAL contracts. Do **not** add eligibility scores to JA. Do **not** auto-verify skills from Learning. |
| R2–R6 Production Readiness | Remain valid. PT does not invalidate them. |
| Recruiting `talent_pool` | Candidate-only. Never aliased to post-hire Talent. |
| Assistant mutations | Remain out unless separately chartered. Core calculations stay deterministic outside the LLM. |

### 0.2 Audit verdict on freeze reopen

**No genuine architectural blocker.** Frozen authorities already encode the right separations:

- OKR achievement ≠ employee quality ≠ potential ≠ HiPo
- 9-box is a projection, never Talent SoT
- Readiness is target-role specific; no universal readiness score
- No master Talent score
- HiPo is an explicit human decision
- Mobility interest ≠ application ≠ selection ≠ employment change
- Learning completion ≠ skill verification ≠ competency
- High performer (Wave 5) ≠ HiPo
- Bench strength is honestly `unavailable` until a governed formula exists

PT depth is an **overlay + composition** programme: new derived services that *read* frozen authorities and write only new, versioned, inspectable objects.

Additive freeze *amendments* (new enum values, optional columns, new tables) will be required in later slices. Those are not reopenings of frozen math.

### 0.3 What “flagship” means here

Not: “Wathefni supports talent mapping.”

Yes: an experienced HR leader opens the Talent Map, inspects a placement, and can see **which configured model version**, **which evidence**, **which gaps**, and **which human judgments** produced the classification — then can change the lens without the system inventing a universal score.

UX remains Wathefni: simple overview → progressive exploration → deep evidence on request. No Excel-first grid, no card spam, no permanent filter wall, no meaningless colorful scores, no generic AI sparkles.

---

## 1. CURRENT STATE MATRIX

Depth classes used below:

| Class | Meaning |
|---|---|
| **Already excellent** | Canonical authority + honesty + enough product surface to trust |
| **Exists but shallow** | Right authority exists; product depth / intelligence / UX is thin |
| **Partially supported** | Primitive, optional contract, or projection exists; not a complete capability |
| **Missing** | No governed implementation; must be designed as new overlay |

### 1.1 Capability A — OKRs

| Target | Class | What is actually shipped |
|---|---|---|
| Objective + multiple measurable KRs | **Already excellent** | `perf_objectives` + `perf_key_results` + `perf_measure_definitions`. Decorative `progress_pct` rejected. `compute_progress` / `objective_rollup` are versioned (`measure_v1`). |
| Owners | **Already excellent** | `owner_employee_key` on objective / goal / measure. |
| Targets + progress | **Already excellent** | Baseline / target / direction / source. Missing current → `not_started` / unknown, never 100%. `perf_progress_entries` + `perf_target_versions`. |
| Alignment scopes company → dept → team → individual | **Exists but shallow** | Scope enum is first-class. `perf_alignment_links` (`aligned` / `contributes_to` / `supports`) exist. **No alignment tree UI, no inheritance visualization, no cycle-scoped cascade view.** Forced cascade remains correctly forbidden. |
| Periods / cycles | **Partially supported** | `period_start` / `period_end` on objectives and measures. **No first-class OKR cycle** (distinct from C2 review cycles — correctly so). Cross-period comparison is not a product. |
| Check-ins | **Partially supported** | C3 `perf_check_ins` can link to `objective` / `key_result`. Check-ins do **not** auto-mutate progress (correct). **No OKR-native check-in cadence, confidence, or update thread in the Performance workspace.** |
| Confidence / health | **Missing** | No governed confidence/health field. Progress status is derived (`on_track` / `unknown` / `not_started`) from measure math only. |
| Comments / updates | **Partially supported** | `perf_progress_entries.note` + C3 check-in notes. **No first-class comment thread on an Objective.** |
| Scoring methodology | **Exists but shallow** | Weighted KR roll-up is explicit. No committed-vs-stretch, no scoring policy object, no company-configurable roll-up alternatives. |
| History / versioning | **Already excellent** (data) / **shallow** (UX) | Target versions + progress entries + audit. Surfaces show current state more than trajectory. |
| Trajectory | **Missing** as a named concept | History exists; no governed period-over-period pattern. |
| Permissions / visibility | **Partially supported** | Module + manager scope + employee self on R5B surfaces. No per-OKR visibility (e.g. company OKR public, individual KR manager-only). |
| OKRs as optional Talent evidence | **Partially supported** | `talent_performance_evidence_links` allows `goal` and `check_in`. **Does not yet admit `objective` / `key_result` as explicit subject types.** Setting `performance_evidence_consume` is opt-in. |

**Preserve (already locked, still binding):** OKR achievement ≠ employee quality ≠ potential ≠ HiPo. `performance_surfaces.strip_talent()` remains.

### 1.2 Capability B — Talent Evidence

| Evidence source | Class | Authority to reuse | Consume status |
|---|---|---|---|
| Employment / role history | **Partially supported** | Wave 2 employees / employment + `ja_employment_assignment` | Talent profile does not read these as evidence. JA assignment is the role-history SoT when JA is on. |
| Job Architecture | **Partially supported** | `ja_job_profile`, `ja_career_edge.optional_requirements` | Requirements are declarative jsonb lists; eligibility scoring is **forbidden** (correct). No Talent read-through. |
| Skills | **Exists but shallow** | `talent_skills` (claimed / verified / assessed) | First-class, versioned, history table. Not yet a map input or role-fit input. |
| Competencies | **Exists but shallow** | C3 `perf_c3_competency_*` + `talent_competency_evidence_maps` | Explicit contract required (correct). Not auto-copied. |
| Certifications | **Partially supported** | `ld_certifications` | Learning honesty: completion ≠ certification ≠ skill verify. No Talent evidence link. |
| Learning | **Partially supported** | `ld_completions`, `ld_development_fulfillment_links` | Source enum already includes `learning_evidence`. No live contract. |
| OKRs | **Partially supported** | C1 objectives/KRs | Optional Performance evidence only; see §1.1. |
| Performance reviews | **Exists but shallow** | C2 reviews + C4 calibrated/sealed | `talent_performance_evidence_links` (`review`, `pre_calibration_result`, `calibrated_result`). Opt-in. Never becomes potential. |
| Manager assessments | **Already excellent** (potential) / **shallow** (other) | `talent_potential_assessments.assessor_role ∈ {manager,hr}` | Potential is human-assessed with rationale. Other manager judgments live as dimension facts. |
| Recruiting-stage evidence | **Missing** as post-hire evidence | Pre-hire assessments / interviews / ranking | Correctly isolated from `talent_pool`. No OPTIONAL “import permitted recruiting evidence at hire” contract. |
| Assessments / psychometrics | **Missing** as Talent evidence | `assessment_lifecycle` (pre-hire) | Must stay optional, consented, and never silently become potential. |
| Career interests | **Already excellent** | `talent_dimension_facts` (`career_aspiration`, `role_interest`, `job_family_interest`, `mobility_preference`) | Employee-declared vs manager/HR kept separate. Silent rewrite forbidden. |
| Development actions | **Already excellent** (authority) | C3 `perf_development_plans` / `perf_development_actions` | Talent `development_context()` reuses C3. No second plan authority. |
| Potential | **Already excellent** | `talent_potential_frameworks` + `talent_potential_assessments` | Versioned framework; performance optional; never auto from ratings. |
| Readiness | **Exists but shallow** | C5 `talent_readiness_observations` + C6 nomination `readiness` | Observations are primitive. Nomination readiness is target-specific (correct) but **manual**, not computed from gaps. |
| Succession | **Exists but shallow** | C6 plans / nominations / coverage facts | Works. Intelligence (risk, concentration, bench) is thin. |
| Mobility | **Partially supported** | C5 mobility preference + R5C `mobility_surface` | Honesty is excellent. **Matching engine was explicitly not built in C6.** |

### 1.3 Capability C — Configurable Talent Models

| Target | Class | Notes |
|---|---|---|
| Versioned tenant-configurable model | **Missing** | Closest analog: `talent_potential_frameworks` (dimensions + scale points) and `talent_nine_box_configs` (two axes). Neither is a general classification model. |
| Dimensions / evidence sources / scales | **Partially supported** | Potential frameworks + 9-box axes. Not a reusable model object. |
| Weights / thresholds / eligibility | **Missing** | Intentionally absent (avoid fake precision). Must be opt-in and explainable if added. |
| Manual HR / manager / system-derived / AI-synthesized kept separate | **Partially supported** | Source enums exist on facts/skills. **No first-class provenance class on a derived classification.** HiPo is human-only (`inferred_from_nine_box = false` CHECK). |
| Derived classification (e.g. High Potential) that does not overwrite | **Missing** | Today HiPo **is** the designation. A model must produce a **separate** `model_classification`, never write `talent_hipo_designations`. |
| No universal Talent score | **Already excellent** | Enforced in schema (`talent_profiles` CHECK) and honesty payloads. |

### 1.4 Capability D — Dynamic Talent Map

| Target | Class | Notes |
|---|---|---|
| Exploratory map with governed lenses | **Missing** | `talent_map_queries()` is a stub: role→successors and employee→target roles. No spatial map. |
| Performance × Potential | **Exists but shallow** | Optional 9-box projection + review snapshot. Default OFF. UI tab exists; not exploratory. |
| Potential × Readiness, Role Fit × Readiness, Growth × Contribution, capability × criticality | **Missing** | No lens objects. Role fit does not exist as a Talent authority (pre-hire ranking `role_fit` in `app.py` is **recruiting-only** and must not be reused). |
| Customer-defined dimensions | **Missing** | Safe only after a model + lens framework exists. |
| Inspectable WHY on every placement | **Missing** | Rationale exists on HiPo / potential / nominations. No structured WHY graph for a map cell. |
| Classical 9-box as one derived visualization | **Already excellent** (contract) | Binding lock. Do not invert. |

### 1.5 Capability E — Explainability

| Target | Class | Notes |
|---|---|---|
| Why HiPo / ready / successor rank / contributing evidence / remaining gaps / model version | **Partially supported** | Human rationale + `evidence_refs` jsonb + Wave 5 KPI `explain` currency. **No structured evidence graph, no model version on a classification, no AI narration layer.** |
| AI synthesizes explanation from canonical evidence | **Missing** | Allowed later as narration only. |
| AI must not invent evidence or secretly classify | **Already excellent** (policy) | C5/C6 `assert_no_forbidden_*_writes`; Assistant mutations out; Wave 5 refuses invented metrics. |

### 1.6 Capability F — Role Fit & Readiness

| Target | Class | Notes |
|---|---|---|
| employee → target role → requirements → evidence → gaps → readiness | **Missing** as an engine | Pieces exist separately. |
| JA as requirement source | **Partially supported** | Profiles + career edges with optional skill/competency lists. **No versioned requirement set.** Eligibility scores forbidden on JA (keep). |
| Competencies / skills / experience / certs / assessments / performance / development | **Partially supported** | Each has an authority; none are composed into a fit evaluation. |
| Readiness is target-role specific | **Already excellent** (contract) | C6 nomination readiness + C5 `role_specific_primitive`. |
| No universal employee readiness score | **Already excellent** | `global_readiness_score: None` on surfaces. |

### 1.7 Capability G — Succession Intelligence

| Target | Class | Notes |
|---|---|---|
| Critical role → holder → multiple successors → target readiness → gaps → development → bench | **Exists but shallow** | All entities exist. Current holder is implied via org/JA, not a first-class succession field. Gaps are jsonb. Development may create a C3 action. |
| No-successor roles | **Already excellent** | `list_uncovered_critical_roles` + Wave 5 `talent.uncovered_critical_roles`. |
| Single-successor risk | **Missing** | Coverage facts count successors; no risk class. |
| Strong benches | **Missing** | Wave 5 `talent.bench_strength` is **explicitly unavailable** (honest). |
| Readiness gaps | **Partially supported** | Per-nomination `capability_gaps` + readiness distribution KPI. No role-level intelligence product. |
| Concentration risk | **Missing** | Same person on many critical slates is allowed (correct) but not flagged. |

### 1.8 Capability H — Internal Mobility

| Target | Class | Notes |
|---|---|---|
| Discover credible lateral / cross-functional candidates | **Missing** | Engine deferred in C6 freeze. JA career edges (`lateral`, `promotion`, `specialist`, `manager`) are the path graph. |
| Honesty: fit ≠ application ≠ selection ≠ employment | **Already excellent** | R5C `mobility_surface` + freeze amendment. |
| Optional Recruiting handoff | **Partially supported** | Explicit handoff descriptor when `pre_hiring` is on. No silent `talent_pool` write. |

### 1.9 Capability I — Trajectory

| Series | Data exists? | Named patterns? |
|---|---|---|
| OKRs | Yes — progress entries + target versions | **Missing** |
| Performance | Yes — C2/C4 snapshots + review population freeze | **Missing** |
| Competencies | Yes — C3 assessments versioned | **Missing** |
| Skills | Yes — `talent_skill_history` + versions | **Missing** |
| Development | Yes — C3 action status over time | **Missing** |
| Readiness | Yes — nomination versions + C5 observations | **Missing** |
| Talent as-of | Yes — `talent_as_of()` | Point-in-time, not pattern labels |

### 1.10 Capability J — Organizational Capability Intelligence

| Question | Class | Notes |
|---|---|---|
| Strongest capabilities / gaps | **Missing** as Intelligence formulas | Wave 5 has population / potential / HiPo / succession coverage. Not skill/capability inventory. |
| Critical capability depends on one person | **Missing** | Compose JA criticality + skills + succession. |
| Skills increasing / decreasing | **Missing** | Skill history exists; no Wave 5 formula. |
| Underutilized capabilities | **Missing** | Needs role-fit + current assignment. |
| What disappears if Person X leaves | **Missing** | Architect toward what-if (L); do not build simulator in V1. |
| Reuse Wave 5 | **Already excellent** (engine) | C1 registry, permission classes, cohort suppression, `assistant_resolve_metric`. C5 projection tables are a **composition smell**, not a second engine — see §16. |

### 1.11 Capability K — Assistant

| Target | Class | Notes |
|---|---|---|
| Domain tools for Talent / OKR / succession / fit | **Missing** | `assistant_capability_catalog` has pre-hire + some post-hire ops + `workforce_analytics`. **No performance/talent tools.** |
| Permission / module / tenant scoped | **Already excellent** (platform) | Catalog pattern is the reuse target. |
| Calculations outside the LLM | **Already excellent** (policy) | Wave 5 already refuses invented metrics. |

### 1.12 Capability L — Future What-If

| Target | Class | Notes |
|---|---|---|
| Person X leaves / cascading gaps / backfills / new branch / retirement / internal vs external | **Missing** (correct for V1) | WFP already has `wfp_scenarios`, demand, gaps, execution handoffs, optional `talent_skills_enabled`. Compose later. Do not make PT0/V1 depend on the simulator. |

### 1.13 Product surfaces (honesty)

| Surface | Class | Notes |
|---|---|---|
| HR Web Performance workspace | **Exists but shallow** | Create/activate objectives, add KRs, reviews, check-ins, calibration. Not an OKR operating system. |
| HR Web Talent workspace | **Exists but shallow** | Overview counts, people, reviews, succession, mobility tab (preferences), 9-box tab. Forms are thin. Sparkles icon is decorative — remove in PT UX (violates “no generic AI sparkles”). |
| Employee App Performance / Talent | **Exists but shallow** | Limited self surfaces; judgments hidden. |
| HR Mobile Performance | **Exists but shallow** | Thin queues. Talent mobile not an enable gate. |
| Setup | **Already excellent** (R6) | Wave 4 Performance + Talent policy cards + effective state. |

---

## 2. REUSE MAP

Exact authorities. PT **reads** these. PT **does not fork** them.

### 2.1 Performance (Wave 4)

| Asset | Path / object | Reuse as |
|---|---|---|
| OKR + goals authority | `wathefni-orchestrator/performance_goals_c1.py` | SoT for objectives, KRs, measures, alignment, progress, target versions |
| Tables | `perf_objectives`, `perf_key_results`, `perf_goals`, `perf_measure_definitions`, `perf_alignment_links`, `perf_target_versions`, `perf_progress_entries` | Live reads; OKR depth extends |
| Review cycles | `performance_reviews_c2.py` | Optional review evidence; **not** OKR cycles |
| Check-ins + competencies + development | `performance_feedback_c3.py` — `perf_check_ins`, `perf_c3_competency_*`, `perf_development_*` | OKR update thread; competency evidence; the only development-plan authority |
| Calibration | `performance_calibration_c4.py` | Sealed outcomes as optional evidence only |
| HTTP / surfaces | `performance_http.py`, `performance_surfaces.py` | Extend; keep `strip_talent()` |
| UI | `apps/wathefni-dashboard/src/posthire/PerformanceWorkspace.tsx` | Deepen; do not replace |
| Setup | `Wave4PerformanceTalentPoliciesCard` `scope="performance"` | Policy only |

### 2.2 Talent (Wave 4)

| Asset | Path / object | Reuse as |
|---|---|---|
| Profile authority | `talent_profile_c5.py` | SoT for dimensions, skills, potential, readiness observations, aspirations |
| Tables | `talent_profiles`, `talent_dimension_facts`, `talent_skills`, `talent_skill_history`, `talent_competency_evidence_maps`, `talent_potential_frameworks`, `talent_potential_assessments`, `talent_readiness_observations`, `talent_performance_evidence_links` | Live evidence |
| Succession / HiPo / 9-box | `talent_succession_c6.py` | SoT for human HiPo, critical roles, plans, nominations, 9-box **projection**, coverage facts |
| Tables | `talent_reviews`, `talent_review_population`, `talent_hipo_designations`, `talent_critical_roles`, `talent_succession_plans`, `talent_successor_nominations`, `talent_succession_coverage_facts`, `talent_nine_box_configs` | Live reads; intelligence overlays |
| HTTP / surfaces | `talent_http.py`, `talent_surfaces.py` | Extend; keep honesty + `strip_employee_judgments` |
| UI | `TalentWorkspace.tsx` | Deepen map / WHY / succession intelligence |
| Permissions | `talent.read`, `talent.manage`, `talent.sensitive`, `talent.review`, `talent.succession` | Do not collapse |

### 2.3 Job Architecture / Learning / WFP (Wave 6)

| Asset | Reuse as |
|---|---|
| `job_architecture_c1.py` — `ja_job_profile`, `ja_job_family`, `ja_level`, `ja_grade`, `ja_career_edge`, `ja_employment_assignment` | Target role identity, career path graph, current/historical assignment. **Never** write eligibility scores onto JA. |
| `learning_development_c2.py` — `ld_completions`, `ld_certifications`, `ld_development_fulfillment_links` | Optional evidence. Completion ≠ verify. |
| `workforce_planning_c7.py` — `wfp_scenarios`, `wfp_demand_items`, `wfp_gaps`, `wfp_execution_handoffs` | Later what-if composition only. Optional `talent_skills_enabled`. |

### 2.4 Intelligence / Assistant / identity

| Asset | Reuse as |
|---|---|
| `hr_intelligence_registry_c1.py` | KPI definitions, formula handlers, publish, evaluate, cohort suppression |
| `hr_intelligence_perf_talent_c5.py` | Existing Perf/Talent semantic keys; add **new** keys for capability intelligence; do not invent a parallel registry |
| `hr_intelligence_surfaces_c6.py` | Drill / explain / snapshot pattern |
| `assistant_capability_catalog.py` + `assistant_resolve_metric` | Tool gating pattern |
| Employees / org / manager scope / `hr_tasks` | One person model. No shadow talent person. |
| Recruiting assessments / interviews | OPTIONAL hire-time import only; never live-merge candidate pool |

### 2.5 What not to reuse

| Tempting asset | Why not |
|---|---|
| Pre-hire `role_fit` / `readiness` scores in `app.py` ranking | Different domain, different math, decorative-adjacent. Talent role-fit must be a new deterministic service over JA + permitted evidence. |
| Recruiting `talent_pool` | Naming boundary is frozen. |
| Wave 5 `hr_intelligence_perf_*` / `hr_intelligence_talent_*` projection tables as SoT | They are Intelligence projections, not Talent SoT. PT person-level reads go to Wave 4/6 live tables. Aggregates go through C1 facts. |
| A new `employees_talent` or blob `talent_score` | Forbidden by C5 CHECK and charter. |

---

## 3. GAP ANALYSIS

What is genuinely needed for the flagship vision — **not** a rewrite.

### 3.1 Must exist (flagship V1)

1. **OKR operating depth** on top of C1: first-class OKR cycle (not a review cycle), alignment tree, check-in/update thread (reuse C3), optional confidence/health, comments, period trajectory, finer visibility, explicit Objective/KR → Talent evidence contract.
2. **Talent Evidence Index** — read-through pointers with provenance class, not copies of other authorities.
3. **Configurable Talent Model** — versioned tenant document: dimensions, allowed evidence sources, scales, optional weights, thresholds, eligibility, output classifications. Produces **derived** classifications only.
4. **Explainability graph** — structured WHY: model version, contributing evidence, missing evidence, human overrides, gaps.
5. **Role requirement sets + fit/readiness engine** — PT-owned, JA-referenced, target-role specific, deterministic, no universal score.
6. **Dynamic Talent Map** — governed lenses + inspectable placements. 9-box remains one lens.
7. **Succession intelligence** — no-successor (exists), plus single-successor risk, concentration, readiness-gap rollup, honest bench formula.
8. **Mobility discovery** — advisory matches from JA edges + permitted evidence; Recruiting handoff remains explicit.
9. **Governed trajectory labels** — few, defined, deterministic.
10. **Assistant read tools** wrapping the deterministic services.

### 3.2 Must not be built as a new system

- Second OKR product
- Second talent profile
- Second development-plan authority
- Second analytics engine
- Universal talent / readiness / role-fit percentage without an explicit model
- Auto-HiPo from 9-box or model
- AI-authored potential, HiPo, readiness, or employment decisions
- Eligibility scores written onto `ja_career_edge`

### 3.3 Additive freeze amendments (not reopenings)

Document in the slice that needs them:

| Authority | Additive change | Why it is not a reopen |
|---|---|---|
| C1 | Optional `okr_cycle_id`; optional confidence on progress entries | Does not change `compute_progress` |
| C3 | Prefer check-ins as OKR update thread; no new progress mutation | Already `linked_subject` allows objective/KR |
| C5 | Allow `objective` / `key_result` on `talent_performance_evidence_links`; optional evidence-index pointer table | Opt-in consume; no potential rewrite |
| C6 | Do **not** auto-write HiPo. New `talent_model_*` tables live beside C6 | Human HiPo remains the only designation SoT |
| Wave 5 C1/C5 | New semantic keys + handlers | Same registry; bench strength may leave `unavailable` only with a published formula |
| JA | None required | Requirement sets are PT-owned and *reference* `ja_job_profile` |

### 3.4 Composition smell (safe debt, not a blocker)

Wave 5 C5 duplicates person-level rows (`hr_intelligence_perf_objectives`, `hr_intelligence_talent_hipo`, …) instead of reading live Wave 4 tables. PT must **not** create a third copy. Person-level intelligence reads Wave 4/6. Aggregates use C1 facts / outbox. Converging C5 projections to read-through is later Wave 5 safe debt, not a PT0 reopen.

---

## 4. TARGET ARCHITECTURE

```text
 Frozen canonical authorities
 Employee/Org · C1 OKRs · C2–C4 Perf · C5 Profile · C6 Succession/HiPo/9-box
 JA · Learning · Assessments · WFP
                │ read-through (no copy)
                ▼
 PT Evidence Index
 provenance: SYSTEM / MANAGER / HR / EMPLOYEE / AI
 (AI = synthesized note, never a fact)
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
 Talent Model  Role Fit   Trajectory
 (derived      (target-   (governed
  class only)   role)      labels)
     │          │          │
     └────┬─────┴────┬─────┘
          ▼          ▼
   Talent Map     Succession /
   + WHY graph    Mobility intel
          │          │
          ▼          ▼
   Wave 5 formulas   Assistant tools
   (aggregates)      (read / explain / deep-link)
          │
          ▼
   Later: What-If  (WFP ∘ Org ∘ JA ∘ Talent ∘ Recruiting)
```

### 4.1 Layer rules

| Layer | May write | Must not write |
|---|---|---|
| Frozen authorities | Their own SoT, as today | Each other’s SoT |
| Evidence Index | Pointers + provenance + permission tags | Skill levels, ratings, HiPo, employment |
| Talent Model run | `talent_model_classifications` + explanation graph | `talent_hipo_designations`, potential assessments, C4 ratings |
| Role fit | `talent_role_fit_evaluations` | JA eligibility scores, universal readiness |
| Talent Map | Placements for a lens+model+as-of | Canonical `employee.box` |
| Assistant | Nothing in V1 (read/explain/deep-link) | Any classification or employment mutation |
| AI narration | `explanation.narrative_*` marked `AI-SYNTHESIZED` | Evidence rows, classifications, scores |

### 4.2 Module composition

- Performance works without Talent (unchanged).
- Talent works without Performance (unchanged).
- Talent works without JA; **Role Fit / JA-backed mobility require JA enabled**.
- Learning / Assessments / Recruiting remain OPTIONAL evidence.
- Intelligence remains the only analytics engine.
- Disabled modules disappear; historical PT objects remain but new runs stop.

---

## 5. TALENT EVIDENCE MODEL

### 5.1 Object

`talent_evidence_ref` (index row, not a fact copy):

| Field | Rule |
|---|---|
| `employee_key` | Canonical employee. No shadow person. |
| `source_module` | `performance` / `talent` / `job_architecture` / `learning` / `assessments` / `recruiting` / `organization` |
| `source_authority` | Exact table/function (e.g. `perf_key_results`, `ld_certifications`) |
| `source_id` + `source_version` | Stable pointer |
| `as_of` | When this evidence was true |
| `evidence_kind` | skill / competency / okr / review_outcome / potential / certification / assignment / assessment / development / aspiration / nomination |
| `provenance_class` | `SYSTEM-DERIVED` \| `MANAGER-ASSESSED` \| `HR-ASSESSED` \| `EMPLOYEE-DECLARED` \| `AI-SYNTHESIZED` |
| `permission_class` | Align with Wave 5 + Talent sensitive flags |
| `consume_contract` | Versioned OPTIONAL contract id (e.g. `okr_as_talent_evidence_v1`) |
| `payload_hash` | Integrity; do not store a second rating |

`AI-SYNTHESIZED` may only point at a narration object, never at a skill/rating/HiPo.

### 5.2 Provenance discipline

| Class | Examples | May drive a derived classification? |
|---|---|---|
| SYSTEM-DERIVED | KR progress, sealed rating, cert valid/expired, JA assignment | Yes, if the model lists that source |
| MANAGER-ASSESSED | Potential assessment (`assessor_role=manager`), check-in judgment | Yes |
| HR-ASSESSED | Potential (`hr`), HiPo designation, succession nomination | Yes |
| EMPLOYEE-DECLARED | Aspiration, mobility preference, claimed skill | Only if the model explicitly allows claims (default: display, not classify) |
| AI-SYNTHESIZED | Narrative WHY | **Never** as a classification input |

Contradictions **coexist** (already C5). The index must not collapse them.

### 5.3 Optional consume contracts (company-configurable, default off except where already on)

| Contract | Default | Effect when on |
|---|---|---|
| `okr_as_talent_evidence_v1` | off | Objective/KR pointers appear on the profile and may be selected by a model |
| `performance_outcome_as_evidence_v1` | existing `performance_evidence_consume` | Sealed C4 / locked C2 only |
| `learning_cert_as_evidence_v1` | off | Valid certs; not completions |
| `learning_completion_as_evidence_v1` | off | Completions as development evidence only |
| `ja_assignment_as_evidence_v1` | on if JA enabled | Role history |
| `recruiting_import_at_hire_v1` | off | One-time consented copy of permitted assessment/interview evidence at hire; still not `talent_pool` |
| `assessment_as_evidence_v1` | off | Named instruments only; never silent potential |

Performance still never becomes potential. OKR attainment still never becomes quality.

---

## 6. CONFIGURABLE TALENT MODEL DESIGN

### 6.1 Why a new object

`talent_potential_frameworks` assesses **potential**.  
`talent_nine_box_configs` projects **two axes**.  
`talent_hipo_designations` is a **human decision**.

None of these is a company-owned *classification model*. Flagship needs a model that can say: “Under **our** v3 model, these people meet the *derived* High Potential *signal*” — without touching the human HiPo record.

### 6.2 `talent_model` (versioned)

```text
talent_model
  model_id, company_code, name_en/ar
  version (immutable once published)
  status: draft | published | deprecated
  output_classifications[]          # e.g. derived_high_potential, derived_watch, none
  dimensions[]                      # each: id, label, scale, input_kind
  evidence_bindings[]               # dimension → allowed evidence_kind + provenance
  derivation                        # none | rules_v1 | weighted_v1
  thresholds[]                      # explicit, inspectable
  eligibility[]                     # e.g. min tenure, exclude contractors — JA/employment facts only
  human_inputs                      # which dimensions require manager/HR assessment
  ai_narration                      # allowed | forbidden (default forbidden in V1)
  published_at, published_by, reason
```

**Derivation modes**

| Mode | When | Precision rule |
|---|---|---|
| `none` | Model is a structured scorecard; humans classify | No system percentage |
| `rules_v1` | Boolean / band rules (if sealed rating ≥ X AND potential ≥ Y AND …) | Labels only, no 91% |
| `weighted_v1` | Company **explicitly** opts into weights | Percentage allowed **only** if every weight, scale, and missing-data rule is stored on that version and shown in WHY |

Missing evidence → `insufficient_evidence`, never a fake 0 or 100.

### 6.3 Outputs (derived, side-by-side)

| Object | Owner | Overwrites |
|---|---|---|
| `talent_model_run` | System, deterministic | Nothing |
| `talent_model_classification` | System, for `(employee, model_version, as_of)` | **Never** `talent_hipo_designations` |
| Human HiPo | HR/facilitator | Unchanged |
| Potential assessment | Manager/HR | Unchanged |

UI language:

- “Designated HiPo” = C6 human record  
- “Meets derived High Potential signal (Model v3)” = model output  
- Never show a single “HiPo: 91%”

A company may later configure “suggest designation” (human still writes C6). V1 does not auto-designate.

### 6.4 No universal Talent score

A model may output **named classifications** and, only in `weighted_v1`, **per-dimension** contributions that sum in WHY. There is still no `talent_score` on the employee.

---

## 7. OKR DEPTH DESIGN

### 7.1 Keep C1 semantics

Do not rename OKRs to goals. Do not store OKRs as `perf_goals.goal_kind`. KPI / milestone / development goals remain siblings.

### 7.2 New / deepened concepts (PT-owned or C1-additive)

| Concept | Design |
|---|---|
| **OKR cycle** | New `perf_okr_cycles` (C1-additive table): period, timezone, status `draft/open/closed`, snapshot of scoring policy. **Distinct from C2 review cycles.** An OKR cycle may exist with reviews off. |
| **Alignment tree** | Read `perf_alignment_links` + scopes. UI: company → department → team → individual. Links are voluntary; no score inheritance. |
| **Check-in / updates** | Reuse C3 check-ins linked to objective/KR. Add a thin “OKR update” presentation (progress note + optional confidence). Still must not auto-write `current_value`. |
| **Confidence / health** | Optional field on a progress entry or check-in: `high` / `medium` / `low` (or 1–3). **Not** a second progress %. Company may disable. |
| **Comments** | Threaded comments as C3 notes or a thin `perf_okr_comments` scoped to objective/KR. Visibility follows OKR visibility. |
| **Scoring policy** | Versioned document on the cycle: roll-up = weighted KR average (default, already shipped); optional committed vs stretch KR tags. Changing policy does not rewrite closed cycles. |
| **Visibility** | Additive: `visibility` on objective (`owner_manager` / `org_unit` / `company`). Default = today’s manager-scope behavior. |
| **Trajectory** | For each closed cycle, store roll-up snapshot. Pattern engine (PT6) reads snapshots. |
| **Talent evidence** | Additive C5 subject types `objective` / `key_result` under opt-in contract. Achievement still ≠ quality. |

### 7.3 UX (LESS IS MORE)

1. **My / team OKRs** — current cycle, health, one progress number per Objective (from roll-up).  
2. **Alignment** — one tree, opened on request.  
3. **One Objective** — KRs, updates, comments, versions.  
4. No KPI-card wall. No second dashboard of decorative percentages.

---

## 8. ROLE FIT / READINESS DESIGN

### 8.1 Requirement set (PT-owned, JA-referenced)

`talent_role_requirement_set`

- `job_profile_id` (JA) **or** `critical_role_id` (C6)  
- `version`, published snapshot  
- requirements: `{ kind: competency|skill|certification|experience|assessment|performance_evidence|development, id, level_or_rule, required|preferred }`  
- May **import** JA `optional_requirements` lists as a starting draft  
- Must **not** write scores back to JA  

### 8.2 Evaluation

`talent_role_fit_evaluation` for `(employee_key, requirement_set_version, as_of)`:

```text
for each requirement:
  find permitted evidence (index)
  compare to rule (deterministic)
  emit: met | partial | gap | not_assessed | not_permitted
readiness_band = company framework
  (reuse C6: ready_now / ready_lt_1y / ready_1_2y / longer_term / not_ready / unassessed)
  from gap severity + development progress — rules published on the set
```

**No universal employee readiness.**  
**No 91% role fit** unless the published set uses `weighted_v1` and WHY lists every term.

Experience uses JA assignment history + employment dates — not free-typed years unless HR-assessed.

Assessments participate only when `assessment_as_evidence_v1` is on and the instrument is named on the set.

### 8.3 Readiness vs fit

| Term | Meaning |
|---|---|
| Role fit | Evidence vs this requirement set (capability match) |
| Readiness | Fit + time-to-gap-close + (optional) performance evidence + development — **for this target** |
| Succession readiness | C6 human band on a nomination; may be **informed** by a fit evaluation, never auto-overwritten in V1 |

---

## 9. TALENT MAP / EXPLAINABILITY DESIGN

### 9.1 Map is a query, not a SoT

`talent_map_lens`

| Field | Rule |
|---|---|
| `axis_x`, `axis_y` | Dimension ids from a published model **or** built-in governed axes |
| `built_in` | `perf_x_potential` (today’s 9-box), `potential_x_readiness`, `fit_x_readiness` (requires a target role), `growth_x_contribution` (requires trajectory + OKR/perf evidence) |
| `model_id` + `model_version` | Required when not the frozen 9-box config |
| `as_of` | Snapshot; changing the model does not rewrite history |
| `target_role_id` | Required for any readiness/fit axis |

`capability × criticality` is V1-optional: X = capability coverage, Y = JA/C6 criticality. Needs PT6 formulas or a scoped query — do not fake a heat map.

Customer-defined lenses: only from published model dimensions. No free-typed axes.

### 9.2 Placement

`talent_map_placement`

- employee, lens, cell/band, `evaluation_id`s used  
- `why_id` → explanation graph  
- `insufficient_evidence` placements are **shown as unknown**, not stuffed into a middle box  

9-box remains `project_nine_box()` for the built-in perf×potential lens. Do not replace that function; the map **calls** it.

### 9.3 Explanation graph

`talent_explanation`

```text
subject: classification | placement | nomination | role_fit
model_id + version
inputs[]: evidence_ref, contribution (label or weight), provenance_class
missing[]: required evidence not present
overrides[]: human HiPo / nomination / potential that differs from derived signal
gaps[]: from role-fit or succession
narrative_en / narrative_ar: optional, AI-SYNTHESIZED, regenerate-able, never stored as evidence
```

Assistant and UI use the same graph. AI may write `narrative_*` only.

### 9.4 UX

- Overview: one lens, one sentence of coverage honesty, people as quiet marks.  
- Select a person: side panel with WHY (inputs / missing / human override).  
- “Show evidence” opens the profile — not a second spreadsheet.  
- Lens switch is a single control, not a filter wall.  
- Empty / forbidden / unavailable use R4 truth states.

---

## 10. SUCCESSION / MOBILITY DESIGN

### 10.1 Succession intelligence (overlay on C6)

Keep C6 as SoT for critical roles, plans, nominations, human readiness.

Add **derived facts** (Wave 5-consumable, like today’s coverage facts):

| Fact | Definition (governed) |
|---|---|
| `uncovered_critical_role` | Already exists |
| `single_successor_risk` | Active plan with exactly one active nomination |
| `no_ready_now` | Successors exist but none `ready_now` |
| `concentration_risk` | Same `employee_key` is active successor on ≥ N critical roles (N company-configured, default 3) |
| `bench_strength_v1` | **Only** if published: e.g. count of `ready_now` + `ready_lt_1y` per role, **not** a 0–100 score. Replaces Wave 5 `unavailable` for companies that publish this formula. |
| `current_holder` | Resolved from JA assignment or org position — displayed, not a second employment SoT |

Successor “stronger/weaker evidence” in V1 = **explainable comparison** of two nomination WHY graphs (fit eval + readiness band + evidence completeness). **Not** a silent rank score. Ordering may be user-chosen (readiness band, then evidence completeness).

### 10.2 Mobility

`talent_mobility_match` (advisory):

- Inputs: JA career edges from current `ja_employment_assignment`, skills/competencies/certs/interests, optional role-fit vs destination profile  
- Output: destination profile, edge type (`lateral` / `promotion` / …), evidence, gaps  
- `is_not_application: true`  
- Explicit action: “Refer to internal opportunity” → existing Recruiting handoff only if module on  

Do not create candidates. Do not write employment.

---

## 11. TRAJECTORY / CAPABILITY INTELLIGENCE DESIGN

### 11.1 Trajectory patterns (deterministic, few)

Computed over **closed** periods only. Each pattern has a published rule on `talent_trajectory_policy` (company may disable labels entirely).

| Label | Illustrative governed rule (publish in PT6; do not invent in UI before then) |
|---|---|
| `stable_high_performance` | ≥ N consecutive closed cycles with sealed rating in company “high” band |
| `accelerating` | Roll-up or sealed rating increased across last N closed periods by published delta |
| `declining` | Symmetric decrease |
| `emerging` | First period meeting high band after below-band history, or first accepted potential ≥ threshold |
| `stalled_development` | Open development actions overdue beyond SLA with no completion in window |

If data are insufficient → no label (not “stable”).  
Labels are `SYSTEM-DERIVED` observations, not potential and not HiPo.

### 11.2 Capability intelligence (Wave 5 formulas, not a new engine)

New semantic keys (names illustrative):

| Key | Question | Sources |
|---|---|---|
| `talent.capability_coverage` | Where are we strong/gapped vs a published requirement set? | Fit evaluations + JA |
| `talent.single_person_capability` | Which required capabilities have one verified holder? | Skills/certs + critical roles |
| `talent.skill_direction` | Which skill_codes increased/decreased in window? | `talent_skill_history` |
| `talent.underutilized_capability` | Verified skill/competency not used on current JA assignment vs requirement sets | Evidence index + JA |
| `talent.holder_dependency` | What capability coverage drops if employee X is excluded? | Same as coverage, minus X — **this is the V1-safe slice of “what if X leaves”** without a WFP simulator |

Reuse C1: permission_class `talent_sensitive`, cohort suppression, published formulas, `insufficient_data` / `suppressed`.  
Do **not** implement `talent.bench_strength` as a black box — only the transparent formula in §10.1.

---

## 12. ASSISTANT TOOL DESIGN

### 12.1 Tools (read-only V1)

All fail closed on module / permission / tenant / manager scope / sensitive flags. Each tool **calls a deterministic service** and returns structured WHY + deep links.

| Tool | Answers | Service |
|---|---|---|
| `list_role_fit_candidates` | Strongest candidates for Role X, and why | Role-fit evaluations + explanation graph |
| `list_uncovered_critical_roles` | Which critical roles have no ready successor | C6 + intelligence facts |
| `list_model_classifications` | Who meets derived signal under configured model | Model run |
| `explain_talent_classification` | Why is X HiPo / derived-HiPo / not ready | Explanation graph (human vs derived distinguished) |
| `list_capability_gaps` | Where are capability gaps | Wave 5 evaluate |
| `list_succession_replacements` | Who could replace X | Nominations where X is holder + mobility matches |
| `get_okr_alignment` | How do X’s OKRs align this cycle | C1 + alignment tree |
| `workforce_analytics` | Existing | Keep; add new semantic keys only |

Do not add `designate_hipo` or `set_readiness` tools in V1.

### 12.2 Catalog

Extend `assistant_capability_catalog.CAPABILITY_IDS` with `posthire_performance`, `posthire_talent` gated on modules `performance` / `talent` and the existing Talent permission split. Mutations stay out.

---

## 13. FLAGSHIP V1 vs LATER ADVANCED

| Capability | Flagship V1 | Later |
|---|---|---|
| OKR depth | Cycles, alignment tree, updates/confidence/comments, history, optional Talent evidence | Committed/stretch policies, integration-sourced KRs at scale, employee social OKR feed |
| Evidence index | Read-through + 4–6 consume contracts | Recruiting import-at-hire, psychometrics library, external integrations |
| Talent model | One published model, rules or explicit weights, derived classifications | Multiple concurrent models, calibration of models, suggest-HiPo workflow |
| Talent Map | 3 built-in lenses + 9-box + WHY drawer | Customer dimensions, capability×criticality heat, org overlay |
| Role fit | One target role at a time, deterministic gaps | Batch org-wide fit, % only with weighted_v1 |
| Succession intelligence | Uncovered, single-successor, concentration, no-ready-now, honest bench counts | Networked succession, retirement waves |
| Mobility | Advisory matches + optional Recruiting handoff | Internal marketplace |
| Trajectory | 5 governed labels, off by default until policy published | More labels only with new published rules |
| Capability intelligence | 4–5 Wave 5 formulas including holder-dependency | Full what-if |
| Assistant | Read/explain/deep-link tools | Mutations if separately chartered |
| What-if simulator | Architected only; holder-dependency formula is the taste | Compose WFP scenarios + cascading succession + internal vs external coverage |
| UX | Overview → explore → evidence | Still no Excel-first mode |

---

## 14. SERIAL IMPLEMENTATION SLICES PT1 → PTn

Do not start PT1 until this PT0 is owner-accepted. One slice at a time. Each slice: authority + HTTP + HR Web (EN/AR+RTL) + Setup if needed + tests + freeze amendment + **stop for owner review**.

| Slice | Name | Ships | Does not ship |
|---|---|---|---|
| **PT1** | OKR depth + Evidence Index | OKR cycles, alignment tree, C3-based updates, optional confidence/comments, C5 objective/KR evidence contract, evidence index v1 | Talent model, map, role fit |
| **PT2** | Configurable Talent Model + WHY | `talent_model`, run, derived classification, explanation graph, Setup model editor (simple) | Auto-HiPo, map UX |
| **PT3** | Role Fit & Readiness | Requirement sets (JA-referenced), evaluations, target-specific readiness **suggestion** (human still owns C6 band) | Universal %, JA writes |
| **PT4** | Dynamic Talent Map | Lenses, placements, WHY drawer, 9-box as one lens | Filter walls, customer free-typed axes |
| **PT5** | Succession intelligence + Mobility discovery | Risk facts, bench counts, mobility matches, Recruiting handoff unchanged | Simulator, silent candidates |
| **PT6** | Trajectory + Capability Intelligence | Trajectory policy + labels; new Wave 5 keys including holder-dependency | New analytics product |
| **PT7** | Assistant tools | Catalog + read tools over PT1–PT6 | Mutations |
| **PT8+** | What-if (advanced) | WFP ∘ JA ∘ Talent ∘ Succession ∘ Recruiting scenarios | Not flagship V1 |

R7 Production Readiness resumes when the owner unpauses it — **not** automatically after PT0.

---

## 15. TEST / EVAL PLAN

Every PT slice inherits R2/R3/R4/R5A/R6 honesty and Wave 4 modularity proofs.

### 15.1 Contract tests (mandatory)

- Performance OFF → Talent still works; OKR evidence hidden  
- Talent OFF → Performance still works; no Talent vocabulary (`strip_talent`)  
- JA OFF → Role fit / JA mobility unavailable (honest), succession still works  
- Learning OFF → no cert evidence  
- Model run never writes `talent_hipo_designations` or potential  
- 9-box / lens change does not rewrite historical placements or assessments  
- `weighted_v1` percentage refused unless methodology snapshot is complete  
- Missing current / missing evidence ≠ 100% / ≠ stuffed into a middle box  
- `AI-SYNTHESIZED` cannot appear as a classification input  
- Tenant isolation + manager scope + `talent.sensitive`  
- Recruiting `talent_pool` untouched  
- Wave 5 cohort suppression on new formulas  
- Assistant tool hidden when module/permission off  
- EN+AR+RTL on new surfaces  
- Disable contract: stop new runs, hide surfaces, preserve history  

### 15.2 Eval (flagship quality, not just green tests)

| Eval | Pass |
|---|---|
| WHY completeness | Every V1 placement/classification has model version + inputs + missing |
| Distinction quiz | Fixture where high OKR + high rating + low potential + no HiPo — UI and Assistant must not conflate |
| Lens switch | Same population, two lenses, two WHYs, same underlying facts |
| Holder-dependency | Removing person X changes coverage formula; employment unchanged |
| No sparkle | UI copy/review: no decorative AI, no universal score |

### 15.3 Qualification shape

Mirror R5: local unit → staging DB journeys → live staging namespaces → Wave 4/5/6 + R2–R6 regressions → evidence pack → freeze amendment → **stop**.

---

## 16. ARCHITECTURAL RISKS

| Risk | Severity | Mitigation |
|---|---|---|
| Building a second Talent/OKR system “because the UI is thin” | High | Adapters only; new tables are overlays |
| Derived classification collapses into HiPo | High | Separate table; UI copy; tests; C6 CHECK remains |
| Fake precision (91% fit) | High | Percentage only in `weighted_v1` with published methodology; default rules/labels |
| Wave 5 C5 projection drift (third copy) | Medium | PT reads live Wave 4/6; aggregates via C1; C5 read-through is later safe debt |
| JA eligibility scores sneak in | High | Requirement sets are PT-owned; JA `create_career_edge` still rejects scores |
| Pre-hire ranking math reused as Talent fit | High | Explicit ban; new service |
| Trajectory labels without published rules | Medium | Labels off until policy published; insufficient → no label |
| Assistant invents WHY | High | Tool returns graph; LLM narrates only; mutations out |
| Filter-wall / Excel UX | Medium | Charter UX; PT4 review gate |
| Scope creep into what-if / WFP | Medium | PT8+ only; V1 holder-dependency formula is enough |
| Additive C1/C5 amendments treated as silent hotfixes | Medium | Each slice writes a freeze amendment |
| Sparkles / decorative AI in TalentWorkspace | Low | Remove in PT4 UX; not an authority issue |
| R7 pause forgotten | Process | This document: R7 remains paused until owner unpauses |

---

## 17. OWNER DECISIONS REQUESTED

PT0 does not implement. Please accept or amend:

1. **Overlay, not reopen** — proceed PT1+ without reopening Wave 4 C1–C6 math.  
2. **Derived ≠ designated** — model “High Potential” is never C6 HiPo.  
3. **OKR cycle ≠ review cycle** — first-class OKR cycle in PT1.  
4. **Role-fit requires JA** (optional integration); succession does not.  
5. **Flagship V1 = PT1–PT7**; what-if = PT8+.  
6. **R7 stays paused** until you unpause.  
7. Any amendment to V1 scope (e.g. include capability×criticality heat in PT4, or allow suggest-HiPo in PT2).

---

## 18. STOP

PT0 is complete. **No production code was written.**

Do not begin PT1.  
Do not begin R7.  
Do not invalidate R2–R6 or R5 freezes.

Owner review next.
