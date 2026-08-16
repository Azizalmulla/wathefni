# Assessments Consistency Audit — Cohorts, Attempts & Counts

**Date:** 2026-07-30  
**Scope:** Assessments follow-up only (audit; **no implement, no deploy**)  
**Tenant proof:** `WATHEFNI` production  
**Verdict:** **FAIL** vs a single consistent cohort / attempt / scope contract  

Ranking: **not touched**. No visual redesign.

Evidence: `ops/evidence/assessments-consistency-audit-20260730/live-proof.json`

---

## 1. Page purpose (as producted today)

Assessments is an **HR operational surface** with three top tabs:

| Tab | Purpose | Unit |
|---|---|---|
| **Send** | Actionable **application cohorts** (ready / resend / delivery failed / in progress / sent pending) | Applications (latest attempt) |
| **Attempts** | Chronological **attempt** history (all statuses) | Attempts (every row) |
| **Reports** | Completed reports for review | Attempts (client slice of current page) |

Cohorts answer “who needs send/resend?”. Attempts answer “what invitations exist?”. Mixing their counts on the same metric strip is the core consistency failure.

Authority modules: `assessment_cohorts.py` (cohorts), `dashboard_assessments_payload` (attempts), `assessment_lifecycle.py` (canonical attempt statuses).

---

## 2. Exact current authorities

### A. Assessment cohorts (Send badges + opened Send queue)

| Layer | Definition |
|---|---|
| Module | `wathefni-orchestrator/assessment_cohorts.py` |
| Eligibility | `application.status ∈ {screening_complete, review_pending, ready_for_review, shortlisted}` |
| Gate | `reviewable` = production + CV exists |
| Attempt facet | **Latest** attempt only (`ORDER BY updated_at DESC, created_at DESC LIMIT 1`) |
| Scope | **Company-wide** — **no** assignment / visibility SQL |
| UI source | `summary.assessment_cohorts.cohorts` → `peopleFor()` prefers `application_count` |

| Cohort key | Predicate (latest attempt) |
|---|---|
| `assessment_ready_to_send` | eligible ∧ status empty |
| `assessment_sent_pending` | eligible ∧ `pending` ∧ ¬delivery_failed |
| `assessment_in_progress` | eligible ∧ `in_progress` ∧ ¬delivery_failed |
| `assessment_expired` / `assessment_resend_needed` | eligible ∧ `expired` (alias; same rows) |
| `assessment_delivery_failed` | eligible ∧ status∈{pending,in_progress} ∧ delivery∈{failed,send_failed,invitation_failed} |
| `assessment_completed` | eligible ∧ `completed` |
| `assessment_attention` | eligible ∧ pending\|in_progress\|expired (aggregate; not a Send CTA) |

Actionable send cohorts are mutually exclusive. Cancelled latest attempt → **no cohort** (`classify_attempt_state` → `None`).

Opened Send list: `GET …/applications?overview_cohort=assessment_*` uses the **same** `cohort_predicate`, but under **detail visibility** (assignment-scoped for hybrid/assigned_only recruiters).

### B. Attempt `status_counts` + Attempts total

| Layer | Definition |
|---|---|
| Endpoint | `GET /dashboard/prehire/assessments` → `dashboard_assessments_payload` |
| SQL | `COUNT(*) GROUP BY aa.status` over **every** attempt row |
| Gate | reviewable application join |
| Scope | Summary plan: company-wide under **hybrid**; list rows use detail assignment |
| Includes | `pending`, `in_progress`, `completed`, `cancelled`, `expired` |
| `total` | **sum(status_counts)** — all statuses |

Comment in code explicitly allows summary counts company-wide while list is scoped (`app.py` ~48667–48668, 52801–52808).

### C. Client re-filters

| Surface | Code | Behavior |
|---|---|---|
| Send queue rows | `assessmentQueue` (`format.ts` ~177–207) | Re-classifies server rows; **extra** `application.cv?.received` (stricter than backend reviewable OR raw CV object) |
| Needs review metric | `AssessmentsPage.tsx` ~115 | `completed && review_status !== 'reviewed'` on **loaded attempts page only** |
| Reports list | ~116–117 | `completedAttempts.slice(0, 6)` from current page |

Backend also computes `needs_review_count` from the **presented page** (~48764–48775); frontend types **omit** the field and recompute locally.

### D. Metric strip dual sources

```210:218:apps/wathefni-dashboard/src/pages/AssessmentsPage.tsx
Ready to send / Resend / Delivery failed → cohort application_count only
In progress / Completed → peopleFor(cohort) || status_counts[status]
Needs review → page-local attempts
Average score → assessments.average_percent (summary_where)
```

So In progress / Completed can silently switch from **eligible latest-app cohort** to **all-attempt status_counts** when the cohort is 0.

---

## 3. Status → queue membership (current)

