# Candidates Stage Contract — Production Report

**Stamp:** `20260730T160407Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Tenant proof:** `WATHEFNI` (unified Candidates on)

## Summary

Implemented the approved Candidates stage-bucket contract. View axis stays job/governance; Stage axis is lifecycle only. Talent Pool no longer displays as New (quiet `—`). Legacy `offered` / `offer_sent` display and filter as Shortlisted. Unknown statuses use Unknown, not New.

## Live proof (WATHEFNI)

| Check | Result |
|---|---|
| Talent Pool rows (2) display bucket | **`none` (—)** — not New |
| Stage filter New | **2** (`awaiting_cv`, `screening` only) — no held |
| Shortlisted expand | `shortlisted`, `offered`, `offer_sent` |
| Legacy offer display | **Shortlisted** |
| Ready / Interview / Hired filters | **3 / 0 / 4** (predicates unchanged) |

Evidence: `live-proof.json`.

## Files

### Dashboard
- `apps/wathefni-dashboard/src/lib/candidatesStageContract.ts` (**new**)
- `apps/wathefni-dashboard/src/lib/candidatesListPresentation.ts`
- `apps/wathefni-dashboard/src/lib/candidatesListPresentation.test.ts`
- `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.test.tsx`

### Backend (shared sets + proofs; list filter still expanded by UI)
- `wathefni-orchestrator/candidates_stage_contract.py` (**new**)
- `wathefni-orchestrator/test_candidates_stage_contract.py` (**new**)
- `wathefni-orchestrator/test_prehire_stage_filter_contract.py`

### Live assets
- `dashboard-BcLGGPb5.js`
- `CandidatesPage-CSe1l05a.js`
- `CandidateProfilePage-BihbTfi8.js`

## Migration impact

**None.** Presentation + Stage filter expansion only. No schema change. View pills unchanged.

## Rollback

```bash
/opt/wathefni/backups/production-pre-candidates-stage-contract-20260730T160407Z/ROLLBACK.sh
```

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| Vitest presentation + table (local) | **PASS** 19/19 |
| Unit contract suite (prod) | **PASS** 10/10 |
| Live Talent Pool ≠ New | **PASS** |
| Live New filter early-lifecycle only | **PASS** |
| Legacy offer → Shortlisted display/filter | **PASS** |
| Health | **PASS** `200` |

## Out of scope (unchanged)

Assessments, Ranking, visual redesign, View pill counts, first-class Offer lifecycle stage.
