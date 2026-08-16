# Jobs Consistency Audit — Applicant Counts & Status Aliases

**Date:** 2026-07-30  
**Scope:** Jobs follow-up only (audit; **no implement, no deploy**)  
**Tenant proof:** `WATHEFNI` production  
**Verdict:** **FAIL** vs a single consistent applicant-count / View-candidates contract

Cross-surface Candidates / Assessments / Ranking: **not touched**.

---

## 1. Exact current predicates (as coded)

### A. Inventory “Applications” badge / Applicants tab count

| Layer | Definition |
|---|---|
| Field | `application_count` |
| SQL | `COUNT(*)` of production applications with CV present, **all statuses** |
| Excludes | none of hired / rejected / withdrawn / archived |
| UI | Jobs list Applications column; Job workspace Applicants tab badge + Applications fact |

```43797:43806:wathefni-orchestrator/app.py
                    COUNT(*) AS application_count,
                    COUNT(*) FILTER (WHERE status NOT IN ('hired','rejected')) AS active_count,
                    ...
                    AND COALESCE(data_source, raw_json->>'data_source', 'production')='production'
                    AND (cv_received IS TRUE OR jsonb_typeof(raw_json->'cv') = 'object')
```

```81:114:apps/wathefni-dashboard/src/pages/JobsPage.tsx
  const apps = Number(job.application_count || 0)
  // click → onViewCandidates(job)
```

### B. Jobs `active_count` (close confirm, not the list badge)

| Layer | Definition |
|---|---|
| Field | `active_count` |
| SQL | `COUNT(*) FILTER (WHERE status NOT IN ('hired','rejected'))` |
| Includes | withdrawn, archived, and all non-hired/rejected pipeline statuses |
| UI | Close-job confirm copy (`App.tsx` ~886–887); **not** the Applications badge |

### C. Funnel / `stage_counts`

| Layer | Definition |
|---|---|
| SQL | `GROUP BY status` under the **same** production+CV gate as `application_count` |
| Includes | **all** statuses (hired appears as a funnel row) |
| UI | Job workspace overview funnel |

Sum of `stage_counts[].count` ≡ `application_count` (same gate).

### D. “View candidates”

| Layer | Definition |
|---|---|
| Navigation | `overview_cohort=role_active` + exact `position_code` |
| Predicate | `status NOT IN ('hired','rejected','withdrawn')` |
| Gate | reviewable / CV presence via candidates list base |

```1645:1654:apps/wathefni-dashboard/src/App.tsx
        overview_cohort: 'role_active',
        cohort_key: job.position_code ? `role_active:${job.position_code}` : 'role_active',
```

```139:141:wathefni-orchestrator/prehire_overview.py
def role_active_predicate(alias: str = "a") -> str:
    return f"{alias}.status NOT IN ('hired','rejected','withdrawn')"
```

### Three-way disagreement (same job)

| Metric | hired | rejected | withdrawn | archived |
|---|---|---|---|---|
| `application_count` (badge / funnel sum) | **in** | **in** | **in** | **in** |
| `active_count` (close confirm) | out | out | **in** | **in** |
| `role_active` (View candidates) | out | out | **out** | **in** |

---

## 2. Product decision required: what does “Applicants / Applications” mean?

Two coherent meanings exist today and are **mixed**:

| Meaning | Definition | Matches today |
|---|---|---|
| **Historical total** | All CV’d applications ever attached to the role (including terminals) | Badge + funnel sum (`application_count`) |
| **Active pipeline** | Applications still in hiring work (exclude terminals) | View candidates (`role_active`) — but terminals set differs from `active_count` |

**Recommendation for the proposed contract (awaiting approval):**

1. Treat the clickable Applications control as an **active pipeline** metric aligned with View candidates.
2. Define **active pipeline** = `status NOT IN ('hired','rejected','withdrawn')` (same as `role_active`). Decide explicitly whether **`archived`** is terminal (recommend: exclude from active pipeline as well).
3. Keep a separate **historical total** (`application_count`) available for funnel / reporting, labeled as total applications — not as the View-candidates badge.
4. Align close-confirm with the same active-pipeline predicate (today close uses `active_count`, which still counts withdrawn).

Until approved, do **not** implement.

---

## 3. Live production proof (`WATHEFNI`)

Application statuses present: `hired`, `shortlisted`, `needs_role`, `screening_complete`, `review_pending`, `screening`.  
**No** `rejected` / `withdrawn` / `archived` rows in this tenant right now — contract must still cover them.

| position_code | job_status | application_count (badge) | active_count (jobs) | role_active (View candidates) | Δ badge − View |
|---|---|---:|---:|---:|---:|
| `IT_MAINTENANCE` | open | **1** (hired only) | 0 | **0** | **1** |
| `MARKETING_SPECIALIST` | open | **1** (hired only) | 0 | **0** | **1** |
| `SOCIAL_MEDIA_MANAGER` | closed | **2** (hired+shortlisted) | 1 | **1** | **1** |
| `HR` | open | 2 | 2 | 2 | 0 |
| `FINANCE` | paused | 1 | 1 | 1 | 0 |
| `ACCOUNTING_EXCEL` | closed | 1 | 1 | 1 | 0 |

**Concrete root-cause proof:**

- `IT_MAINTENANCE`: list shows **1** application; View candidates opens `role_active` → **empty list**.
- `SOCIAL_MEDIA_MANAGER`: badge **2**, funnel shows hired+shortlisted; View candidates → **1** (shortlisted only).

Job statuses in DB today are canonical only: `open` (9), `closed` (2), `paused` (1). No leftover `active`/`published`/`inactive` rows in this tenant — alias bugs are latent, not currently visible in WATHEFNI inventory chips.

