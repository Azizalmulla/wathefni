# PERFORMANCE & TALENT INTELLIGENCE FLAGSHIP V1

**Status:** `PERFORMANCE_TALENT_INTELLIGENCE_FLAGSHIP_V1_FULL_PASS`  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**PT0:** `PERFORMANCE_TALENT_INTELLIGENCE_PT0_DESIGN_ACCEPTED`  
**PT1:** `PT1_OKR_EVIDENCE_FULL_PASS` — OWNER ACCEPTED / FROZEN  
**Paused throughout:** Production Readiness R7  
**Do not begin:** PT8, R7, opportunistic Talent features  

**STOP FOR OWNER REVIEW.**

Evidence: `ops/evidence/performance-talent-intelligence-flagship-v1-20260815T225117Z/`

---

## 0. Verdict

PT1–PT7 each have an authority contract, targeted qualification, evidence directory, FULL_PASS stamp, and freeze amendment. Each slice was frozen before the next started. PT0 architecture was not reopened. Wave 4 C1–C6 math/state was not reopened. No second source of truth was introduced. No new security/privacy/tenant-isolation defect was found that required changing an accepted owner decision.

Flagship evals 1–9 passed on staging (`PT_FLAGSHIP_EVALS_DB_PASS`, 37/0).

R7 remains paused. PT8 is not started.

---

## 1. PT1–PT7 stamps

| Slice | Stamp | Qualify | Evidence |
|---|---|---|---|
| PT1 | `PT1_OKR_EVIDENCE_FULL_PASS` (owner accepted) | `ops/qualify-pt1-okr-evidence.sh` | `ops/evidence/pt1-okr-evidence-20260815T221631Z/` |
| PT2 | `PT2_TALENT_MODELS_WHY_FULL_PASS` | `ops/qualify-pt2-talent-models.sh` | `ops/evidence/pt2-talent-models-20260815T222914Z/` |
| PT3 | `PT3_ROLE_FIT_READINESS_FULL_PASS` | `ops/qualify-pt3-role-fit.sh` | `ops/evidence/pt3-role-fit-20260815T223405Z/` |
| PT4 | `PT4_DYNAMIC_TALENT_MAP_FULL_PASS` | `ops/qualify-pt4-dynamic-talent-map.sh` | `ops/evidence/pt4-talent-map-20260815T224352Z/` |
| PT5 | `PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS` | `ops/qualify-pt5-succession-mobility.sh` | `ops/evidence/pt5-succession-mobility-20260815T224503Z/` |
| PT6 | `PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_FULL_PASS` | `ops/qualify-pt6-trajectory-capability.sh` | `ops/evidence/pt6-trajectory-capability-20260815T224724Z/` |
| PT7 | `PT7_ASSISTANT_TALENT_INTELLIGENCE_FULL_PASS` | `ops/qualify-pt7-assistant-talent.sh` | `ops/evidence/pt7-assistant-talent-20260815T224957Z/` |

Freeze amendments live beside each stamp under `ops/PTN_*_FREEZE_AMENDMENT.md`.

---

## 2. Architecture / reuse proof

PT remains an overlay/composition programme. New tables and services **read** frozen authorities and write only new inspectable objects.

| Authority | Reused as | Not replaced by |
|---|---|---|
| Performance C1 OKR math | PT1 cycles/alignment + PT6 closed-period history | No Performance 2.0 |
| Talent C5 profile / potential / skills | PT2 dimensions, PT3 evidence, PT4 facts, PT6 holders | No Talent 2.0, no second employee profile |
| Talent C6 HiPo / succession / 9-box | Human designation + slate SoT; 9-box is one PT4 lens | No automatic HiPo, no second holder record |
| Job Architecture | Optional requirement import + career edges | PT never writes fit/eligibility back to JA |
| Learning | Optional evidence only | No auto-verify |
| Wave 5 registry/evaluator | PT6 `register_formula_handler` only | No second analytics engine |
| Recruiting `talent_pool` | Explicit mobility handoff only | No silent candidate / application |
| Canonical employee/employment/org | Holder + org filters from employment/profile | No second employee SoT |
| Assistant | PT7 tools call PT services | No prompt-side Talent math |

Module independence preserved: Talent works Performance OFF, JA OFF, Recruiting OFF, Learning OFF.

---

## 3. Evidence / provenance matrix

