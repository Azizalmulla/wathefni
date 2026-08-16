# Reports Page — Correctness & Clarity Audit (Pre-UI)

**Date:** 2026-07-30  
**Scope:** Reports page only — **audit; no implement; no deploy**  
**Structure to preserve:** leadership Overview · Breakdowns · Exports · cream/ink  
**Tenant proof:** `WATHEFNI` (`live-proof.json`)  
**UX / correctness verdict:** **FAIL**  
**Visual direction:** Leave alone (structure looks strong)

**Canvas:** `reports-page-ux-audit.canvas.tsx`

---

## Exact purpose

Reports is the **company leadership snapshot + CSV export desk**: read-only hiring performance for the tenant — headline counts, breakdowns, and downloads. It does **not** mutate lifecycle, send assessments, schedule interviews, or soft-rank candidates.

| Surface | Owns | Does **not** own |
|---|---|---|
| **Reports** | Leadership metrics, breakdowns, CSV exports (unit + current/history declared) | Day-to-day work queues |
| **Overview** | Today’s action CTAs / people-first work queue | Spreadsheet export, full historical inventory |
| **Jobs** | Opening lifecycle + active-pipeline applicant counts | Leadership export desk |
| **Candidates** | Pipeline list + stage contract + application authority | Aggregate leadership cards |
| **Interviews** | Interview queue tabs (`interview_queue_contract`) | Leadership “needing action” redefined locally |
| **Assessments** | Cohorts / attempts / needs-review (`assessments_queue_contract`) | Reports page assessment “needing action” math |
| **Ranking** | Job-scoped advisory review order | Export / leadership totals |

---

## Current structure (preserve)

| Block | What exists |
|---|---|
| Overview | Six Info cards (Open roles, Active applications, Ready for review, Interviews needing action, Assessments needing action, Current follow-ups) |
| Breakdowns | Stage · Assessment status · Interview status · Applications by role |
| Exports | Up to six download cards with unit + current/history caption |
| Visual | Shared cream/ink cards — **do not redesign** |

Primary files: `ReportsPage.tsx`, `App.tsx` (`exportReport`), `api.ts` (`getPrehireReports` / `downloadPrehireReport`), `types.ts` `PrehireReportsResponse`, backend `GET /dashboard/prehire/reports` + `/export`, `reports_v1.py`, `reports_metrics.py`, `prehire_overview.compute_action_counts`.

---

## Overview metrics → predicates (locked contracts)

| UI label | What UI actually computes | Exact backend authority today | Correct contract should be | Live `WATHEFNI` |
|---|---|---|---|---|
| **Open roles** | `metrics.open_roles` | `reports_metrics`: `positions` with `jobs_queue_contract.effective_job_status_sql` = `open` | `jobs` open-status aliases — **aligned** | **9** |
| **Active applications** | Client sum of stage rows excluding labels hired/rejected/withdrawn/closed | Stage SQL: **all company apps with CV**, **no** `reviewable` / production gate | `jobs.active_pipeline` under reviewable/production+CV | UI **12** vs pipeline **7** |
| **Ready for review** | `metrics.ready_for_review` ← `compute_action_counts` | `prehire_overview.ready_for_review_predicate` + overview `reviewable_predicate` (people unit) | Same as Overview — **label OK; unit must stay people** | **2** (Overview parity) |
| **Interviews needing action** | `(summary.interview_scheduled\|completed\|no_show)` — **fields absent** → always **0** | Should be `prehire_overview.interview_scheduling_debt` (apps needing schedule) **or** Interviews `needs_feedback` — not “all interviews” | Debt / needs-feedback contract | UI **0** vs debt **4** |
| **Assessments needing action** | `assessment_pending + assessment_completed` | Attempt status sums from `reports_metrics` (raw attempt statuses) | Attempt attention (`pending`/`in_progress`/`expired`) **or** Overview assessment pending — **never include completed** | UI **2** (1+1) vs pending-only **1** vs Overview `assessment_pending` **2** |
| **Current follow-ups** | `metrics.followups_current` ← `follow_up_needed` | `prehire_overview.follow_up_needed_exists` via action_counts | Same as Overview — **OK** | **2** |

### Tenant / visibility / assignment / lifecycle

| Gate | Reports JSON (`GET /reports`) | Export (`GET /reports/export`) |
|---|---|---|
| Tenant `company_code` | Yes | Yes |
| Production / TEST filter | **Inconsistent** — action_counts & most exports use reviewable/production; **stage + by-role breakdown omit reviewable** | Reviewable SQL on rows |
| Assignment / visibility | **Not applied** to metrics/breakdowns (company-wide) | Applied post-query when `apply_assignment_scope` |
| Lifecycle | Mixed — Overview cards use action predicates; stage/role use inventory-style counts | Per export type |

