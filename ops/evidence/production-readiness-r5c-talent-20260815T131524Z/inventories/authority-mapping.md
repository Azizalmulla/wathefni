# R5C authority mapping

HTTP and clients are adapters. No second Talent model. No frontend `talent_score`. Performance does not determine Talent truth.

| Product concept | Canonical library | Persistence | Adapter |
|---|---|---|---|
| Talent profile | `talent_profile_c5` | `talent_profiles` | `/profiles`, `/app/talent/profile` |
| Evidence / signals | C5 dimension facts | `talent_dimension_facts` + history | `/evidence` |
| Skills | C5 | `talent_skills` + `talent_skill_history` | `/skills`, `/app/talent/skills` |
| Potential framework / assessment | C5 | `talent_potential_frameworks`, `talent_potential_assessments` | `/potential/*` |
| Optional Performance evidence | C5 link only | `talent_performance_evidence_links` | `/performance-evidence` |
| Readiness observation | C5 (not a nomination) | `talent_readiness_observations` | `/readiness` |
| Employee aspirations / mobility | C5 `employee_declared` | dimension facts | `/app/talent/aspirations`, `/app/talent/mobility` |
| Talent review | `talent_succession_c6` | `talent_reviews` + population snapshot | `/reviews` |
| HiPo | C6 explicit decision | `talent_hipo_designations` | `/hipo` |
| Critical / target role | C6 | `talent_critical_roles` | `/critical-roles` |
| Succession plan / slate | C6 | `talent_succession_plans`, `talent_successor_nominations` | `/plans`, `/succession` |
| Target-specific readiness | C6 nomination `readiness` | per plan + employee | `/plans/{id}/nominations` |
| 9-box | C6 `project_nine_box` | config only (`talent_nine_box_configs`) | `/nine-box`, `/nine-box/project` |
| Development context | `performance_feedback_c3` | `perf_development_plans` / actions | `/development/{employee_key}` |
| Recruiting handoff | catalog `pre_hiring` when ON | none in Talent | mobility `handoff`; `writes_talent_pool=false` |

## Frozen rules preserved

- Performance ≠ Talent. `strip_talent()` on Performance payloads unchanged.
- High performer is not HiPo. Potential is not HiPo. No automatic promotion.
- No master Talent score. Dimensions stay distinct.
- 9-box is projection, not SoT. `is_canonical_employee_state=false`. `does_not_imply_hipo=true`.
- Readiness is target-specific. `global_readiness_score` is always null.
- Recruiting `talent_pool` isolated. Mobility interest is not an application.
- Job Architecture not required. Learning not required. C3 remains the only development-plan authority.
- Employee payloads run through `strip_employee_judgments()`.

## Runtime gate

Commercial key: `talent`. Triple gate: env flag + allowlist + company settings.

After R5C, empty allowlist + `customer_enableable` admits via `talent_runtime_allowlist_admits`. Kill switch and `WATHEFNI_TALENT_*` still win.