| Kind | Canonical source | Consume path | Missing behaviour |
|---|---|---|---|
| Human Potential | C5 assessments | PT2 `human_potential` dimension | `insufficient_evidence` if required and absent |
| Designated HiPo | C6 designations | PT2/PT4/PT7 read only | Stays not designated |
| Performance outcome | C5 dimension facts / C1 | PT2 optional; PT4 axis | Unknown — never forced middle |
| OKR progress | PT1 cycles + C1 rollup | Opt-in consume contract; PT6 closed periods only | No trajectory label without history |
| Skills | C5 `talent_skills` | PT3 requirement outcomes; PT6 holders | `not_assessed` / `not_permitted` |
| Role fit | PT3 evaluations | PT4 lens; PT5 mobility WHY | `unavailable` if JA required and JA OFF |
| Human readiness | C6 nominations | Authoritative where present | Fit suggestion never overwrites |
| Trajectory | PT6 published policy | Closed comparable periods | No label if unpublished or short history |
| WHY graph | PT2/PT3/PT4/PT6 stored JSON | UI + Assistant | Graph is deterministic; AI may narrate only |

AI-SYNTHESIZED index rows cannot classify. Missing evidence is never coerced to 0 or 100%.

---

## 4. Configurable model proof (PT2)

- Versioned `talent_model` + immutable published versions
- Configurable dimensions, permitted evidence, scales, thresholds, eligibility, `rules_v1`, optional explicit `weighted_v1`
- `weighted_v1` refused unless every weight is explicit and weights sum to 1
- Missing-data policy: `insufficient` | `exclude_renormalize`
- Derived High Potential signal ≠ designated HiPo
- Default signal requires human potential in `{high, expanding, enterprise}` — OKR/perf cannot mint it
- WHY includes model/version, consumed/excluded/missing, provenance, rules/weights, human overrides, `contradictions_reconciled: false`

---

## 5. WHY consistency proof

Flagship eval 3: the same Sarah evaluation’s `model_id` appears in:

- PT2 `evaluate_employee` WHY
- PT2 `get_why` (Talent Profile path)
- PT4 placement WHY pointer
- PT7 `explain_talent_classification` (`pt2.get_why`)

Assistant message names model/version and does not claim designated HiPo.

---

## 6. Role-fit proof (PT3)

- Employee → target JA/critical role → published requirement set → permitted evidence → `met` / `partial` / `gap` / `not_assessed` / `not_permitted`
- Overall: `strong_fit` / `partial_fit` / `gaps` / `not_assessed` / `unavailable`
- Role fit ≠ readiness ≠ promotion eligibility
- Human C6 readiness remains authoritative; deterministic suggestion never writes C6
- JA OFF + JA-linked set → `unavailable`; Talent-only (critical-role) sets still work
- Flagship eval 2: missing IFRS skill → `not_assessed`, suggestion `unassessed`, no 0% / 100% / `not_ready`

---

## 7. Talent Map proof (PT4)

- Lenses: Performance × Potential, Potential × Readiness, Role Fit × Readiness, Growth × Contribution
- 9-box remains C6 `project_nine_box()` as one derived lens — not the product
- One lens selector; progressive org filters from `employees.profile`
- Unknown stays unknown; `forced_middle=false`
- Flagship eval 4: lens switch keeps Sarah’s potential=`high` and designated HiPo=`false`
- EN/AR/RTL Map tab on the existing Talent workspace
- Growth × Contribution stays unknown until a PT6 label exists

---

## 8. Succession / mobility proof (PT5)

- Overlay on C6: uncovered, zero ready-now, single-successor, honest bench counts, concentration (N=3)
- No second holder record; `bench_score=None`; `master_rank_score=None`
- Flagship eval 6: one ready successor → single-successor risk; successor_count=1; no invented candidates
- Mobility matches are advisory (`is_not_application`, `candidate_created=false`, `employment_mutated=false`)
- Flagship eval 7: discover + refer does not create an application
- Talent works Recruiting OFF; what-if remains PT8+

---

## 9. Trajectory proof (PT6)

- No label without a published company policy
- Closed OKR periods only; default minimum 2
- Insufficient history → no label + WHY
- Labels: accelerating, stable high performance, declining, emerging, stalled development
- Does not overwrite Performance / Potential / HiPo / readiness

---

## 10. Wave 5 capability-intelligence proof

PT6 registers additive handlers only:

- `talent_capability_coverage`
- `talent_single_person_capability`
- `talent_skill_direction` (honest `insufficient_data` until a closed skill window)
- `talent_underutilized_capability` (honest `insufficient_data` until JA assignment + requirement set)
- `talent_holder_dependency`

Wave 5 product unit still `WAVE5_PRODUCT_UNIT_PASS`. Frozen C5 `FORMULA_KINDS` / `ALL_SEMANTIC_KEYS` were not mutated.

Flagship eval 8: unique verified skill becomes vulnerable under analytic exclusion; `employees.employment_status` stays `active`; baseline coverage unchanged after the call.

