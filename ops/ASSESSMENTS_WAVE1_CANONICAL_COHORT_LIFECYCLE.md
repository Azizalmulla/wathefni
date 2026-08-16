# Assessments Wave 1 — Canonical Cohort & Lifecycle Authority

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T022920Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Scope:** Canonical cohort unit + lifecycle presentation contract + error envelope  
**Not in this wave:** UI redesign, report presentation, page/role separation

---

## Final verdict

**PASS — Wave 1**

Operational assessment queues now count actionable **application/attempt** records, so counts match rows. Resend shows **3** (3 resendable rows) while people count remains secondary metadata (**2**). A backend presentation contract separates person / application / invitation / attempt / delivery / attempt state / review / report / next action / allowed actions. Completed, report-ready, and reviewed stay separate. Raw error keys are wrapped in a canonical human error envelope.

---

## Canonical cohort unit

| Cohort | Unit | Display count | People (metadata) |
|---|---|---:|---:|
| Ready to send | applications | 2 | 2 |
| Resend needed | applications | 3 | 2 |
| Delivery failed | applications | 0 | 0 |
| In progress | applications | 0 | 0 |
| Sent / pending | applications | 0 | 0 |
| Completed | people (display) | 1 | 1 |

Operational queues use `unit="applications"` with `display_count = application_count`; people count remains available as secondary metadata only.

---

## Presentation contract

`assessment_presentation_v1` (per application/attempt):

- `person { name, email, phone }`
- `application { app_key, status, position_code, position_title }`
- `invitation { attempt_id, has_active, delivery_state, expires_at, cancelled_at }`
- `attempt { state, delivery_state, review_state, report_state, percent, band, job_match_percent, completed_at }`
- `report { state, ready, immutable }`
- `cohort_key`, `display_status`, `needs_review`
- `next_human_action`, `allowed_actions`

Completed / report-ready / reviewed are separate truths.

---

## Error envelope

`assessment_error_envelope(code)` returns `{ error, message, next_step, safe_user_message }`.

| Raw key | HR message |
|---|---|
| `attempt_expired` | “This assessment link has expired. Send a new invitation to let the candidate continue.” |
| `assessment_resend_failed` | “The assessment could not be resent. Review the candidate contact details and try again.” |
| `already_sent` | “An assessment invitation is already active. Resend only if the candidate needs a new link.” |
| `delivery_failed` | “The invitation could not be delivered. Check the candidate email/WhatsApp and retry.” |
| `report_not_ready` | “The report is not ready yet. Wait for scoring to finish before opening the report.” |
| `permission_denied` | “You do not have permission to do this action. Ask an admin for assessment access.” |

Frontend `friendlyDashboardError` maps these codes and matching messages to human copy; raw keys are not shown directly.

---

## Live proof (`20260728T022920Z`)

| Assertion | Result |
|---|---|
| Resend count matches rows | **3 = 3** (people metadata 2) |
| Ready to send count matches rows | **2 = 2** |
| Completed deterministic | **1** |
| Needs review deterministic | **1** |
| Report ready deterministic | **1** |
| Presentation attached to attempts | **PASS** |
| No duplicate active attempts | **PASS** |
| Replacement/expired history preserved | **3 expired attempts with `expired_at`** |
| Raw error keys not exposed | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |

Evidence: `/opt/wathefni/production-evidence/assessments-wave1-canonical-cohort-lifecycle/20260728T022920Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`, `assessment_cohorts.py`) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore (+ `assessment_presentation.py`) | Health **200** |
| Dashboard restore | Health **200**; Resend `display=3`, people `2` |

---

## Remaining limitations

- UI has not been redesigned; counts now match rows but the page structure is unchanged.
- Report presentation contract (HR executive summary) is a later wave.
- Page/role separation (authoring/admin vs HR) is a later wave.
- Error envelope covers known assessment codes; new backend codes should be added to the same map rather than shown raw.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Operational queues count application/attempt records | **PASS** |
| Resend 3 rows / people 2 labeled | **PASS** |
| Ready to send parity | **PASS** |
| Completed + needs review deterministic | **PASS** |
| No duplicate active attempts | **PASS** |
| Replacement history preserved | **PASS** |
| Canonical presentation contract | **PASS** |
| Completed/report-ready/reviewed separate | **PASS** |
| Error envelope (no raw keys) | **PASS** |
| Permissions/tenant/EN/AR/RTL/links preserved | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 1.**
