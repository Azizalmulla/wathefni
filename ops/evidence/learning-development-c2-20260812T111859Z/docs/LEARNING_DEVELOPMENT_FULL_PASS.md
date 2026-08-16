# LEARNING_DEVELOPMENT_FULL_PASS

**Status:** QUALIFIED — pending owner acceptance (stop before C3 Benefits)  
**Stamp:** `LEARNING_DEVELOPMENT_FULL_PASS`  
**Evidence:** see `ops/evidence/learning-development-c2-*` (latest green)  
**Charter:** `WAVE6_HCM_EXPANSION_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-learning-development-c2-staging.sh`  
**Freeze amendment:** `ops/LEARNING_DEVELOPMENT_C2_FREEZE_AMENDMENT.md`  
**Modules:**  
- `wathefni-orchestrator/learning_development_c2.py`  
- `wathefni-orchestrator/setup_console_wave6_policies.py` (learning module)  
- `apps/wathefni-dashboard/src/setup-console/Wave6LearningPoliciesCard.tsx`  

## Proved (charter C2)

- Canonical L&D authority: catalog → programs/courses → assignments → offerings/sessions → evidence-backed completion → certifications/renewal  
- Does not own employee/employment/org; optional refs only  
- Does not duplicate Wave 4 C3 development plans/actions; fulfillment link only; `silently_closed_c3` CHECK false  
- Completion does not auto-verify skill/competency  
- JA / Talent optional; L&D works Performance/Talent OFF  
- Catalog stable IDs + version history; assigned item/program versions pinned  
- Assignment provenance + lifecycle; due date overdue derived ≠ failure  
- Request ≠ approval ≠ enrollment ≠ completion  
- Session/offering distinct from catalog item  
- External-provider completion + evidence required  
- Mandatory policy population pinned; generation idempotent; revision creates new obligation  
- Certification ≠ course completion; expiry/expiring derived; renewal history  
- Manager scope / employee self / Setup vs ops separation (Setup card)  
- Shared notification dedupe; typed Wave 5 fact outbox (no analytics engine)  
- Assistant read-only  
- Module-off retains history; company allowlist fail-closed; tenant isolation  
- EN/AR labels; C1 JA stamp remains green  

## Stop

Owner review of `LEARNING_DEVELOPMENT_FULL_PASS`. Freeze C2. **Do not start C3 Benefits** until owner accepts.  
Global Learning remains OFF / company-gated. FULL_PASS ≠ broad rollout.
