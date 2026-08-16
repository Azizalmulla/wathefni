# Pre-hiring mobile navigation — final fix evidence

**Stamp:** `20260731T124927Z`  
**Scope:** Mobile PRE-HIRING navigation only (active route always visible)  
**Deploy:** **LIVE** via `ops/evidence/prehire-visual-deploy-20260731T131216Z/` (`20260731T131216Z`)

Related packs preserved:
- M365 outbound mail authority **COMPLETE / FULL PASS** — `ops/evidence/hybrid-email-m365-outbound-recheck-20260731T024000Z/`
- Visual correction (prior HOLD) — `ops/evidence/prehire-visual-fix-20260731T023139Z/`
- Accepted Vitest/ESLint waivers — that pack’s `waivers/VITEST_ESLINT.md` (three unrelated failures accepted)

---

## Final verdict

| Gate | Result |
|---|---|
| Mobile PRE-HIRING active-route chip always visible | **PASS** |
| No misleading non-active chip as dominant nav item | **PASS** |
| All pre-hiring routes reachable (rail + More for posthire/settings) | **PASS** |
| Page title + `data-active` / `aria-current` preserved | **PASS** |
| EN + AR/RTL | **PASS** |
| Narrow widths (320) + route changes | **PASS** |
| Mobile route smoke (all pre-hire pages) | **PASS** 23/23 shell, 0 login walls |
| EN/AR screenshots | **PASS** (`screenshots/`) |
| Targeted navigation Vitest | **PASS** 20/20 |
| Production build | **PASS** |
| Bundle vs prod | **PASS** (expected `dashboard` +3.74%; page deltas from prior visual pass) |

**Overall: PASS**

---

## What changed

1. **Sticky active-route chip** (`mobile-active-route-chip`) is the only active nav affordance on mobile; PRE-HIRING rail lists **other** pre-hire routes only (no duplicate active button).
2. **More** menu keeps Settings / post-hire / alerts access without polluting the pre-hire rail.
3. **Desktop vs mobile nav** are mutually exclusive via `matchMedia('(min-width: 1024px)')` (avoids duplicate a11y trees).
4. **RTL overflow containment:** framed shell / aside / section use `min-w-0` + `overflow-x-clip`; mobile nav forced `dir="ltr"` with bounded width so the active chip cannot be clipped off-screen under Arabic `main dir=rtl`.

Unrelated visual areas were **not** reopened.

---

## Verification artifacts

| Artifact | Path |
|---|---|
| Mobile nav proofs | `verify/mobile-nav-proofs.json` (21/21 PASS) |
| Route smoke | `verify/route-smoke.json` |
| EN route-change | `verify/route-change-nav.json` |
| AR route-change | `verify/ar-route-change-nav.json` |
| Vitest | `verify/vitest-nav.log` |
| Build | `verify/build.log` |
| Capture log | `verify/capture.log` |
| Bundle | `bundle/COMPARISON.md` |
| Screenshots | `screenshots/*-{en,ar}-mobile.png`, `*-en-narrow.png` |

---

## Accepted waivers (unchanged)

From `prehire-visual-fix-20260731T023139Z/waivers/VITEST_ESLINT.md`:

1. `candidateProfilePresentation` Stage `—` vs `New`
2–3. `PlatformIntegrationsPanel` / Settings `EmailSendingCard` `choices.map`

**Accepted for ship.** Not caused by this mobile-nav fix.

---

## Deploy recommendation

**DEPLOYED** `20260731T131216Z` — see `ops/evidence/prehire-visual-deploy-20260731T131216Z/REPORT.md`.  
Leave `api.ts` / email Settings mock fixes on their own tracks.
