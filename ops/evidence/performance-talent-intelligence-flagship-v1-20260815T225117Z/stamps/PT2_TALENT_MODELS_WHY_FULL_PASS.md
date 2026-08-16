# PT2 — Configurable Talent Models + WHY Graph

**Status:** `PT2_TALENT_MODELS_WHY_FULL_PASS`  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**Prior freeze:** `PT1_OKR_EVIDENCE_FULL_PASS` (OWNER ACCEPTED / FROZEN)  
**Paused:** Production Readiness R7  
**Do not begin:** PT8, R7  
**Next (serial, no owner gate):** PT3 Role Fit + Readiness Intelligence

---

## 0. What shipped

PT2 adds a versioned Talent **model** overlay over PT1 evidence and frozen C5/C6 human authority.

Shipped:

- Versioned `talent_models_pt2` + immutable published `talent_model_versions_pt2`
- Configurable dimensions, evidence bindings, scales, thresholds, eligibility, `rules_v1`, optional explicit `weighted_v1`
- Explicit missing-data policy (`insufficient` | `exclude_renormalize`)
- Derived classifications stored beside — never instead of — human Potential / HiPo
- Deterministic WHY graph (model/version, consumed/excluded/missing, provenance, rules/weights, human overrides)
- Optional AI narrative only when a published version allows narration; narrative is not evidence
- HR Web Models tab (EN/AR) on the existing Talent workspace

Did **not** ship:

- Automatic HiPo
- Universal Talent score
- Frontend Talent math
- Role-fit engine (PT3)
- Talent Map (PT4)
- Succession intelligence (PT5)
- Trajectory labels (PT6)
- Assistant Talent tools (PT7)

---

## 1. Binding authorities preserved

| Authority | PT2 rule |
|---|---|
| C5 human Potential | Unchanged. Model may read it. Model never writes it. |
| C6 designated HiPo | Unchanged. Only existing human Talent authority designates HiPo. |
| Derived High Potential signal | Side-by-side classification. ≠ designated HiPo. |
| PT1 evidence index | Pointers + consume contracts remain. AI-SYNTHESIZED cannot classify. |
| Wave 5 | No second analytics engine. |
| Wave 4 C1–C6 math/state | Not reopened. |
| R7 | Stays paused. |

---

## 2. Qualification

Run: `ops/qualify-pt2-talent-models.sh`

Evidence: `ops/evidence/pt2-talent-models-20260815T222914Z/`

Proved:

- Published versions are immutable
- Missing evidence → `insufficient_evidence`, never 0 or 100%
- `weighted_v1` refused unless every weight is explicit and weights sum to 1
- High OKRs + high Performance + low human Potential + no HiPo remain exactly that
- Derived signal does not write C6 HiPo
- AI is not a classification input
- Contradictions are not reconciled
- Talent works with Performance OFF
- Consume contracts still default off
- Tenant isolation on models and WHY
- EN/AR labels
- PT1 predecessor unit + R5C + Wave 4 product contracts
- Live model routes are not public

---

## 3. Safe debt

- Models tab is a thin HR publish/evaluate surface, not a full model studio
- Weighted band mapping is a small explicit qualitative table, not a customer scale editor
- Eligibility is clause-based on collected dimensions only (tenure/contractor JA facts remain PT3+ if needed)

---

## 4. Next

PT2 frozen. Continue serially to **PT3**. Do not resume R7. Do not start PT8.