Live leak probe: **5** non-production / held / TEST-shaped apps sit inside the stage-breakdown scope (`non_production_or_held_in_stage_scope=5`), including **Needs role** rows in the stage chart.

---

## Breakdowns

### Applications by current stage
- Source preferred: `metrics.breakdowns.applications_by_stage` (`reports_metrics.merge_stage_breakdown`).
- **Does not** use `candidates_stage_contract` buckets (Talent Pool ≠ New; legacy `offered`/`offer_sent` → Shortlisted; Unknown).
- Labels merge some aliases to “Ready for review” but still emit **Needs role**, **Waiting for CV**, raw-ish inventory — not Candidates stage axis.
- Scope: CV-present apps **without** reviewable → includes held/non-production.
- Live stage “Ready for review” **3** ≠ Overview ready **2**.

**Proposed:** `reports.breakdown.applications_by_stage` = reviewable ∧ Candidates stage buckets; unit = applications; exclude Talent Pool/held from lifecycle bars or label them out-of-stage.

### Applications by role
- SQL: same CV-present, no reviewable, `LIMIT 50`, all statuses.
- UI title does **not** say active pipeline vs historical total.
- Product rule in `reports_metrics` docstring says “current”; Jobs contract distinguishes `applications_total` vs `active_pipeline`.

**Proposed:** declare `reports.breakdown.applications_by_role.scope = active_pipeline | historical_total` and match Jobs predicates.

### Assessment status
- Groups `assessment_attempts.status` under reviewable join — **attempt unit** (good vs cohort).
- Labels are **raw enums** (`pending`, `expired`, `completed`) — not Assessments vocabulary / `ASSESSMENT_STATE_LABELS` in `reports_v1`.
- Not cohort counts (good), but not presentation-normalized (fail clarity).

### Interview status
- Groups `candidate_interviews.status` under reviewable — interview unit.
- Raw enums (`cancelled`, `completed`); no `interview_queue_contract` tab predicates / alias normalize (`noshow`→`no_show`).
- Does not surface Needs feedback (feedback-complete authority).

---

## Exports

| Card | Displayed count (UI) | Actual CSV rows (live) | Scope claim | Verdict |
|---|---|---|---|---|
| Candidate applications | `exports.candidate_rows` **10** | **10** | current · application | **PASS** count |
| Roles | `exports.role_rows \|\| openRoles` → **9** | **12** (all roles) | current · role | **FAIL** — open ≠ export universe; `role_export_total` metric **20** unused |
| Assessments | `exports.assessment_rows` **5** | **5** | current · attempt | **PASS** count |
| Interviews | Gated by `interviewTotal` (**0**) → **card often hidden**; if shown would use `exports.interview_rows` **2** | **4** | current · interview | **FAIL** visibility + count |
| Current follow-ups | `followupsCurrent` **2** | **2** | current · application | **PASS** count (payload `exports.followup_rows` is wrongly **21** delivery events — UI luckily ignores it) |
| Delivery failure history | delivery metric **21** | **21** | history · event | **PASS** count |

Other export notes:
- Server enforces `report.export` + module gates — **PASS**.
- Assignment scope filtered on download for scoped roles — **PASS** server-side; displayed counts remain company-wide → recruiters may see count ≠ their file.
- Failed download: `App.exportReport` notice error — **PASS**; empty download not specially messaged beyond 0 records badge.
- Unit labels: mostly correct; Roles card understates universe; Follow-ups payload key is misnamed historically.

---

## Arabic / RTL / mobile / states / Profiler

| Topic | Reality | Rank |
|---|---|---|
| AR / RTL | `dir="ltr"` hardcoded; EN-only strings; no `locale` prop | High |
| Mobile stacking | `md`/`xl` grids OK; no dedicated AR stacking | Leave alone (layout) / Medium (copy) |
| Loading | Initial spinner + refreshing line | Leave alone |
| Error | Generic “will appear once loaded” — no failed-load state | Medium |
| Stale / partial | `reports_metrics` build failure swallowed; UI may mix summary + missing metrics | High |
| React Profiler | **None** on Reports; export/refresh unmarked | High (evidence gap) |

---

## Ranked findings

### Critical
1. **“Interviews needing action” is always 0** — reads missing `summary.interview_*` fields; live debt **4**. Interviews export card also gated on that zero.
2. **“Assessments needing action” includes completed attempts** — pending+completed; contradicts “needing action” and diverges from Overview assessment pending.
3. **Stage / by-role breakdowns omit production+reviewable** — **5** held/non-production apps in stage scope; **Needs role** appears in leadership stage chart.

