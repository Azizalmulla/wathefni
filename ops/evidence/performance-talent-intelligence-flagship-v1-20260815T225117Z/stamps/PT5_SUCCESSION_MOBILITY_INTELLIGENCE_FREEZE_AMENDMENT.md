# PT5 — Freeze Amendment

**Stamp:** `PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS`  
**Prior:** `PT4_DYNAMIC_TALENT_MAP_FULL_PASS`  
**Module:** `wathefni-orchestrator/talent_succession_intel_pt5.py`

## Owns

- Derived succession intelligence facts over C6 slates
- Advisory mobility matches (`talent_mobility_matches_pt5`)
- Explicit Recruiting handoff gate

## Does not own

- C6 critical roles / plans / nominations / human readiness
- Employment or JA holder records
- Recruiting candidates / applications
- What-if simulation (PT8+)
- Trajectory (PT6)
- Assistant tools (PT7)
- R7

## Additive rules

- Mobility match ≠ application ≠ selection ≠ employment change
- Bench depth is counts/categories, never a 0–100 score
- No silent ranking via a master score
- Talent must work with Recruiting OFF
- Do not reopen C1–C6 or PT1–PT4 except for a genuine correctness/security blocker
