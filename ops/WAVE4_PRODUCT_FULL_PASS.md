# WAVE4_PRODUCT_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-12 — Wave 4 remains **FROZEN**  
**Date:** 2026-08-12  
**Stamp:** `WAVE4_PRODUCT_FULL_PASS`  
**Evidence:** `ops/evidence/wave4-product-acceptance-20260812T083316Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE4_PERFORMANCE_TALENT_BUILD_CHARTER.md` (`WAVE4_PERFORMANCE_TALENT_CHARTER: APPROVED`)  
**Qualify:** `ops/qualify-wave4-product-acceptance-staging.sh`  
**Freeze:** `ops/WAVE4_PRODUCT_FREEZE.md`

## Prior frozen slices (do not reopen)

| Slice | Stamp | Evidence |
|---|---|---|
| C1 | `PERFORMANCE_GOALS_FULL_PASS` ACCEPTED | `ops/evidence/performance-goals-c1-20260811T215044Z` |
| C2 | `PERFORMANCE_REVIEWS_FULL_PASS` ACCEPTED | `ops/evidence/performance-reviews-c2-20260812T063543Z` |
| C3 | `PERFORMANCE_FEEDBACK_COMPETENCIES_FULL_PASS` ACCEPTED | `ops/evidence/performance-feedback-c3-20260812T064217Z` |
| C4 | `PERFORMANCE_CALIBRATION_DEV_FULL_PASS` ACCEPTED | `ops/evidence/performance-calibration-c4-20260812T080424Z` |
| C5 | `TALENT_PROFILE_FULL_PASS` ACCEPTED | `ops/evidence/talent-profile-c5-20260812T081339Z` |
| C6 | `TALENT_SUCCESSION_MOBILITY_FULL_PASS` ACCEPTED | `ops/evidence/talent-succession-c6-20260812T081940Z` |

## What C7 proved

### Full Performance path

Objective + measurable KRs → alignment → progress/evidence → review cycle (frozen policy/population) → self → manager → 360 (threshold + raw protection) → check-in + C3 development → deterministic pre-calibration → governed calibration → SoD lock → original layers intact; history survives later Setup policy edits.

### Full Talent path (Performance can be absent)

Canonical employee Talent identity → aspiration → skill claim/verify → potential without Performance → optional Performance evidence consume (does not become potential) → Talent Review lock → explicit HiPo → optional 9-box projection (not SoT; top-right ≠ HiPo) → critical role → multiple successors with target readiness → C3 development linkage → Wave 5 coverage facts.

### Modularity matrix

goals_only · reviews_plus_goals · reviews_without_formal_goals · performance_full_talent_off · talent_only_performance_off · talent_plus_optional_performance_evidence · talent_without_recruiting · talent_without_learning · succession_without_hipo · succession_without_nine_box · hipo_without_nine_box · nine_box_without_succession · full_performance_plus_talent · all_wave4_disabled

Every cell: correct runtime gates, no fake fallback truth, history retained when disabled.

### Setup Console

`setup_console_wave4_policies.py` + Setup card `Wave4PerformanceTalentPoliciesCard` — company ownership of Performance + Talent policies (not env-only). Env flags remain kill-switches. Setup rejects `forced_distribution_assumed=true`.

### Cross-surface contract

HR Web / Manager / Employee App / HR Mobile composition rules documented; Assistant mutations remain OUT (read/explain/summarize/deep-link only). No empty shells for disabled capabilities; HR Mobile not forced into heavyweight calibration/succession/9-box admin.

### Authority / anti-regressions

- No canonical `employee_box` / `talent_score` / `master_talent_score` columns  
- No duplicate succession development store — C3 sole development authority  
- Recruiting `talent_pool` ≠ post-hire `talent`; assessment norms ≠ Performance calibration  
- Tenant isolation · RBAC/visibility · raw 360 protection · potential/HiPo confidentiality · module rollback preserves history  
- Global Wave 4 flags remain off outside process-scoped canary prove  

### Wave 5 fact readiness

Catalog emitted (goal attainment, performance outcome/distribution, competency/development, talent population, HiPo, critical-role coverage, successor counts, ready-now distribution, uncovered roles). Wave 5 owns KPI defs, segmentation, trends, drill, export — **not built here**.

### Regression

C1–C6 staging smokes + Wave 1 / Wave 2 / Wave 3 product unit freezes — all green.

## Genuine blockers

None.

## Safe debt (non-blocking)

- Broader OTA / live channel fan-out for Wave 4 operator UX beyond Setup card + API contracts  
- Full HR Mobile / Employee App pixel parity polish for every Performance/Talent card (canonical APIs already sole truth; compose intentionally when subset enabled)  
- Executive analytics cards / KPI spine (Wave 5)  
- Broad production rollout beyond named canary (owner-gated)

## Stop

Owner accepted. Wave 4 remains frozen — do not reopen for safe debt.  
Wave 5 proceeds via charter only: `ops/WATHEFNI_HCM_WAVE5_HR_INTELLIGENCE_BUILD_CHARTER.md`.
Do not implement Wave 5 until `WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED`.