### High
4. **Active applications ≠ `jobs.active_pipeline`** — client stage-label math **12** vs pipeline **7**.
5. **Stage breakdown ≠ Candidates stage contract** — missing Talent Pool/`offered` rules; Ready label count ≠ Overview ready.
6. **Export count parity broken** for Roles (9 vs 12) and Interviews (hidden / 2 vs 4).
7. **Raw assessment & interview enum labels** in breakdowns.
8. **No AR/RTL** on a page that other desks localize.
9. **No React Profiler / interaction marks** for load, refresh, export.
10. **Dual payload authorities** (`reports_v1` funnel wrongly named `applications_by_stage` vs `reports_metrics`) — silent metrics failure leaves inconsistent UI.

### Medium
11. **Applications by role scope unlabeled** (historical inventory vs active pipeline).
12. **Assignment visibility** only on export rows, not on Overview/breakdown numbers.
13. **Types `PrehireReportsResponse` stale** vs live `metrics` / summary keys.
14. **Weak error empty state** when fetch fails.

### Leave alone
- Overview → Breakdowns → Exports composition and cream/ink look.
- Privacy denylist + `report.export` entitlement + confirm-before-download.
- Delivery failure history as separate historical export.
- Module-gated Assessments block when assessments off.
- Candidate / assessment / follow-up / delivery export row counts that already match (when cards visible).

---

## Proposed contracts (implement later — not now)

```
reports.overview.open_roles          = jobs open-status (positions)
reports.overview.active_applications = jobs.active_pipeline ∧ reviewable
reports.overview.ready_for_review    = prehire_overview.ready_for_review (people; Overview parity)
reports.overview.interviews_action   = interview_scheduling_debt OR interviews.needs_feedback (pick one; label must match)
reports.overview.assessments_action  = attempt attention statuses OR Overview assessment_pending (exclude completed)
reports.overview.followups_current   = follow_up_needed (Overview parity)

reports.breakdown.stage              = Candidates stage buckets ∧ reviewable; no held-as-lifecycle
reports.breakdown.role               = declare active_pipeline | historical_total; Jobs predicates
reports.breakdown.assessment_status  = assessments.attempt.* + vocabulary labels
reports.breakdown.interview_status   = interview_queue_contract normalize + human labels

reports.export.count                 = displayed count ≡ CSV row count ≡ export query universe
reports.export.roles                 = all roles (status column); do not show open_roles as the count
reports.export.interviews            = always offer when module on; count = interview rows
```

Profiler (later): `reports:overview|breakdowns|exports` commits; marks `reports_page_load`, `reports_refresh`, `reports_export`.

---

## Exact files

### Dashboard
- `apps/wathefni-dashboard/src/pages/ReportsPage.tsx`
- `apps/wathefni-dashboard/src/App.tsx` (`exportReport`, LazyReportsPage props)
- `apps/wathefni-dashboard/src/lib/api.ts`
- `apps/wathefni-dashboard/src/types.ts` (`PrehireReportsResponse`)
- `apps/wathefni-dashboard/src/lib/perf/dashboardPerf.ts` (absent wiring)

### Backend
- `wathefni-orchestrator/app.py` (`dashboard_prehire_reports`, `dashboard_prehire_report_export`)
- `wathefni-orchestrator/reports_v1.py`
- `wathefni-orchestrator/reports_metrics.py`
- `wathefni-orchestrator/prehire_overview.py`
- Locked peers: `candidates_stage_contract.py`, `jobs_queue_contract.py`, `assessments_queue_contract.py`, `interview_queue_contract.py`

### Evidence
- `ops/evidence/reports-page-ux-audit-20260730/live-proof.json`
- `ops/evidence/reports-page-ux-audit-20260730/prove-reports-audit-live.py`

---

## Tests / live — PASS/FAIL

| Check | Result |
|---|---|
| Structure / cream visual preserve recommendation | **PASS** (leave alone) |
| Open roles ↔ jobs open | **PASS** |
| Ready for review ↔ Overview action_counts | **PASS** (value) |
| Current follow-ups ↔ Overview | **PASS** |
| Active applications ↔ active_pipeline | **FAIL** |
| Interviews needing action correctness | **FAIL** |
| Assessments needing action correctness | **FAIL** |
| Stage ↔ Candidates stage contract + reviewable | **FAIL** |
| Assessment/interview labels normalized | **FAIL** |
| Export displayed ≡ downloaded (all cards) | **FAIL** (roles, interviews) |
| Test/held leakage into stage | **FAIL** (5 in scope) |
| AR/RTL | **FAIL** |
| React Profiler evidence | **FAIL** (absent) |
| Server export permission | **PASS** |
| **Overall** | **FAIL** |

---

## Implementation / deploy

**Not started** (audit only). Do not change predicates or UI until contracts above are approved.
