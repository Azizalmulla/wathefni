# Shifts Visual & Interaction Redesign Wave 3B — production report

**Stamp:** `20260804T170817Z`  
**Verdict:** GREEN  
**Bundle:** `PostHire-Cehe0aMR.js`  
**Database:** `wathefni`

## Delivered

- CSS-grid weekly roster lanes; no HTML schedule table
- employee identity anchored once per row
- time-first shift tiles with semantic inline-start rails
- overlap lanes and linked overnight continuation fragments
- continuous today lane treatment
- seven-day mobile strip with employee-grouped day agenda
- compact filter/scope bar and removable active filters
- client-only status filtering without server refetch
- fixed 420px desktop end sheet and full-screen mobile sheet
- grouped Shift, Organization, and Controls fields
- retained board, drawer, and history content during refresh
- quieter Requests and Planning surfaces
- intentional EN/AR and LTR/RTL layouts

## Verification

- Wave 1 + Wave 2 IQ-12 + semantic color + Wave 3B: 23/23 PASS
- TypeScript + Vite production build: PASS
- Wave 3B production marker/authority smoke: PASS
- Wave 2 IQ-12 production recheck: PASS
- EN/AR × desktop/mobile Schedule: captured
- EN/AR × desktop/mobile create drawer: captured
- EN/AR × desktop/mobile Requests: captured

The full dashboard suite is 358/372 green. The 14 unrelated failures predate
this change and are outside Shifts. Targeted Shifts contracts and production
smokes are fully green.

## Production evidence

- `tests/shifts-contracts.out`
- `tests/dashboard-build.out`
- `verify/production-smoke.out`
- `verify/iq12-production-recheck.out`
- `verify/production-screenshots.out`
- `after/*.png`

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave3b-visual-20260804T170817Z/ROLLBACK.sh
```

## Baseline decision

**GO** for Wave 3B's composition and interaction primitives as the shared
post-hiring visual baseline, adopted page-by-page.

Rejected Wave 3 remains historical evidence only and must not be propagated.

