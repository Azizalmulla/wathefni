# Interviews Wave 2 — Action Eligibility & Operational Actions

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T012500Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Authority:** `interview_presentation_v1`  
**Not in this wave:** drawer redesign, feedback authority changes, colors, unrelated pages

---

## Final verdict

**PASS — Wave 2**

Every action HR sees is now derived from the backend presentation contract by type, progress, evidence, schedule, invitation, and permission. Opened async video with **0 answers** no longer exposes review/feedback-complete actions; ready-for-review video exposes review + feedback; live completed exposes feedback only; live without date exposes Set date/time + Assign interviewer, not Complete/No-show. Frontend renders only `presentation.allowed_actions`. Idempotent video create/resume and permission boundaries proven.

---

## Action matrix (backend-authoritative)

### Async recorded video

| State | Allowed actions |
|---|---|
| created / not sent | `send_video_invitation`, `cancel_interview` |
| send failed | `retry_video_invitation`, `cancel_interview` |
| link sent / awaiting response | `resend_video_link`, `cancel_interview`, `open_candidate` |
| opened / consented (0 answers) | `resend_video_link`, `cancel_interview`, `open_candidate` |
| submitted / ready for review (evidence) | `review_video`, `write_notes`, `mark_reviewed`, `cancel_interview`, `open_candidate` |
| submitted (summary pending) | `write_notes`, `cancel_interview`, `open_candidate` (no review completion) |
| reviewed | `open_candidate` |
| expired | `reopen_invitation`, `resend_video_link`, `cancel_interview` |

### Live video / phone / in-person

| State | Allowed actions |
|---|---|
| draft / missing date | `set_interview_datetime`, `assign_interviewer` (if unassigned), `cancel_interview` |
| invitation pending | `send_interview_invitation`, `set_interview_datetime`, `assign_interviewer`, `cancel_interview` |
| scheduled / confirmed / rescheduled | `reschedule_interview`, `send_interview_invitation`, `mark_completed`, `mark_no_show`, `cancel_interview`, `assign_interviewer` (if unassigned) |
| completed | `write_notes` (if feedback incomplete), `open_candidate` |
| no-show / cancelled | `reschedule_interview`, `open_candidate` |

Rules enforced:

- No review/feedback-complete/mark-reviewed before required evidence exists.
- No conduct/complete/no-show for live without a valid schedule.
- Async never uses live “Conduct interview”.
- `Save feedback` (`write_notes`) and `Mark reviewed` are separate actions.
- Notes do not count as completed feedback (unchanged authority).
- No permission → no actions.

---

## Mutation paths (existing canonical authorities only)

| Action | Path |
|---|---|
| send/resend/retry/reopen video invitation | `POST /dashboard/prehire/interviews/{id}/actions/send-video-invitation` → `create_or_resume_async_video_interview` + `send_async_video_interview_invite` |
| assign interviewer | `POST /dashboard/prehire/interviews/{id}/actions/assign-interviewer` → `interview_service.reschedule_interview` (panel/assignment authority) |
| set date/time, reschedule | `POST /dashboard/prehire/interviews/{id}/reschedule` → `interview_service.reschedule_interview` |
| send live invitation | `send_interview_invite` (existing) |
| mark completed / no-show / cancel | `PATCH /dashboard/prehire/interviews/{id}` (existing, audited) |
| write notes | `POST /dashboard/prehire/interviews/{id}/notes` (existing) |

Each new action path re-checks the presentation `allowed_actions` before mutating (409 when not allowed). No parallel lifecycle authority was created.

---

## Live record proofs (`20260728T012500Z`)

| Interview | Type | Progress | Evidence | Next action | Allowed actions |
|---|---|---|---|---|---|
| `06e4a65d` | async video | consented | waiting (0 answers) | `wait_for_video_response` | `resend_video_link`, `cancel_interview`, `open_candidate` |
| `8552e251` | async video | link_sent | waiting (0 answers) | `wait_for_video_response` | `resend_video_link`, `cancel_interview`, `open_candidate` |
| `369997d8` | live video | completed | ready | `record_feedback` | `write_notes`, `open_candidate` |
| `669366ae` | async video | ready_for_review | ready (1 answer) | `review_video_interview` | `review_video`, `write_notes`, `mark_reviewed`, `cancel_interview`, `open_candidate` |

Gates proven live:

- Opened async with 0 answers has **no** review/feedback-complete action → **PASS**
- Ready-for-review exposes review + feedback actions → **PASS**
- Async rows never show **Conduct interview** → **PASS**
- Live without date → Set date/time + Assign interviewer, not Complete/No-show → **PASS** (synthetic + model)
- Interviewer-unassigned surfaced → **PASS**
- Completed live → feedback action only, no scheduling actions → **PASS**
- Table/drawer actions match backend contract → **PASS**
- Counts numerically correct → **PASS**
- No permission → no actions → **PASS**
- EN/AR + RTL → **PASS** (locale/dir unchanged)
- Health 200 → **PASS**
- Rollback / restore → **PASS**
- No unrelated mutations → **PASS**

Evidence: `/opt/wathefni/production-evidence/interviews-wave2-action-eligibility/20260728T012500Z/live-proof.json`

---

## Idempotency & safety proof

| Concern | Result |
|---|---|
| Duplicate video sends prevented | `create_or_resume_async_video_interview` returns the same active interview for the same app; second call does not create a duplicate row → **PASS** |
| Retry/resend idempotent | Same resume path; send events recorded on the same interview → **PASS** |
| Schedule updates do not duplicate provider events | `interview_service.reschedule_interview` reuses the same record/provider sync authority → **PASS (path)** |
| mark completed/no-show/cancel valid + audited | Existing audited PATCH path unchanged → **PASS** |
| Tenant/permission boundaries | `require_interview_record`, module entitlement, and permission-gated actions preserved → **PASS** |

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`, presentation) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore | Health **200** |
| Dashboard restore | Health **200**; asset `dashboard-G2ATLaR3.js`; post-restore proofs PASS |

Artifacts in stamp directory: `app.py.before|after`, `interview_presentation.py.before|after`, `wathefni-dashboard.before|after`, `asset.after.txt`, `health.*`, `live-proof.json`.

---

## Remaining limitations

- Set date/time, assign interviewer, resend link, retry, and reschedule are exposed as valid backend actions; the drawer triggers them but does not yet open dedicated input dialogs (uses current values). A follow-up UX wave should add proper forms.
- No-show / cancelled / expired / live-assigned rows do not exist in current production data; those states are covered by the matrix and local proofs, not live rows.
- Feedback authority itself was not redesigned (only separated from review completion).
- A transient DB deadlock appeared during rapid restart+proof; re-run passed and final state is healthy.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Canonical allowed actions by type/state | **PASS** |
| Evidence-gated review/feedback-complete | **PASS** |
| Schedule-gated live conduct/complete/no-show | **PASS** |
| Async never uses Conduct interview | **PASS** |
| Save feedback ≠ Mark reviewed | **PASS** |
| Operational actions (assign, datetime, resend, retry, reschedule, cancel) | **PASS** |
| Frontend renders only presentation.allowed_actions | **PASS** |
| Idempotency (video create/resume) | **PASS** |
| Permission boundaries | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 2.**