---

## 11. Assistant grounding proof (PT7)

Tools call PT2/PT3/PT5/PT6/PT1. No mutation tools are registered. Flagship eval 9: “why is Sarah classified this way?” uses the authorized WHY graph, names model/version, and does not claim designated HiPo.

---

## 12. Module optionality

| Module OFF | Honest behaviour |
|---|---|
| Performance | Talent models still evaluate human potential; OKR consume stays opt-in |
| Job Architecture | JA-linked role fit `unavailable`; Talent-only sets continue |
| Recruiting | Mobility remains advisory; handoff returns `recruiting_off`; no candidate |
| Learning | No auto-verify; Talent continues |
| Wave 5 | PT overlays still store WHY; capability KPIs simply are not published |

---

## 13. Permission / tenant negatives

- Live Talent routes (`/models`, `/map`, `/succession-intelligence`, holder-dependency) return 401/403/503 unauthenticated
- PT2/PT3 staging journeys include tenant isolation (other-company rows not visible)
- Assistant tools inherit Talent runtime gate + existing permission map
- Sensitive Potential/HiPo remain behind `talent.sensitive`
- Employee surfaces continue to strip HiPo/potential judgments (R5C)

---

## 14. EN / AR / RTL

HR Web Talent workspace tabs (Models, Role fit, Map) ship bilingual copy. PT2–PT6 status labels have EN/AR pairs. Map pane uses `dir={isAr ? 'rtl' : 'ltr'}`. Dashboard 89/481 and mobile composition (71) passed at each freeze that ran full vitest, including PT7.

---

## 15. Comprehensive regressions (PT7 freeze)

Local units that stamped:

- PT1–PT7
- Waves 1–6 product acceptance
- R2 security, R3 data safety, R4 truth-in-UI
- R5A honesty, R5B Performance, R5C Talent, R5D JA, R5E Learning
- R6 Setup self-service
- JA C1 unit
- Recruiting requisitions Wave 1 (boundary)

Staging: PT7 Assistant DB + flagship evals 1–9.  
Live: staging health 200; Talent routes not public.  
Dashboard: 89 files / 481 tests. Mobile composition: 71 checks.

---

## 16. Flagship evals 1–9

| # | Case | Result |
|---|---|---|
| 1 | High OKR/perf + low human Potential + not HiPo | All four preserved; contradiction not reconciled |
| 2 | Target role lacks skill evidence | `not_assessed` / `unassessed`; no 0% / 100% / `not_ready` |
| 3 | WHY in Profile, Map, Assistant | Same `model_id` graph |
| 4 | Lens switch | Same canonical facts; projection only |
| 5 | Derived High Potential signal | Employee remains not designated HiPo |
| 6 | One ready successor | Single-successor risk; no invented candidate |
| 7 | Strong lateral / interest match | Advisory only; no application |
| 8 | Unique capability holder excluded | Coverage facts change; employment not mutated |
| 9 | “Why is Sarah high potential?” | Authorized WHY; not claimed as designated HiPo |

---

## 17. Genuine blockers

None. PT0 architecture held. No Wave 4 C1–C6 reopen. No second SoT. No owner-decision change required.

---

## 18. Safe debt (V1)

- Models / role-fit / trajectory publish UIs are thin HR surfaces, not full studios
- Growth × Contribution map lens is unlabeled until a PT6 policy+history exists
- Skill-direction and underutilized-capability Wave 5 handlers honestly return `insufficient_data`
- Holder lookup is employment profile jsonb + optional JA peek
- Mobility without JA edges seeds from declared interest
- Map is people-list + WHY drawer, not a visual 2D canvas
- Assistant is tool-grounded read/explain, not a new conversational product

---

## 19. PT8+ roadmap (separate — not started)

The following remain **out of V1** and must not be started from this stamp:

- Full cascading organizational what-if / “if this person leaves” simulation beyond analytic holder-dependency
- Customer-published weighted methodologies that mathematically emit a 91% fit (only if they deliberately publish one)
- Closed skill-history windows and JA assignment×requirement underutilization
- Visual 2D Talent Map canvas
- Model studio / trajectory policy designer
- Any governed ML that would be allowed to *source* potential, HiPo, readiness, role fit, succession, or trajectory
- R7 Mobile Keyboard / Native Safety (still paused)

---

## 20. Stop

`PERFORMANCE_TALENT_INTELLIGENCE_FLAGSHIP_V1_FULL_PASS`

Flagship V1 is frozen. **Owner review is required before any next programme step.**

Do not start PT8.  
Do not resume R7.  
Do not add another Talent feature opportunistically.
