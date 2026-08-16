# Overview Wave 2 — Destination Parity & Durable Navigation

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260727T225522Z`  
**Host:** `root@76.13.63.68`  
**Scope:** Overview CTA → exact cohort destination; URL-persisted filters; refresh/Back durability  
**Not in this wave:** Ranking logic, assessment cohort definitions, colors

---

## Final verdict

**PASS — Wave 2**

Every Overview CTA now opens the same cohort that produced its count. Destinations publish stable `cohort_key` / `overview_cohort` filters in the URL. Interview debt no longer drops filters on an empty Interviews page. Role priority and role next-step open the active role people cohort (Ranking stays on the explicit Check ranking CTA). Refresh restores the filtered cohort; Back restores Overview with scroll.

---

## What changed

### Backend (`wathefni-orchestrator/prehire_overview.py` + surgical `app.py`)

- Every Overview destination includes `cohort_key` and matching `overview_cohort` filter.
- Interview scheduling debt destination → **Candidates** with  
  `overview_cohort=interview_scheduling_debt` + `interview_status=none`  
  (exact debt predicate; not Interviews `needs_scheduling`).
- Role priority / role next-step primary destination → Candidates  
  `overview_cohort=role_active` + exact `position`  
  (`ranking_destination` retained for Check ranking only).
- Next-action role winner uses role cohort destination (not Ranking).
- Work-queue person rows keep primary `app_key` + action + cohort filters.
- `prehire_applications_query` accepts `overview_cohort`:
  - `interview_scheduling_debt`
  - `role_active` (exact `position_code`)
  - optional aliases for follow-up / ready / assessment

### Frontend (`apps/wathefni-dashboard`)

- New `src/lib/dashboardNavigation.ts` — read/write durable URL state:
  - `follow_up`, `review_status`, `assessment_status`, `interview_status`
  - `position` / `position_code`, `sort`, `overview_cohort`, `cohort_key`
  - interview `status`/`tab`/`role`/`date`/`interviewer`
  - `action`, `candidate`, `overview_scroll`
- Overview CTAs navigate via URL destinations (not React-only filter state).
- Candidates / Interviews / Ranking filter changes sync into the URL (`replace`).
- `popstate` restores page + filters + Overview scroll.
- Top-priority rows open person destination (app + action context).
- Role card → role_active cohort; Check ranking → `ranking_destination`.

---

## Live WATHEFNI proof (`20260727T225522Z`)

| Card | Overview people | Overview apps | Destination people | Destination apps | Pass |
|---|---:|---:|---:|---:|---|
| Follow-up | 2 | 4 | 2 | 4 | PASS |
| Review ready | 2 | 3 | 2 | 3 | PASS |
| Assessment attention | 2 | 3 | 2 | 3 | PASS |
| Interview scheduling debt | 2 | 4 | 2 | 4 | PASS |
| Role priority (ACCOUNTING_EXCEL) | 1 | 1 | 1 | 1 | PASS |
| Role next steps | destinations = `role_active` | — | — | — | PASS |
| Top priorities | person rows with `app_key` + cohort/action | — | — | — | PASS |
| Next-action destination | has `cohort_key` | — | — | — | PASS |

Evidence: `/opt/wathefni/production-evidence/overview-wave2-destination-parity/20260727T225522Z/live-proof.json`

### URL samples (visible filters)

```text
?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed
?page=candidates&review_status=ready&sort=ready_for_review&overview_cohort=ready_for_review&cohort_key=ready_for_review
?page=candidates&assessment_status=awaiting&overview_cohort=assessment_pending&cohort_key=assessment_pending
?page=candidates&overview_cohort=interview_scheduling_debt&interview_status=none&cohort_key=interview_scheduling_debt
?page=candidates&position=ACCOUNTING_EXCEL&overview_cohort=role_active&cohort_key=role_active:ACCOUNTING_EXCEL
?page=overview&overview_scroll=420
```

### Navigation durability

| Check | Result |
|---|---|
| Filters visible in URL | **PASS** |
| Refresh restores cohort | **PASS** (URL is source of truth on load) |
| Back restores Overview + scroll | **PASS** (`overview_scroll` + history state) |
| Direct links work | **PASS** (same query params) |
| Interview filters not dropped | **PASS** (exact debt cohort on Candidates) |
| EN/AR + RTL | **PASS** (Overview locale/`dir` unchanged; destinations are URL-based) |
| Lifecycle / data mutations | **None** (read-only SQL + UI/deploy) |

---

## Health / rollback / restore

| Step | Result |
|---|---|
| Health after orchestrator deploy | **200** |
| Rollback `prehire_overview.py` + `app.py` | Health **200** |
| Restore Wave 2 orchestrator | Health **200**; destinations restored (`role_active`, interview → candidates) |
| Dashboard asset | `dashboard-DDyznYge.js` |
| Dashboard rollback → Wave 1 asset | `dashboard-CelXMCur.js` |
| Dashboard restore Wave 2 | `dashboard-DDyznYge.js`; health **200** |

Rollback artifacts:

- `/opt/wathefni/production-evidence/overview-wave2-destination-parity/20260727T225522Z/prehire_overview.py.before`
- `/opt/wathefni/production-evidence/overview-wave2-destination-parity/20260727T225522Z/prehire_overview.py.after`
- `/opt/wathefni/production-evidence/overview-wave2-destination-parity/20260727T225522Z/app.py.before`
- `/opt/wathefni/production-evidence/overview-wave2-destination-parity/20260727T225522Z/app.py.after`
- `/opt/wathefni/production-evidence/overview-wave2-destination-parity/20260727T225522Z/wathefni-dashboard.wave2-before`

Local unit: `smoke-test-prehire-overview-unit.py` PASS; `dashboardNavigation.test.ts` PASS; `App.test.tsx` PASS.

---

## Intentionally deferred

- Ranking auto-load / score presentation
- Assessments send/resend queue parity (cohort definition unchanged)
- Color / visual redesign

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Stable cohort_key / identifiers on destinations | **PASS** |
| Card count ≡ destination cohort (people + apps) | **PASS** |
| No extra / missing records | **PASS** |
| Filters in URL | **PASS** |
| Refresh preserves cohort | **PASS** |
| Back restores Overview | **PASS** |
| Direct links work | **PASS** |
| Interview destinations keep filters | **PASS** |
| Top-priority opens person/app/action context | **PASS** |
| Role next-step opens role cohort | **PASS** |
| No Ranking logic / assessment definition / color changes | **PASS** |
| No lifecycle/data mutations | **PASS** |
| Health 200 | **PASS** |
| Rollback + restore | **PASS** |

**Wave 2: PASS**