Canonical attempt statuses (`assessment_lifecycle.py`):  
`pending | in_progress | completed | cancelled | expired`

Canonical delivery: `pending | sent | failed | intentionally_skipped`  
(cohorts also accept legacy `send_failed`, `invitation_failed`)

Review: `unreviewed | reviewed` (facet, not attempt status)

| State | Send cohort? | Attempts list / status_counts? | Notes |
|---|---|---|---|
| No attempt | ready_to_send | no | |
| pending + good delivery | sent_pending | yes | |
| in_progress + good delivery | in_progress | yes | |
| pending/in_progress + failed delivery | delivery_failed | yes (as pending/in_progress) | delivery facet |
| expired | resend_needed | yes | |
| completed | completed (no Send CTA tab) | yes | Reports / Needs review |
| cancelled | **none** | **yes** | Inflates Attempts total |
| review unreviewed | n/a | Needs review metric (page-local) | |
| scored / submitted / incomplete | — | — | **Not** attempt statuses |

Presentation maps cancelled → `assessment_attention` (`assessment_presentation.py` ~205–206), but attention SQL **excludes** cancelled — presentation/cohort mismatch.

---

## 4. Units: cohorts vs attempts (must stay separate)

| Authority | Unit | Multi-attempt rule |
|---|---|---|
| Cohorts / Send queue | **Applications** (operational) / people also published | **Latest** attempt only |
| Attempt status_counts / Attempts total / Average | **Attempts** | **Every** row |
| Needs review / Reports (UI today) | Attempts on **current page** | Page-local |

Live proof of unit mix (WATHEFNI):

| Metric | Value |
|---|---:|
| `status_counts.expired` | **3** |
| Resend cohort apps | **2** |
| Cause | `TING_EXCEL` has latest=`pending` + superseded `expired`; expired still in attempt counts |

---

## 5. Scope matrix (tenant / assignment / visibility)

| Payload | Tenant | Assignment | Lifecycle |
|---|---|---|---|
| Cohort badges (`compute_assessment_cohorts`) | company | **None** | reviewable + eligible + latest |
| Send opened list | company | **Detail** (hybrid → assigned) | same cohort SQL |
| Attempts list | company | **Detail** | all attempts |
| Attempt status_counts / average | company | Summary (hybrid → **company-wide**) | all statuses |
| Needs review / Reports UI | company | page of detail list | client filter |

Under **hybrid**, a recruiter can see company-wide Send badges larger than their assignment-scoped opened queue — by design of visibility today, **FAIL** vs “counts ≡ opened results” consistency.

---

## 6. Live proof (WATHEFNI, company-wide / no assignment)

| Check | Result |
|---|---|
| Cohort badge apps ≡ opened list total (all cohort keys) | **PASS** (unscoped) |
| Ready 2 / Resend 2 / Sent pending 1 / Completed 1 / In progress 0 / Delivery failed 0 | recorded |
| Attempt status_counts | expired 3, pending 1, completed 1; **total 5** |
| expired attempts ≠ resend cohort | **FAIL** (3 vs 2) — unit divergence |
| Cancelled attempts | **0** live (latent code FAIL) |
| Needs review company vs first page | 0 = 0 (no divergence today; mechanism still page-local) |
| Dual-source In progress/Completed | numbers match today; **code still dual** |

---

## 7. Root cause

1. **Primary:** Three count authorities — **cohorts** (latest eligible apps, company-wide), **attempt status_counts** (every attempt, hybrid-company summary), **client page filters** (Needs review / Reports) — presented as one metric strip.
2. **Secondary:** Send badges ignore assignment scope while opened Send lists apply it (hybrid/assigned_only).
3. **Tertiary:** Cancelled (and superseded expired) inflate Attempts totals without belonging to any send cohort; presentation labels cancelled as attention without SQL membership.
4. **Quaternary:** Client `assessmentQueue` and `cv?.received` can drop rows the server returned; In progress/Completed fall back across unit boundaries.

---

## 8. Exact files

| Area | Path |
|---|---|
| UI metrics / tabs / Needs review / Reports | `apps/wathefni-dashboard/src/pages/AssessmentsPage.tsx` |
| Client queue re-filter | `apps/wathefni-dashboard/src/pages/shared/format.ts` (`assessmentQueue`) |
| FE cohort keys | `apps/wathefni-dashboard/src/lib/assessmentCohorts.ts` |
| Queue fetch | `apps/wathefni-dashboard/src/lib/query/fetchers.ts` |
| Wiring | `apps/wathefni-dashboard/src/App.tsx` (~2391–2501) |
| Types omit `needs_review_count` | `apps/wathefni-dashboard/src/types.ts` (`AssessmentsResponse`) |
| Cohort authority | `wathefni-orchestrator/assessment_cohorts.py` |
| Attempt statuses | `wathefni-orchestrator/assessment_lifecycle.py` |
| Presentation / cancelled→attention | `wathefni-orchestrator/assessment_presentation.py` |
| Attempts payload + counts | `wathefni-orchestrator/app.py` (`dashboard_assessments_payload`, route ~52792) |
| Cohort list filter | `wathefni-orchestrator/app.py` (~48003–48027) |
| Visibility hybrid | `wathefni-orchestrator/prehire_visibility.py` |
| Overview embed | `wathefni-orchestrator/prehire_overview.py` |

