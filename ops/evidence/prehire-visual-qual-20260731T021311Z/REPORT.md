# Pre-hiring visual qualification — local (no deploy)

**Stamp:** `20260731T021311Z`  
**Build under test:** local `apps/wathefni-dashboard` dist (proxy → `https://api.wathefni.ai`)  
**Direction:** `ops/evidence/prehire-visual-direction-20260731T014945Z/`  
**Deploy:** **NOT DONE — awaiting visual evidence approval**

Screenshots: `screenshots/` · Verify: `verify/` · Bundle: `bundle/COMPARISON.md`

---

## Suite gates

| Gate | Result | Notes |
|---|---|---|
| Production build (`tsc -b && vite build`) | **PASS** | See `verify/build.log` |
| Route smoke (9 pages × EN/AR desktop + EN mobile) | **PASS** | 32/32 shell visible, no login wall — `verify/route-smoke.json` |
| Bundle-size vs production | **PASS** | All key chunks within ±1% — `bundle/COMPARISON.md` |
| Behavior regression (visual chrome vs API/permission) | **PASS*** | Visual primitives + page chrome are className/shell/token oriented; no permission/API surface changes in the visual page modules. *Broader dirty tree still contains unrelated `api.ts` / Settings work — do not treat as part of this visual ship.* |
| Frontend tests (vitest) | **FAIL** | 4 failed / 170 passed — unrelated to visual chrome (PlatformIntegrationsPanel, EmployeeProfile.repro, candidateProfilePresentation). `verify/vitest.log` |
| ESLint (repo) | **FAIL** | 90 errors / 13 warnings mostly pre-existing `set-state-in-effect` |
| ESLint (visual-touched paths) | **FAIL** | 17 errors / 8 warnings — pre-existing hooks patterns on Jobs/Overview; not introduced as product logic |
| Typecheck | **PASS** | Covered by production build |
| Keyboard focus smoke | **PASS** | Tab reaches nav control; native outline present — `verify/focus-smoke.json`, `overview-en-desktop-focus.png` |

**Overall visual ship readiness:** **HOLD** — visual personalities largely **PASS**, but remaining corrections below should be fixed or explicitly waived before deploy. Do not deploy until approved.

---

## Page-by-page visual verdict

Personality check: none of the pages clone Overview’s pastel metric desk. Shared dark framed shell + cream canvas holds; composition differs per job.

| Page | Personality | EN desktop | AR desktop | Mobile | Empty / loading / error | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| **Overview** | Editorial desk | `overview-en-desktop.png` | `overview-ar-desktop.png` | `overview-en-mobile.png`, `overview-ar-mobile.png` | N/A (live desk) | **PASS** | Authority reference; dark shell + pastel priority band unique to this page. AR content flips; sidebar stays EN/LTR (product pattern). |
| **Jobs** | Hiring portfolio / table | `jobs-en-desktop.png` | `jobs-ar-desktop.png` | `jobs-en-mobile.png` | Loading: `jobs-en-desktop-loading.png` | **PASS*** | Strong table rhythm, not Overview grid. *Mobile: horizontal nav can leave active Jobs off-screen (chrome shows Overview). Duplicate Refresh (shell + page).* |
| **Candidates** | People list | `candidates-en-desktop.png` | `candidates-ar-desktop.png` | `candidates-en-mobile.png`, `candidates-ar-mobile.png` | Forced API fail → empty copy not error: `candidates-en-desktop-error.png` | **PASS*** | Identity rows + filter rail distinct. *AR: page chrome title stays EN while board is AR. Error path soft-fails to empty.* |
| **Interviews** | Schedule queue | `interviews-en-desktop.png` | `interviews-ar-desktop.png` | `interviews-en-mobile.png` | Empty queue captured on Upcoming tab | **PASS** | Coordination board / queue, not metric cards. Sans titles OK. |
| **Calendar** | Spatial grid | `calendar-en-desktop.png` | `calendar-ar-desktop.png` | `calendar-en-mobile.png` | Empty week grid | **PASS*** | Spatial personality clear; pill Day/Week/Month + My/Team/Company. *Slight rounded nesting (shell → board → grid).* |
| **Assessments** | Evaluation workspace | `assessments-en-desktop.png` | `assessments-ar-desktop.png` | `assessments-en-mobile.png` | Cohort empty counts present | **PASS*** | Eval tabs + send queue, not Overview pastel strip. *Two stacked pill rows (primary + cohort) → black-pill density.* |
| **Ranking** | Comparison / decision | `ranking-en-desktop.png` | `ranking-ar-desktop.png` | `ranking-en-mobile.png` | Empty: `ranking-en-desktop-empty-or-loaded.png` | **PASS** | Minimal chrome; select-job empty state correct. |
| **Reports** | Quiet analytical | `reports-en-desktop.png` | `reports-ar-desktop.png` | `reports-en-mobile.png` | N/A (always data tiles) | **PASS*** | Quieter / lower chroma vs Overview. *Highest nested rounded cards (metrics + breakdowns + exports).* |
| **Assistant** | Conversational | `ai-en-desktop.png` | `ai-ar-desktop.png` | `ai-en-mobile.png` | Empty: `ai-en-desktop-empty.png` | **PASS** | Cream chat shell; not foreign glass/dark floating assistant. |

