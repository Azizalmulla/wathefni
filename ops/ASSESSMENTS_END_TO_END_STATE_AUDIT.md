# Assessments End-to-End State Audit

**Date:** 2026-07-28 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Mode:** Read-only. No status, count, action, scoring, report, data, permission, lifecycle, routing, or messaging changes were made.

---

## Final verdict

**FAIL — Assessments experience is not fully coherent yet.**

The shared cohort authority (Wave 3) is solid for **who needs action**, but the page mixes **people counts** with **attempt/application rows**, shows raw technical error keys, mixes operational queues with admin/authoring surfaces, routes “Open” to the wrong context, and renders a raw-JSON-style report. Most issues are **systemic**, not one-off data bugs.

---

## 1. Canonical cohort unit

### Live contradiction: Resend shows 2 vs 3 rows

| Surface | Unit | Value |
|---|---|---|
| Cohort count (`assessment_cohorts`) | **people** | **2** |
| Resend queue rows | **applications/expired attempts** | **3** |

Live resend rows:

| app_key | person | attempt status |
|---|---|---|
| `96597485758-WATHEFNI-ACCOUNTING_EXCEL` | Hamad Almulla | expired |
| `96597485758-WATHEFNI-HR` | Hamad Almulla | expired |
| `96598900677-WATHEFNI-HR` | AZIZ ALMULLA | expired |

**Root cause:** `assessment_cohorts` intentionally counts distinct confirmed **people** (`people_count`) and publishes `application_count` beside it. The Assessments page renders one row per **application/attempt**, so Resend shows **3 actionable records** while the card/tab uses the **2 people** number.

**Canonical unit recommendation:**

| Queue | Canonical unit |
|---|---|
| Send / Resend / Delivery failed / In progress / Sent pending | **actionable application/attempt** (matches rows) |
| Completed / Reports | **attempt** |
| Overview attention signals | may stay **people**, but must be labeled as such |
| Candidate profile | application-specific attempt |

The current mixed unit is **systemic** across summary cards, tabs, queue headings, Overview signals, and pagination.

---

## 2. Source-of-truth map

| Concern | Source of truth |
|---|---|
| Cohort membership | `assessment_cohorts.py` predicates on latest attempt per application |
| Attempt state | `assessment_attempts.status` + `delivery_status` + `expires_at` |
| Delivery truth | `delivery_status` / communication events |
| Score | `assessment_scores` + `assessment_reports.report_json` |
| Review | `assessment_attempts.review_status` / `reviewed_at` / `reviewed_by_user_id` |
| Report | `assessment_reports` (immutable) + `fetch_dashboard_assessment_report_payload` |
| Cohort counts | `assessment_cohorts.compute_assessment_cohorts` (people) + `application_count` |
| Actions | `assessment_allowed_actions` (cohort-derived) + dedicated endpoints |
| Notifications/errors | backend error `code`/`message` → `friendlyDashboardError` |

Invitation state, attempt state, review state, and report state are **separate columns**, but the UI and counts often flatten them into one “Assessment” badge or one cohort.

---

## 3. Lifecycle / state authority

| State | DB fields | Backend derivation | Current handling |
|---|---|---|---|
| ready to send | no latest attempt + eligible app | `cohort_predicate(ready_to_send)` | Send queue |
| sent/pending | latest attempt `pending` | cohort `sent_pending` | Sent/pending tab |
| delivery failed | `delivery_status IN failed/send_failed/invitation_failed` | cohort `delivery_failed` | Delivery failed tab |
| in progress | latest attempt `in_progress` | cohort `in_progress` | In progress tab |
| expired | latest attempt `expired` | cohort `resend_needed` | Resend tab |
| completed | latest attempt `completed` | cohort `completed` | Completed tab / reports |
| cancelled | `cancelled` attempts exist in schema | not exposed as a primary cohort here | limited |
| needs review | completed + `review_status<>'reviewed'` | `needsReview` count on page | separate metric |
| reviewed / report complete | `review_status='reviewed'` + immutable report | report payload | View report |

`attempt_expired` rows in production: **3 expired attempts**, all `delivery_status='pending'`, `review_status='unreviewed'`.

---

## 4. Raw `attempt_expired` error exposure

### What happens

A top-right alert/toast shows the raw technical key **`attempt_expired`**.

### Root cause

