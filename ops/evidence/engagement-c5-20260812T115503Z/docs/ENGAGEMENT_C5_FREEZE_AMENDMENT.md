# Wave 6 C5 — Freeze Amendment (Engagement)

**Stamp:** `ENGAGEMENT_FULL_PASS`  
**Evidence:** latest green `ops/evidence/engagement-c5-*`  
**Charter:** `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` (`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`)  
**Date:** 2026-08-12  

## What freezes with C5

- Survey templates/versions, questions, campaigns, invitations, response batches/answers  
- Anonymity threshold policy (default 5, upward-only) + aggregate suppression  
- Action plans/items (distinct from ER / performance development)  
- Setup Wave 6 Engagement module card + company policy knobs  
- Typed Wave 5 fact outbox (no raw anonymous responses as general facts)  
- Flags: `WATHEFNI_ENGAGEMENT_C5` + `WATHEFNI_ENGAGEMENT_COMPANIES`  

## What does **not** change

1. Waves 1–5 remain frozen  
2. C1–C4 Wave 6 remain frozen  
3. Recognition remains OUT of Wave 6 MVP  
4. ER remains separate; feedback does not auto-create ER cases  
5. No Comp Planning / Workforce Planning product slices yet  
6. Global flags remain off / company-gated; FULL_PASS ≠ broad rollout  

## Rollback

`WATHEFNI_ENGAGEMENT_C5=off` + clear company allowlist; campaign/response history retained.
