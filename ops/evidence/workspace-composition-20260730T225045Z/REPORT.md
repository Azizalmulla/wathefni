# Entitlement-driven workspace composition

**Stamp:** `20260730T225045Z`  
**Verdict:** **PASS**

## Goal

One shared workspace capability authority drives sidebar, Overview composition, tabs, Settings sections, Assistant-adjacent surfaces, notifications deep-links, and filters—so the UI adapts coherently to tenant modules, actor permissions, provider readiness, and live work.

## Composition matrix

| Scenario | Modules | Role | Nav groups | Nav includes | Nav excludes | Overview layout |
|---|---|---|---|---|---|---|
| **One module** | `pre_hiring` | owner | prehire, settings | overview, ai, jobs, candidates, interviews*, ranking, reports, notifications, activity, settings | payroll, assessments, attendance | **two** (review + follow-up cards) |
| **Two modules** | `pre_hiring` + `assessments` | owner | prehire, settings | + assessments | payroll, leave | **three** |
| **Three–four modules** | + `interviews`, `calendar` | owner | prehire, settings | + calendar | payroll | **three** |
| **Full pre-hiring** | + `video_interviews` | owner | prehire, settings | full pre-hire set; video tab **on** | payroll, onboarding | **three** |
| **Post-hire only** | onboarding, attendance, leave, payroll | owner | **posthire**, settings | ai (in posthire), employees, module pages | overview, jobs, candidates, assessments | **none** (no pre-hire Overview) |
| **Mixed pre/post** | pre_hiring, assessments, leave, attendance | owner | prehire, posthire, settings | both suites | payroll | **three** |
| **Restricted recruiter** | pre_hiring, assessments, interviews, leave, payroll | recruiter | prehire, settings | jobs, candidates, interviews, notifications | overview, ai, ranking, reports, assessments, payroll, leave | **two** (review + follow-up entitlement; no assessment card) |

\*Interviews remains available under legacy `pre_hiring` OR `interviews` until tenants migrate fully to the dedicated module.

### Layout rules (Overview priority action cards)

| Eligible priority cards | Layout |
|---|---|
| 0 | `none` — calm / no priority strip |
| 1 | `one` — full-width focused surface |
| 2 | `two` — balanced two-column |
| 3 | `three` — three-card row |
| 4+ | `grid` — responsive grid |

Live zero-count cards are omitted at render time (work over decoration). Empty nav groups are never emitted. Single remaining tab → hide tab bar (`filterTabsByAuthority`).

## Shared authority

| Layer | Path |
|---|---|
| FE authority | `apps/wathefni-dashboard/src/lib/workspaceCapability.ts` |
| FE tests | `workspaceCapability.test.ts` |
| BE mirror | `wathefni-orchestrator/workspace_capability.py` |
| BE tests | `test_workspace_composition_matrix.py` |
| Wiring | `App.tsx` (nav groups from authority), `OverviewPage.tsx`, `InterviewsPage.tsx` (video tab), `SettingsPage.tsx` (team/integrations) |

Assistant empty-state/chips remain on `assistant_capability_catalog` (same entitlement inputs). Notifications stay module-scoped; deep-links use authority `navIds`.

## Visual fixtures

Under `fixtures/`:

- `composition-matrix.json`
- `one_module_prehire.json`, `two_modules.json`, `three_four_modules.json`, `full_prehiring.json`, `posthire_only.json`, `mixed.json`, `restricted_recruiter.json`

## Tests

| Suite | Result |
|---|---|
| `python3 test_workspace_composition_matrix.py` (local + prod) | **PASS** |
| `vitest workspaceCapability.test.ts` (12) | **PASS** |
| `vitest App.test.tsx` + `InterviewsPage.test.tsx` | **PASS** |
| Prod dashboard bundle probe (`overview.action.review`) | **PASS** |
| Prod health after deploy | **200** |

## Deploy

- Host: `root@76.13.63.68`
- Dashboard: `/var/www/wathefni-dashboard`
- Orchestrator: `/opt/wathefni/orchestrator` (`workspace_capability.py`)
- Backup: `/opt/wathefni/backups/production-pre-workspace-composition-20260730T225045Z`
- Script: `ops/deploy-workspace-composition.sh`

## Overall

**PASS** — shared composition authority defines nav + Overview for all required module/role combinations; regression tests and production deploy are green.