Backend raises structured errors with `error: "attempt_expired"` in multiple paths (start/resume/submit/resend on an expired attempt). Example paths:

- `app.py` `attempt_expired` `HTTPException(status_code=409, detail={"error": "attempt_expired"})`
- `resend_assessment` returning `{"ok": False, "error": "attempt_expired"}`

Frontend `friendlyDashboardError` only humanizes a small set of codes (`stale_state`, `permission_denied`, `module_disabled`, etc.). For other errors it falls through to `error.message` if it doesn’t match a technical regex, or to the generic fallback. `attempt_expired` is **not mapped**, so HR sees the raw key.

### Scope

- **Systemic**: many backend error keys are not mapped to human copy (`attempt_expired`, `delivery_failed`, `already_sent`, `invalid_transition`, `report_not_ready`, `stale_attempt`, `duplicate_request`, etc.).
- EN/AR mappings for these keys are missing.
- Alerts can remain stale after the underlying action succeeds because the toast is just the last notice text.

**Best correction:** one backend→frontend error contract with canonical codes and localized human messages + next action; never render raw keys.

---

## 5. Action eligibility matrix (current)

| Action | Current authority | Finding |
|---|---|---|
| Send assessment | cohort `ready_to_send` + `assessment.manage` | mostly backend; frontend also infers from cohort |
| Resend assessment | `/assessments/{attempt_id}/resend` + `resend_assessment` | revokes/replaces prior attempt; idempotent by design |
| Cancel | `/assessments/{attempt_id}/cancel` | audited |
| Open | routes to general candidate profile | **wrong context** (see navigation) |
| View attempt | not a dedicated attempt workspace | missing |
| View report | `/assessments/{attempt_id}/report` (HTML) | detached blob page |
| Mark reviewed | `/assessments/{attempt_id}/review` | requires completed |
| Reopen/reissue expired | resend path | uses replacement invitation |

**Findings:**

- Duplicate open attempts: none in current data (`duplicate_open = []`).
- Completed attempts cannot be resent through the same resend path without hitting completion/expiry rules.
- Mark reviewed appears only for completed attempts in the Recent attempts table.
- View report appears for completed attempts.
- **Open routing defect:** assessment row “Open” goes to the candidate profile, not a dedicated assessment attempt/workspace. This is a **UX/navigation defect**, not intended long-term behavior.

---

## 6. Report and scoring authority

| Field | Source |
|---|---|
| Overall score | `assessment_scores.percent` / `report_json.percent` |
| Job match | `report_json.job_match.job_match_percent` |
| Ability fit | `report_json.job_match.ability_fit_percent` |
| Competency fit | `report_json.job_match.competency_fit_percent` |
| Section scores | `report_json.report_sections.verify_ability.sections` |
| Percentiles / T-scores / STEN | inside section score objects |
| Bands | `report_json.band` + `job_match.fit_band` |
| Strengths / development | `job_match.strengths` / `development_areas` |
| Interview probes | `report_sections.interview_probes` |
| Review status | `assessment_attempts.review_status` |
| Norm version | `report_json.norm_version` (`wathefni_ability_v1_local` live) |

Scores are deterministic and backend-owned; reports are immutable.

### Current report experience (systemic UX failure)

- Opens as a detached **`blob:` page** (not inside Wathefni).
- Header literally says **“Official deterministic score JSON”**.
- Exposes raw labels like **`low`**, **`needs_review`**, **`development`**, **`mixed`**.
- Long technical tables for ability/competency.
- No executive HR summary, interpretation, or next step.
- Feels disconnected from the application.

There is **no dedicated report presentation contract** — `assessment_report_html` renders raw report JSON sections into HTML.

---

## 7. Page structure and audience separation

The Assessments page currently mixes:

- summary metrics
- Send/Resend operational queues
- Recent attempts
- Reports
- Assessment setup / details
- **Product2 authoring workbench**
- production/non-production warnings
- backend kill-switch status
- AI governance notices
- publishing controls

The authoring workbench (`Product2AuthoringPanel`) is gated by `assessment.manage` + backend authoring kill-switch, but it still renders on the primary HR page and can show technical operational details (non-production badge, kill-switch messaging).

**Recommended separation (long-term):**

- **HR operational page:** Send, Attempts, Reports.
- **Assessment administration/setup:** separate admin-only area.
- **Authoring workbench:** hidden from normal HR, admin-only, and completely absent in production when authoring is disabled.

