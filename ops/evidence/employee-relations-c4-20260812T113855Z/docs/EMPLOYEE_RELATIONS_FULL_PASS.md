# EMPLOYEE_RELATIONS_FULL_PASS

**Status:** QUALIFIED — pending owner acceptance (stop before C5 Engagement)  
**Stamp:** `EMPLOYEE_RELATIONS_FULL_PASS`  
**Evidence:** `ops/evidence/employee-relations-c4-20260812T113855Z`  
**Charter:** `WAVE6_HCM_EXPANSION_CHARTER: APPROVED`  
**Qualify:** `ops/qualify-employee-relations-c4-staging.sh`  
**Freeze amendment:** `ops/EMPLOYEE_RELATIONS_C4_FREEZE_AMENDMENT.md`  
**Modules:**  
- `wathefni-orchestrator/employee_relations_c4.py`  
- `wathefni-orchestrator/setup_console_wave6_policies.py` (employee_relations module)  
- `apps/wathefni-dashboard/src/setup-console/Wave6EmployeeRelationsPoliciesCard.tsx`  
- Smoke: `wathefni-orchestrator/smoke-test-employee-relations-c4.py`  

## Proved (charter C4)

- Canonical confidential ER authority: case → intake → triage → investigation → evidence → outcome → closure  
- No shadow employee/employment truth  
- Case type/version history; closed cases not rewritten by later Setup edits  
- Explicit lifecycle; due date overdue ≠ silent outcome  
- Employee submission ≠ finding; investigation ≠ outcome; outcome ≠ employment mutation  
- Explicit Wave 3 employment-change handoff only  
- Case-level RBAC: ordinary HR denied; manager denied by default; investigator scoped  
- Sensitive evidence fail-closed across api/direct_url/export/assistant  
- Employee-safe self view; internal notes/witness/investigation hidden  
- Shared tasks reused; notification payloads stay non-sensitive  
- Setup owns policy; no invented Kuwait legal outcomes  
- Wave 5 typed facts exclude sensitive free text  
- Assistant read-only; module-off retains history; tenant isolation; EN/AR  
- C1–C3 Wave 6 + Waves 1–5 unit freezes green  

## Stop

Owner review of `EMPLOYEE_RELATIONS_FULL_PASS`. Freeze C4. **Do not start C5 Engagement** until owner accepts.  
Global ER remains OFF / company-gated. FULL_PASS ≠ broad rollout.
