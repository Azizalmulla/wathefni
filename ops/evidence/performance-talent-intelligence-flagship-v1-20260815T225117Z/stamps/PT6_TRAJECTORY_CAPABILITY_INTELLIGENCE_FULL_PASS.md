# PT6 — Trajectory + Organizational Capability Intelligence

**Status:** `PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_FULL_PASS`  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**Prior freeze:** `PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS`  
**Paused:** Production Readiness R7  
**Do not begin:** PT8, R7  
**Next (serial, no owner gate):** PT7 Wathefni Assistant Talent Intelligence

---

## 0. What shipped

Governed trajectory labels over PT1 closed-period history, plus Wave 5 formula handlers for capability intelligence. No second analytics engine.

Shipped:

- Versioned published `talent_trajectory_policies_pt6` (company must publish/enable)
- Closed/comparable OKR periods only; default `min_closed_periods=2`
- Labels: accelerating, stable high performance, declining, emerging, stalled development
- Insufficient history → no label + WHY
- Wave 5 handlers: capability coverage, single-person capability, skill direction (honest insufficient), underutilized (honest insufficient), holder-dependency
- Holder-dependency excludes the person from the analytic skill-holder population only — never `UPDATE employees`
- Every capability fact carries definition, source, cohort/privacy, drill path, historical version

Did **not** ship:

- Universal Talent / flight-risk score
- Overwrite of Performance / Potential / HiPo / readiness / Wave 5
- Full PT8 what-if simulation
- A second KPI evaluator

---

## 1. Binding authorities preserved

| Authority | PT6 rule |
|---|---|
| Performance / OKR | Closed periods read only |
| C5 Potential / skills | Read only |
| C6 HiPo / readiness | Not overwritten |
| Wave 5 registry | Extended via `register_formula_handler` only |
| Wave 4 C1–C6 | Not reopened |
| Employment | Never mutated by holder-dependency |
| R7 | Stays paused |

---

## 2. Qualification

Run: `ops/qualify-pt6-trajectory-capability.sh`  
Evidence: `ops/evidence/pt6-trajectory-capability-20260815T224724Z/`

Proved:

- Dashboard 89/481 + mobile composition
- PT6 unit 19/0 + PT5 predecessor + R5C + Wave 4 + Wave 5 unit
- Staging DB: no policy → no label; insufficient history → no label; UNIQUE skill becomes vulnerable under holder-dependency; employment remains active; baseline coverage unchanged after analytic exclusion
- Live holder-dependency and map routes not public
- Wave 5 product unit still `WAVE5_PRODUCT_UNIT_PASS`

---

## 3. Safe debt

- Skill-direction and underutilized-capability handlers honestly return `insufficient_data` until a closed skill window / JA assignment+requirement set exists
- Trajectory uses OKR objective rollup averages; review ratings are not a second series in V1
- Growth × Contribution map lens remains unknown until a published label exists for the employee

---

## 4. Next

PT6 frozen. Continue serially to **PT7**. Do not resume R7. Do not start PT8.