### Permissions snapshot

| Role | Expected exposure |
|---|---|
| Recruiter | operational queues, attempts, reports |
| Hiring manager | same, limited setup |
| HR admin | setup + norms |
| Company admin | authoring/admin |
| Super admin | all |

Normal HR should not see backend kill-switch text, governance internals, or authoring controls they cannot act on.

---

## 8. Count and parity audit (live)

| Cohort | People | Applications | Tab/queue rows | Parity |
|---|---:|---:|---:|---|
| Ready to send | 2 | 2 | Send rows = applications | card people vs rows applications |
| Resend needed | 2 | 3 | Resend rows = 3 | **2 vs 3** |
| Delivery failed | 0 | 0 | 0 | ok |
| In progress | 0 | 0 | 0 | ok |
| Sent / pending | 0 | 0 | 0 | ok |
| Completed | 1 | 1 | 1 attempt | ok |
| Needs review | — | — | 1 completed unreviewed | completed ∩ needs review (valid overlap) |

Valid overlap: a completed attempt can still need HR review. That must be labeled as **Completed — feedback/review pending**, not a contradictory status.

---

## 9. Navigation and URL behavior

- Cohort tabs preserve `assessment_cohort` / `tab` in URL (Wave 3 durability).
- “Open” from an assessment row routes to the **candidate profile**, not an assessment attempt workspace — **defect**.
- View report opens a detached blob page; Back returns to the dashboard, but the report is not a first-class route.
- A replaced/expired attempt can leave stale context that surfaces `attempt_expired` when a user retries an old link.

---

## 10. UX findings (audit only)

- Mixed operational + administrative workflows on one page.
- Raw technical copy (`attempt_expired`, report labels) exposed to HR.
- Duplicated Send/Resend representation across cohort queue + Recent attempts.
- Columns like battery key are low-value for daily HR.
- “Open” lacks assessment context.
- No dedicated assessment attempt/report workspace.
- Page should eventually simplify into **Send / Attempts / Reports / Setup-Admin only**.

---

## 11. Security and safety

| Check | Status |
|---|---|
| Tenant boundaries | company-scoped queries |
| Permission boundaries | `assessment.manage` gating on mutations |
| Report access control | assessments dashboard context |
| Invitation revocation | resend revokes/replaces prior attempt |
| Duplicate sends/attempts | none live; create/resume + open-attempt rules |
| Score mutation from frontend/AI | reports immutable; AI may summarize, not score |
| Audit events | review/cancel/resend events recorded |

---

## 12. Isolated vs systemic classification

| Issue | Type |
|---|---|
| Resend 2 people vs 3 rows | **Systemic** unit/labeling |
| Raw `attempt_expired` | **Systemic** error contract |
| Open → candidate profile | **Systemic** navigation defect |
| Detached raw report page | **Systemic** presentation defect |
| Authoring/admin on primary page | **Systemic** page-structure/role issue |
| Duplicate attempts | Not reproduced live |
| Score mutation | No evidence |

---

## 13. Best long-term corrections

1. **Canonical cohort unit:** application/attempt for operational queues; clearly label any people-based number.
2. **Error contract:** canonical error codes → localized human messages + next action; never raw keys.
3. **Dedicated assessment workspace:** attempt/report context instead of generic candidate profile.
4. **Report presentation contract:** HR executive summary, strengths, gaps, next step; no raw JSON labels; keep deterministic scores immutable.
5. **Page/role separation:** HR operational page vs admin setup/authoring.
6. **Review vs completion:** keep completed vs needs-review clearly separate.

---

## 14. Recommended implementation waves

1. Canonical assessment cohort and lifecycle authority (unit + unified states).
2. Backend-authoritative actions and idempotency (send/resend/cancel/reopen).
3. Canonical report/review authority (presentation contract).
4. Page structure and role separation (HR vs admin/authoring).
5. HR report + table/workspace UX cleanup.

---

## 15. Remaining unknowns

- Whether `attempt_expired` originated from a stale resend, a direct old link, or a profile action in the exact user session (requires the triggering click/URL at that moment).
- Whether any historical duplicate sends exist outside current production rows.
- Exact intended owner/role for assessment authoring in production.
- Whether Overview should keep people-based assessment signals while Assessments uses attempt-based queues (needs a labeled cross-page contract).

**Stop after the audit. No changes were made.**