\* = PASS with remaining corrections listed below.

---

## Cross-cutting audit

| Audit item | Finding |
|---|---|
| Repeated cream panels / identical templates | Shared board surface language, but compositions differ (desk / table / people / queue / grid / eval / rank / quiet tiles / chat). **OK** |
| Too many black pills | Primary CTAs + active filters OK on most pages; **Assessments** stacked pill rows and **Jobs** dual Refresh elevate density. |
| Rounded-container nesting | Present by design (frame → stage → board). **Reports** densest; **Calendar** moderate. |
| Weak hierarchy | Generally strong titles → actions → board. |
| Cramped tables / filters | Desktop Jobs/Candidates spacious. Mobile Jobs filters wrap / clip “More filters”. |
| Inconsistent headers | Shared App header for non-Overview pages is consistent; Overview intentionally different. **Jobs duplicate Refresh** vs shell Refresh. |
| Awkward RTL spacing | Jobs AR table aligns well. Candidates AR mixed EN chrome + AR board. Global `dir` not set on document (only Jobs title/subtitle in App). Toast stays English on AR. |
| Sidebar / content alignment | Desktop framed shell aligned. **Mobile horizontal nav** does not keep active item in view. |
| Mobile overflow | No horizontal document overflow detected in metrics (`overflow_x=false`). Filter chips may scroll inside. |
| Contrast / keyboard focus | Dark rail + ink on cream contrast OK. Focus outline present after Tab. |

---

## Remaining visual corrections (before deploy)

1. **Mobile nav active visibility** — horizontal PRE-HIRING rail should scroll/center the active item (Jobs mobile chrome currently reads as Overview).  
2. **Deduplicate Refresh** — shell Refresh vs page Refresh (Jobs especially; mobile stacks both).  
3. **RTL completeness** — set page/`dir` for AR across pre-hire (not Jobs-only); localize page titles/subtitles for Candidates/Interviews/etc.; keep toast locale-aware.  
4. **Candidates error state** — surface API failure distinctly from empty filters (forced 500 currently looks like empty).  
5. **Assessments pill density** — quiet secondary cohort controls (text/segment) vs second black-pill row.  
6. **Reports nesting** — flatten one layer (metric tiles without extra card chrome) to match “quiet analytical” personality.  
7. **Waive or fix** unrelated vitest failures before calling the FE suite green (out of visual chrome scope, but blocks a clean verify gate).

---

## Explicit non-actions

- No production deploy  
- No tenant / email / calendar / Teams mode changes  
- No permission or API contract changes in this visual phase  

---

## How screenshots were captured

`proxy-and-capture.mjs` served local `dist/` on `127.0.0.1:4177`, proxied `/dashboard/*` APIs to production, seeded a short-lived owner session in localStorage only (token not stored in this pack), and wrote the matrix under `screenshots/`.