---

## 9. Proposed Assessments contract (for approval)

Named scopes — **do not mix cohort application counts with attempt counts** on the same badge unless labeled as attempts.

### Axis separation

| Axis ID | Meaning | Unit | Attempt rule |
|---|---|---|---|
| `assessments.cohort.*` | Send / resend / delivery / in-progress / sent-pending / completed queues | Applications | **Latest** only |
| `assessments.attempt.*` | Attempts tab history + status breakdown | Attempts | **Every** row |
| `assessments.review.*` | Needs review / report-ready | Attempts | Completed + review facet |

### Cohort membership (unchanged predicates; shared for badge ≡ opened list)

Keep current `cohort_predicate` sets. Require:

1. Badge count, segment count, and opened list `total` use the **same** predicate **and the same visibility/assignment scope** (detail scope for both, or document company-wide oversight-only badges separately).
2. No client re-filter that can drop server rows (`assessmentQueue` becomes identity / display-only, or matches backend gates exactly including CV OR).
3. Cancelled latest attempt: **not** in any send cohort; optionally a dedicated non-actionable terminal or Attempts-only.
4. Superseded expired attempts: visible in Attempts/`status_counts.expired`; **not** in Resend cohort (latest wins) — badge must not use raw `status_counts.expired`.

### Attempt status policy

| Status | Cohort axis | Attempt axis |
|---|---|---|
| *(none)* | ready_to_send | — |
| pending | sent_pending or delivery_failed | counted |
| in_progress | in_progress or delivery_failed | counted |
| expired | resend_needed | counted |
| completed | completed (non-send) | counted; feeds review/reports |
| cancelled | **excluded** | counted; terminal; not attention SQL |

Delivery failed remains a **delivery facet** on pending/in_progress, not a separate attempt status.

### Metrics strip (proposed)

| Metric | Authority |
|---|---|
| Ready / Resend / Delivery failed / Sent pending | `assessments.cohort.*` application_count only |
| In progress (Send context) | cohort `assessment_in_progress` only — **no** status_counts fallback |
| Completed (Send/overview context) | cohort `assessment_completed` application_count (or people if product chooses people — pick one and stick) |
| Attempts total / per-status chips on Attempts tab | `assessments.attempt.status_counts` only |
| Needs review | company-or-scoped `assessments.review.needs_review` (not page-local); badge ≡ opened filter |
| Average score | attempt axis completed scores, same scope as Attempts summary |
| Reports tab | attempt-axis completed (+ report ready), same scope as list — not `slice(0,6)` of current page as the only total |

### Out of scope for this contract

Ranking, UI redesign, changing eligible application stages, inventing new attempt statuses (`submitted`/`scored`/`incomplete`).

---

## 10. PASS / FAIL

| Check | Result |
|---|---|
| Cohort badge ≡ opened Send list (same predicate + scope) | **PASS** unscoped; **FAIL** under hybrid/assigned_only by design |
| Cohort counts ≠ attempt status_counts (units separated in UI) | **FAIL** (In progress/Completed dual source; expired 3 vs resend 2) |
| Cancelled policy consistent across cohort / counts / presentation | **FAIL** (counts yes, cohorts no; presentation→attention vs SQL) |
| Needs review / Reports ≡ company-or-scoped totals | **FAIL** (page-local) |
| Client queue ≡ server cohort membership | **FAIL** (extra `cv?.received` re-filter) |
| Canonical attempt statuses documented | **PASS** |
| Automated contract locking badge≡list≡scope | **FAIL** (missing) |
| Implementation / deploy | **NOT STARTED** (audit only) |

---

## 11. Approval gate

Do **not** implement or deploy Assessments count fixes until this contract is approved. After approval, implementation should:

1. Split cohort metrics from attempt metrics (no cross-fallback).
2. Align badge and opened list on one visibility scope.
3. Fix Needs review / Reports to shared review/attempt predicates (not page-local).
4. Codify cancelled as Attempts-only terminal; stop attention mislabel.
5. Remove or harden client `assessmentQueue` so it cannot disagree with server.
6. Add regression tests for multi-attempt (superseded expired), cancelled, delivery_failed, and hybrid scope.
7. Re-run WATHEFNI live matrix (resend 2 vs expired 3; cohort≡list).

**Out of scope:** Ranking, visual redesign, Jobs/Candidates (already shipped).
