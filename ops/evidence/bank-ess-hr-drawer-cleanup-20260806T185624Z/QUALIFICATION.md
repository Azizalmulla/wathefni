# HR onboarding drawer cleanup

**Stamp:** `20260806T185624Z`  
**Verdict:** `deployed`  
**Auth Wave 2:** not started

## Correction

The first Phase 2 drawer release mounted the full canonical Bank review panel
above every checklist group. In the narrow drawer it dominated the workflow,
repeated the HR state, and forced masked bank values into an unreadable
two-column layout.

The corrected interaction is:

1. The drawer opens with only the canonical state/progress/next-owner summary.
2. `bank_details` appears as a compact row under **Needs HR action**.
3. **Review bank** explicitly opens the canonical panel.
4. The drawer variant is always single-column and masked identifiers wrap.
5. **Close** returns to the compact checklist.
6. Evidence, decision history, Reject+reason, Approve and Apply remain intact.

No backend, mobile, permission, audit, evidence or canonical-state behavior was
removed or changed in this correction.

## Qualification

- Dashboard focused Vitest: **21/21 PASS**
- TypeScript + Vite production build: **PASS**
- Static controls: **1,134 controls; 0 dead candidates**
- Live asset: `PostHire-C_o12y1w.js`
- Live asset HTTP: **200**
- SHA-256: `905498b38c80a72a0edfb79ac3ca6269503a0f12695245f768a69be0f75729da`

## Rollback

Dashboard backup:

`/opt/wathefni/dashboard-dist-bak/bank-ess-hr-drawer-cleanup-20260806T185624Z/`
