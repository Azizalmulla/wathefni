# Reports End-to-End Truth Audit

**Date:** 2026-07-28 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Mode:** Read-only. No report, metric, export, breakdown, routing, permission, or data changes were made.

---

## Final verdict

**FAIL — Reports are not yet one coherent truth.**

Reports V1 summary numbers are mostly correct against canonical authorities, but the **export cards, breakdowns, and exports disagree** because they use different sources and units. Some fields are hardcoded/empty (role breakdown, stage breakdown), some exports count **history** while cards imply **current state**, and leadership exports leak **raw internal statuses**.

---

## Source-of-truth map

| Surface | Source | Unit | Current vs history |
|---|---|---|---|
| Reports V1 summary (`build_reports_v1_payload`) | `prehire_overview.compute_action_counts` + lifecycle funnel | applications (mostly) | current |
| Export cards (`exports.*_rows`) | mixed: CV count / **hardcoded 0** / event counts / assessment rows | mixed | mixed |
| Breakdowns (`breakdowns.*`) | funnel (stage), **empty arrays** for role/followups/interview, assessment status query | mixed | mixed |
| Exports (`iter_export_rows`) | dedicated queries per type (candidates, roles, assessments, interviews, followups) | per type | current for most, **history for followups** |
| Canonical authorities | `assessment_cohorts`, `prehire_overview`, `interview_presentation`, `assessment_presentation` | application/attempt | current |

---

## Unit map

| Metric | Canonical unit (should be) |
|---|---|
| Candidate report | application |
| Role report | role |
| Assessment report | attempt |
| Interview report | interview |
| Follow-up report | current follow-up **application**, not historical delivery events |
| Ready for review | application |
| Assessment status (pending/completed/expired) | attempt |
| Role breakdown | role |
| Stage breakdown | application (current stage) |

---

## Every mismatch found

### 1) Role report card = 0 records, but export contains many roles — **Systemic**

- Card: `exports.role_rows = 0` (**hardcoded** in `reports_v1.py`).
- Export (`roles`): **11 rows** live.
- Root cause: card uses a placeholder `0`; export uses a real role query. No shared role-count authority.

**Correction:** one role-count authority shared by card, breakdown, and export; `role_rows` should equal the roles export count (or a clearly labeled current-open-roles count).

### 2) Ready for review = 2 in analytics, but 0 in stage breakdown — **Systemic**

- Summary: `ready_for_review = 2` (canonical `compute_action_counts`).
- Breakdown `applications_by_stage`: funnel rows show **Ready for review = 0**, Shortlisted = 0, Interview = 0, Hired = 0, only “CV received = 10”.
- Root cause: breakdown uses a **lifecycle first-entry funnel** with a window that yields no later stages for this data, while the summary uses current application status. Two different sources.

**Correction:** stage breakdown must use current application stage (canonical stage authority), not a lifecycle-event funnel, or be clearly labeled as “entries over time”.

### 3) Assessment status 0/0 in analytics, but export shows pending/completed/expired — **Partially fixed / still inconsistent**

- Live export breakdown `assessment_status`: expired 3, completed 1, pending 1.
- Live assessment attempts: pending 1, expired 3, completed 1.
- Canonical cohorts (after our resend): `sent_pending=1`, `expired=2`, `resend_needed=2`, `completed=1`.
- Card/summary `assessment_pending` uses `compute_action_counts.assessment_pending` (people-oriented), while breakdown/export count **attempts**. Wave 1 made operational queues application-based; Reports still blends people vs attempts.

**Correction:** Reports assessment status should use **attempt** unit from the assessment authority (`assessment_presentation`/attempt status), and labels should match cohort wording.

### 4) Follow-up report = 21 records, but most are repeated historical events for a few candidates — **Systemic**

- Card/summary: `followup_rows = 21`, `followup_delivery_events = 21`.
- Export (`followups`): **21 rows**, many duplicates for Hamad (Accounting Excel).
- Distinct applications needing follow-up: **2** (`action_counts.follow_up_needed`), distinct failed-delivery apps: **5**.
- Root cause: follow-up report counts **historical failed `outbound_delivery_events`**, while the card/leadership expectation is **current follow-up applications**. History vs current state are mixed under one label.

**Correction:** separate **Current follow-ups (applications)** from **Delivery failure history (events)**; card and default export should be current applications, with an optional events export.

### 5) Raw legacy labels in exports — **Systemic**

- Candidate export shows `screening_complete`, `review_pending`.
- Assessment export shows `needs_review`.
- Interview export shows `feedback_complete`, `notes_pending`.
- Root cause: exports pass raw DB/status values straight to CSV.

**Correction:** one export label map to human/canonical labels (stage labels, report band labels, review labels); leadership exports should not expose raw internal codes.

---

## Isolated vs systemic

| Issue | Type |
|---|---|
| Role card hardcoded 0 | **Systemic** |
| Stage breakdown funnel vs current | **Systemic** |
| Assessment people vs attempt units | **Systemic** |
| Follow-up events vs current applications | **Systemic** |
| Raw labels in exports | **Systemic** |

---

## Does it use the canonical authorities?

- Candidates: partially (exports use latest attempt/interview, but raw statuses).
- Interviews: no (`interview_presentation_v1` not used for reports).
- Assessments: partially (cohorts exist, but Reports still mixes people/attempts and raw labels).

---

## Recommended implementation waves

1. **Canonical report metrics authority** — one backend contract for every card/breakdown/export with explicit unit + current/history flag.
2. **Role and stage breakdown truth** — role count from role authority; stage breakdown from current application stage.
3. **Follow-up separation** — current follow-up applications vs delivery failure history (two labeled surfaces).
4. **Export label presentation** — human/canonical labels for all exports; no raw internal statuses.
5. **Adopt fixed authorities** — use `interview_presentation`, `assessment_presentation`, and cohort units in Reports.

---

## Remaining unknowns

- Whether leadership expects the Role card to mean “all roles ever” vs “currently open roles”.
- Whether the follow-up export should keep a separate “delivery history” CSV for auditing.
- Exact stage taxonomy leadership wants (canonical 8-stage vs legacy statuses).

**Stop after the audit. No changes were made.**
