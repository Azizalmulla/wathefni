# PT2 — Freeze Amendment

**Stamp:** `PT2_TALENT_MODELS_WHY_FULL_PASS`  
**Prior:** `PT1_OKR_EVIDENCE_FULL_PASS` (OWNER ACCEPTED / FROZEN)  
**Module:** `wathefni-orchestrator/talent_models_pt2.py`  
**Surfaces:** existing Talent HTTP / HR Web Models tab

## What this slice owns

- Versioned Talent models and immutable published versions
- `rules_v1` and optional explicit `weighted_v1`
- Explicit missing-data policy
- Derived classifications
- Deterministic WHY graph
- Optional AI narration of that graph (never a classification input)

## What this slice does **not** own

- Human Potential (C5) or designated HiPo (C6)
- Role-fit / readiness engine (PT3)
- Talent Map (PT4)
- Succession intelligence / mobility discovery (PT5)
- Trajectory labels / Wave 5 capability keys (PT6)
- Assistant Talent tools (PT7)
- Full workforce what-if (PT8+)
- Production Readiness R7

## Additive freeze rules

- Derived High Potential signal ≠ designated HiPo
- Only existing human Talent authority may designate HiPo
- Missing evidence is `insufficient_evidence`, never 0 or 100%
- Weighted percentages exist only when weights, methodology, and missing-data handling are explicit and inspectable
- WHY graphs must remain deterministic; AI may only narrate
- High OKRs + high Performance + low human Potential + no HiPo must remain exactly that
- Do not reopen Wave 4 C1–C6 or PT1 except for a genuine correctness/security blocker
- No second employee profile, skills authority, or analytics engine
- No universal Talent score and no automatic HiPo

## Prior freezes

- PT1 remains OWNER ACCEPTED / FROZEN
- Wave 4 C1–C6 remain frozen
- R5C Talent surface remains an adapter
- R7 stays **PAUSED**

## Rollback

```text
Stop publishing new model versions
Do not hard-delete published versions or WHY graphs
Derived classifications are overlay rows — C5/C6 records are untouched
WATHEFNI_TALENT_KILL=on (optional immediate block)
```

## Next

PT2 frozen. Continue to PT3. Do not resume R7.
