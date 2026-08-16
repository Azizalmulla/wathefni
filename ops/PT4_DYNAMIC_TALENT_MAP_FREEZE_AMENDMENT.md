# PT4 — Freeze Amendment

**Stamp:** `PT4_DYNAMIC_TALENT_MAP_FULL_PASS`  
**Prior:** `PT3_ROLE_FIT_READINESS_FULL_PASS`  
**Module:** `wathefni-orchestrator/talent_map_pt4.py`

## Owns

- Talent Map placements and lens projections
- Canonical fact snapshot reused across lenses
- Placement WHY (lens + consumed/missing + pointers to PT2/PT3 WHY)

## Does not own

- Human Potential / HiPo / C6 readiness
- Role-fit evaluation (PT3)
- Configurable talent models (PT2)
- Succession intelligence (PT5)
- Trajectory labels (PT6)
- Assistant tools (PT7)
- R7 / PT8

## Additive rules

- Not a 9-box product; 9-box is one derived lens
- Unknown stays unknown; `forced_middle` is always false
- Switching lenses must not rewrite the employee
- No decorative AI; no universal Talent score
- Do not reopen C1–C6, PT1, PT2, or PT3 except for a genuine correctness/security blocker