---

## 4. Job-status alias audit

Canonical lifecycle (`prehire_jobs.py`): `draft | open | paused | closed`  
Transitions: publish `draft→open`, pause `open→paused`, resume `paused→open`, close `*→closed`, reopen `closed→open`.

| Layer | `active` | `published` | `inactive` | Unknown |
|---|---|---|---|---|
| UI badge `normalizedJobStatus` | → **open** | → **open** | stays `inactive` | infer from `active_count` |
| Backend `normalize_status` / serialize | → **open** | → **closed** | → **closed** | → **closed** |
| Jobs list filter `effective_status` | exact match only | exact match only | exact match only | exact |
| Reports open-roles | counts as open | counts as open | not open | — |

**Mismatch:** UI treats `published` as Open; backend serialize + schema treat `published` as Closed; Open filter chip never matches raw `active`/`published` rows.

Lifecycle actions already emit canonical statuses only — reopen is `closed→open` (no separate `reopened` status).

---

## 5. Test matrix coverage (audit — expected outcomes under current code)

| Job state | Apps mix | Badge (`application_count`) | Funnel sum | View candidates (`role_active`) | Current consistent? |
|---|---|---|---|---|---|
| open | only pipeline | N | N | N | yes |
| open | + hired | N+hired | N+hired | N | **no** |
| open | + rejected | N+rej | N+rej | N | **no** |
| open | + withdrawn | N+w | N+w | N (excludes w) | **no**; also `active_count` still includes w |
| open | + archived | N+a | N+a | N+a (archived still in) | **ambiguous** |
| paused / closed / reopened→open | any | same predicates | same | same | status chip OK if DB canonical |
| legacy job `published` | — | badge Open | — | — | filter Open **misses**; serialize Closed |

Existing automated coverage does **not** pin these count contracts (`JobsPage.test.tsx` clicks View candidates but does not assert cohort; no unit test for `application_count` vs `role_active`).

---

## 6. Root cause

1. **Primary:** Applications badge and funnel use **historical total** (`application_count` / full `stage_counts`); the same clickable control opens **active pipeline** (`role_active`), so count and list disagree whenever terminals exist.
2. **Secondary:** `active_count` (close confirm) is a third predicate — excludes hired/rejected but **not** withdrawn — so it matches neither the badge nor View candidates.
3. **Status aliases:** UI, filter SQL, backend normalize, and reports use **different** alias tables for `active` / `published` / `inactive`.

---

## 7. Exact files

| Area | Path |
|---|---|
| Count SQL | `wathefni-orchestrator/app.py` `_dashboard_prehire_positions_query` (~43792–43922) |
| Serialize | `wathefni-orchestrator/prehire_jobs.py` `serialize_job`, `normalize_status` |
| role_active | `wathefni-orchestrator/prehire_overview.py` `role_active_predicate` |
| Candidates cohort apply | `wathefni-orchestrator/app.py` (~47914–47984) |
| List badge + click | `apps/wathefni-dashboard/src/pages/JobsPage.tsx` |
| Workspace funnel / Applicants tab | `apps/wathefni-dashboard/src/components/JobWorkspace.tsx` |
| View candidates nav | `apps/wathefni-dashboard/src/App.tsx` `viewJobCandidates` |
| UI status alias | `apps/wathefni-dashboard/src/pages/shared/format.ts` `normalizedJobStatus` (+ duplicate in JobWorkspace) |
| Status chips | `JobsPage.tsx` ~417–423 |
| Reports alias drift | `wathefni-orchestrator/reports_metrics.py` ~90 |

---

## 8. Proposed Jobs applicant-count contract (for approval)

Named scopes (one shared helper each; list badge / CTA / funnel / close must cite them explicitly):

| Scope ID | Predicate (CV + production gate unchanged) | Intended use |
|---|---|---|
| `jobs.applications_total` | all statuses | Historical total; funnel sum; reports “applications” |
| `jobs.active_pipeline` | `status NOT IN ('hired','rejected','withdrawn'[, 'archived'])` | Applications badge **if** it opens View candidates; close confirm; Overview role pressure |
| `jobs.role_active_candidates` | **identical** to `jobs.active_pipeline` + exact `position_code` | View candidates list |

**Status contract:** single alias map shared by filter SQL, badge, serialize, schema rewrite, reports:

- `active`, `published` → `open`
- `inactive` → `closed`
- canonical: `draft|open|paused|closed` only after normalize

**Lifecycle:** unchanged transitions; reopen remains `closed→open` (no `reopened` status).

**UI (when implementing later — not this audit):** badge number driving “View candidates” must equal the candidates list total for that role under `jobs.active_pipeline`. Funnel may still show historical stages including hired, with total labeled separately if needed.

---

## 9. PASS / FAIL

| Check | Result |
|---|---|
| Badge ≡ View candidates list for every job | **FAIL** (`IT_MAINTENANCE`, `MARKETING_SPECIALIST`, `SOCIAL_MEDIA_MANAGER`) |
| Funnel sum ≡ badge | **PASS** (same `application_count` gate) |
| `active_count` ≡ `role_active` | **FAIL** (withdrawn divergence; latent) |
| Job status alias display ≡ filter ≡ serialize | **FAIL** (latent; no legacy rows in WATHEFNI today) |
| Automated contract tests for counts | **FAIL** (missing) |
| Implementation / deploy | **NOT STARTED** (audit only) |

---

## 10. Out of scope

- No UI redesign in this phase  
- No deployment  
- Candidates / Assessments / Ranking follow-ups unchanged  

**Next step after owner approval of §8:** implement shared predicates + tests + prove the three live mismatch jobs, then deploy.
