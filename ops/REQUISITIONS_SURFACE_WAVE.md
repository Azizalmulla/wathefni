# Requisitions Surface Wave

**Status:** QUALIFIED — `REQUISITIONS_SURFACES_FULL_PASS`  
**Evidence:** `ops/evidence/requisitions-surfaces-20260811T185808Z`  
**Backend freeze:** `ops/REQUISITIONS_WAVE1_BACKEND_FREEZE.md` (preserved)

## Surfaces

| Surface | Path |
|---|---|
| Thin helpers | `wathefni-orchestrator/requisitions_surfaces.py` |
| HTTP | `wathefni-orchestrator/requisitions_http.py` |
| HR Web | `apps/wathefni-dashboard/src/prehire/RequisitionsWorkspace.tsx` |
| HR Mobile | `apps/wathefni-employee-mobile/src/hr/features/requisitions/*` |
| Assistant | `/dashboard/assistant/requisitions/{id}` + deep link `/hr/requisitions` |

## Product answers

- Who requested headcount?
- What needs approval?
- What is open to fill?
- SoD: creator cannot self-approve

## Modularity

Works with or without Pre-Hiring / Offers / Onboarding. Employment not required for requisitions themselves. Job publish gate remains OPTIONAL_INTEGRATION (frozen backend).

## Employee App

No ESS requisitions surface in Wave 1.
