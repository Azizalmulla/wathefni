# Interviews Consistency Audit — Cancelled Counts

**Date:** 2026-07-30  
**Stamp:** audit-only (no deploy)  
**Tenant:** `WATHEFNI`  
**Verdict:** Root cause proven against live DB. Contract proposed. Implementation **not** deployed.

---

## User observation

After cancelling two interviews:

| Tab badge | Observed |
|---|---:|
| Upcoming | empty (correct) |
| Needs feedback | **1** |
| Video | **3** |
| Completed | **2** |
| All | **4** |

---

## Live Hamad Almulla records (production proof)

| id8 | status | type | feedback_status | human_feedback_status | async_status |
|---|---|---|---|---|---|
| `06e4a65d` | **cancelled** | async_video | notes_pending | notes_pending | consented |
| `8552e251` | **cancelled** | async_video | notes_pending | notes_pending | link_sent |
| `669366ae` | completed | async_video | notes_pending | feedback_complete | completed |
| `369997d8` | completed | live | feedback_complete | notes_pending | — |

Company-wide scoped counts (CV-exists via applications, same as dashboard) **exactly** match the badges:

| Tab | Live count | Which Hamad rows |
|---|---:|---|
| Upcoming | 0 | none |
| Needs feedback | **1** | **`369997d8` only** (not the cancelled ones) |
| Video | **3** | `06e4a65d`, `8552e251`, `669366ae` |
| Completed | 2 | `669366ae`, `369997d8` |
| Cancelled | 2 | `06e4a65d`, `8552e251` |
| All | 4 | all four |

### Exact inclusion reasons

1. **Upcoming empty** — cancel set `status='cancelled'`; Upcoming requires `scheduled|rescheduled`. Correct.
2. **Video = 3 includes both cancelled** — Video list + `video_count` filter only on `interview_type/source = async_video` with **no status exclusion**. Cancelled videos remain.
3. **All = 4** — All is the sum of every status bucket. Cancel moves Upcoming→Cancelled; **All does not drop**. Feels “inflated” but is historically consistent with “All”.
4. **Needs feedback = 1 is NOT the cancelled interviews** — Needs feedback SQL requires `status='completed'`. Cancelled rows are excluded. The remaining **1** is live completed `369997d8` where `COALESCE(human_feedback_status, feedback_status, …)` prefers stale `human_feedback_status=notes_pending` over `feedback_status=feedback_complete`.
5. **Completed = 2** — both completed rows; cancel correctly did not remove them.

Cancel UPDATE (`interview_service.py`) sets `status='cancelled'` only — it **retains** `feedback_status`, `human_feedback_status`, `async_status`, video answers. That is fine for history; the bug is that Video (and partially Needs-feedback COALESCE) still read those fields / type without excluding terminals.

---

## Root cause

**Primary:** Video tab list predicate and `video_count` ignore terminal status → cancelled async interviews stay in Video badge and Video list.

**Secondary:** Needs-feedback SQL uses `COALESCE(human, legacy)` so a stale human `notes_pending` can keep a completed interview in Needs feedback even when legacy is `feedback_complete`. Separate from cancel, but explains the “Needs feedback 1” after cancel.

**Not a root cause for Needs feedback / Completed inflation via cancel:** cancel does not leave cancelled rows in those SQL buckets.

**Invalidation:** `afterInterviewAction` does invalidate interviews queries; `keepPreviousData` can briefly show prior badges but live DB proves durable Video/All membership, not only stale UI.

---

## Exact files

| Area | Path |
|---|---|
| List + counts | `wathefni-orchestrator/app.py` `dashboard_interviews_payload` (~46745–47035) |
| Cancel mutation | `wathefni-orchestrator/interview_service.py` `cancel_interview` (~1162–1174) |
| Tab badges | `apps/wathefni-dashboard/src/pages/InterviewsPage.tsx` (~151–168) |
| Query wiring | `apps/wathefni-dashboard/src/lib/query/useDashboardServerState.ts`, `invalidation.ts` |
| Presentation feedback | `wathefni-orchestrator/interview_presentation.py` `canonical_feedback_state` |
| **New contract** | `wathefni-orchestrator/interview_queue_contract.py` |
| **New tests** | `wathefni-orchestrator/test_interview_queue_contract.py` |

---

## Proposed tab contract (approve before implement)

Default: **terminal cancelled / no-show must not appear in active work or Video type queues.** History stays in Cancelled / No-shows / All. Cancel may retain feedback/video fields; queues must ignore them for membership.

| Tab | Membership predicate | Cancelled/no-show? |
|---|---|---|
| **Upcoming** | `status ∈ {scheduled, rescheduled}` | No |
| **Needs feedback** | `status = completed` AND feedback not complete (either human **or** legacy `feedback_complete` counts as complete; structured submission wins when present) | No |
| **Video** | async_video type/source AND `status ∉ {cancelled, no_show}` | No |
| **Completed** | `status = completed` | No |
| **No-shows** | `status = no_show` | Yes (this tab) |
| **Cancelled** | `status = cancelled` | Yes (this tab) |
| **All** | no status filter (history) | Yes |

**List results and tab counts must use the same predicates and the same scope** (company + CV-exists + module kind + assignment + visibility).

**Cancel / feedback / video state policy:** retain fields for history; clear nothing required for this fix; membership ignores stale pending feedback once terminal.

### Expected Hamad matrix after contract

| Tab | Count | Rows |
|---|---:|---|
| Upcoming | 0 | — |
| Needs feedback | **0** | conflict resolved; cancelled excluded |
| Video | **1** | `669366ae` only |
| Completed | 2 | both completed |
| Cancelled | 2 | both cancelled |
| All | 4 | all |

---

## Tests — PASS/FAIL

| Suite | Result |
|---|---|
| `test_interview_queue_contract.py` (contract predicates + Hamad fixtures + divergence docs) | **PASS** (locks approved contract; documents current inflation) |
| Current `app.py` still has divergent Video / COALESCE Needs-feedback SQL | **FAIL vs contract** (expected until implementation) |
| Deploy | **NOT RUN** (awaiting contract approval) |

---

## Cross-surface consistency scan (findings only)

| Surface | Verdict | Evidence |
|---|---|---|
| **Jobs** | **MISMATCH** | Applicants/funnel include hired/rejected; “View candidates” uses `role_active` excluding them. Open chip aliases (`active`/`published`→`open`) can diverge from filter. |
| **Candidates** | **MISMATCH** | Stage badge forces Talent Pool → “New”, but Stage filter “New” does not include `needs_role`/`import_review`. Offer stage display-only. List `total` otherwise aligns with filters. |
| **Assessments** | **MISMATCH** | Cohort badges vs attempt `status_counts` vs client queue re-filter; company-wide counts vs assignment-scoped list; cancelled in attempt counts but not Send cohorts. |
| **Ranking** | **MISMATCH** | Header “matching” uses full non-terminal pool (`total_matching`), not `eligible_count`. |

No redesign performed on these surfaces.

---

## Approval gate

Do **not** deploy Interviews count fixes until this tab matrix and state policy are approved. After approval, implementation should:

1. Align Video list + `video_count` with terminal exclusion.
2. Align Needs-feedback list + `feedback_counts` with either-complete (or canonical submission) authority.
3. Ensure count queries apply the same scope as the list.
4. Keep cancel field retention; membership-only change.
5. Re-run contract tests + live Hamad matrix as PASS before cutover.
