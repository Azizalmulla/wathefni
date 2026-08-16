# TALENT_PROFILE_C5_FREEZE_AMENDMENT

**Slice:** Wave 4 C5 — Canonical Talent Profile / Talent Dimensions  
**Stamp:** `TALENT_PROFILE_FULL_PASS`  
**Status:** QUALIFIED / FROZEN after staging prove — stop for owner review before C6  
**Module:** `wathefni-orchestrator/talent_profile_c5.py`  
**Flags:** `WATHEFNI_TALENT_PROFILE_C5` + `WATHEFNI_TALENT_PROFILE_COMPANIES` (empty = nobody)  
**Kill:** `WATHEFNI_TALENT_KILL`  
**Commercial module:** `talent` (Recruiting `talent_pool` remains candidate-only)

## Frozen authority

C5 owns dimension-first post-hire Talent truth:

1. Thin `talent_profiles` anchor on canonical `company_code` + `employee_key` (no shadow person; no master Talent score)
2. Versioned `talent_dimension_facts` with mandatory provenance (employee/manager/HR/competency/development/performance/imported/learning)
3. Employee-declared career aspirations/mobility — not silently rewritten by manager/HR
4. `talent_skills` with claimed vs verified/assessed states + history
5. Explicit competency→Talent evidence mapping contract
6. Configurable `talent_potential_frameworks` + assessments (works without Performance; performance ≠ potential)
7. Optional Performance evidence links (consume flag; never hard dependency)
8. Readiness observation primitives without succession nominations
9. As-of temporal queries over facts/skills/potential history

## Explicit non-goals (do not reopen into C5)

- HiPo designation · 9-box placement · succession nominations · employee rankings · internal mobility engine  
- Universal Talent score  
- Duplicate C3 development plans  
- Writes to recruiting `talent_pool`  
- Assistant mutations  

## Next

C5 frozen and owner-accepted 2026-08-12. C6 may proceed; do not reopen C1–C5.
