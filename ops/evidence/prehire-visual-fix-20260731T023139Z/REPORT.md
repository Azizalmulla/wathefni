# Pre-hiring visual correction pass — evidence

**Stamp:** `20260731T023139Z`  
**Prior qual:** `ops/evidence/prehire-visual-qual-20260731T021311Z/`  
**Deploy:** **HOLD — do not deploy yet**

Screenshots: `screenshots/before/` · `screenshots/after/` · Waivers: `waivers/VITEST_ESLINT.md` · Isolation: `isolated/README.md`

---

## Corrections completed

| Item | Status | Evidence |
|---|---|---|
| Mobile active navigation | **PARTIAL → improved** | `data-active` + `aria-current="page"` + aside `scrollTo` centering. Page title always Jobs. Horizontal strip may still show a non-active chip in some mobile captures (see residual). |
| Duplicate Refresh | **PASS** | Shell is sole pre-hire refresh authority; Jobs page Refresh removed. After Jobs mobile shows one Refresh only. |
| Arabic / RTL completeness | **PASS** | `dir`/`lang` on `<main>`; aside stays LTR for brand rail; AR page titles/subtitles/nav groups/toast/Refresh. After: `jobs-ar-desktop.png`. |
| Candidates error state | **PASS** | Forced API fail → pink retryable alert, not empty list. `after/candidates-en-desktop-error.png`. |
| Assessments hierarchy | **PASS** | Primary Send/Attempts/Reports stay black; cohort row is soft cream chips (no second black-pill row). Page Refresh removed (shell owns it). |
| Reports density | **PASS** | Card nesting removed; flat overview metric grid + open breakdowns + export rows. `after/reports-en-desktop.png`. |
| api.ts isolation | **Documented** | Working-tree `api.ts` excluded from visual review boundary (`isolated/`). Hard restore to HEAD breaks Calendar/Assistant/Settings imports. |

---

## Gates

| Gate | Result |
|---|---|
| Production build | **PASS** (`verify/build.log`) |
| Route smoke | **PASS** 32/32 (`verify/route-smoke.json`) |
| Bundle vs prod | **PASS with expected growth** — `dashboard` +2.5% (AR chrome strings); `CandidatesPage` +7% (error UI); `ReportsPage` +7% (layout rewrite). See `bundle/COMPARISON.md`. |
| Targeted Vitest (visual-related) | **PASS** App + Jobs + EmployeeProfile = 18/18 |
| Original 4 Vitest failures | **1 fixed**, **3 waived** with evidence — `waivers/VITEST_ESLINT.md` |
| Changed-file ESLint | **Pre-existing only** waived — no new phase-caused rule debt kept |

---

## Page-by-page after correction

| Page | Verdict |
|---|---|
| Overview | **PASS** (authority unchanged) |
| Jobs | **PASS*** (*mobile nav strip residual) |
| Candidates | **PASS** |
| Interviews | **PASS** |
| Calendar | **PASS** |
| Assessments | **PASS** |
| Ranking | **PASS** |
| Reports | **PASS** |
| Assistant | **PASS** |

---

## Residual / follow-up (non-blocking for visual approve, still HOLD deploy)

1. **Mobile horizontal nav visibility** — **cleared** in `ops/evidence/prehire-mobile-nav-final-20260731T124927Z/` (sticky PRE-HIRING active chip + rail; RTL overflow fixed).
2. **Unrelated Vitest waivers** — **accepted** (candidate stage `—` vs `New`; PlatformIntegrations/EmailSendingCard mock crash).
3. **api.ts** — keep out of visual PR; ship on its own track.

---

## Deploy recommendation

**Superseded:** see `ops/evidence/prehire-mobile-nav-final-20260731T124927Z/REPORT.md` — mobile residual cleared; **READY TO DEPLOY on explicit approval**. This correction pack itself did not deploy.
