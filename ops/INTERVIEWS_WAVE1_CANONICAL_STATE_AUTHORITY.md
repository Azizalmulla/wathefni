# Interviews Wave 1 — Canonical State Authority

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T010943Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Scope:** Backend-authoritative canonical interview state + minimal presentation consumption  
**Not in this wave:** UI redesign, feedback behavior changes, colors, unrelated pages

---

## Final verdict

**PASS — Wave 1**

One backend presentation object now owns interview type, progress, schedule state, invitation state, candidate confirmation, evidence readiness, interviewer assignment, next human action, and allowed actions. Async recorded video no longer appears to HR as **Scheduled** when there is no date/time. Live interviews cannot be patched to `scheduled` without `scheduled_start`. Review actions are gated on video evidence. Raw legacy fields are preserved; no interview history was destroyed or merged.

---

## Before / after state model

| Concern | Before | After (Wave 1) |
|---|---|---|
| Interview type | `interview_type` + `source` only | Canonical type: `async_video` / `live_video` / `phone` / `in_person` |
| Async progress | Reused live `scheduled` wording | `created` / `link_sent` / `opened` / `consented` / `submitted` / `ready_for_review` / `reviewed` / `expired` / `cancelled` |
| Live progress | Loose `scheduled` | `draft` / `invitation_pending` / `scheduled` / `confirmed` / `completed` / `no_show` / `cancelled` / `rescheduled` |
| Schedule state | None | `not_applicable` / `date_missing` / `scheduled` |
| Invitation + confirmation | Two loosely coupled labels | Matrix: `not_sent` / `send_pending` / `sent_awaiting_response` / `delivered_confirmed` / `delivery_failed` / `candidate_declined` (+ explicit note for drift) |
| Evidence readiness | Inferred in UI | `none` / `waiting` / `partial` / `ready` / `reviewed` |
| Next human action | `conduct_interview` for async video | Type-aware (`wait_for_video_response`, `review_video_interview`, `schedule_interview`, `set_interview_datetime`, …) |
| Allowed actions | Permission + coarse status | Type/evidence-gated (no review before answers exist) |
| Interviewer assignment | Not surfaced | `interviewer_assignment` in presentation |

---

## Migration / reconciliation rules (no destructive migration)

- No rows were rewritten or deleted.
- Raw `status`, `async_status`, `feedback_status`, `human_feedback_status`, `scheduled_start`, and `consent_accepted_at` remain the database authority.
- Presentation is derived read-only in `interview_presentation.build_interview_presentation`.
- Async video with no `scheduled_start` → `schedule_state='not_applicable'`; never presented as “Scheduled”.
- Live/phone/in-person with no `scheduled_start` → `date_missing`, progress `draft`/`invitation_pending`.
- PATCH guard: live/phone/in-person cannot be set to `scheduled`/`rescheduled` without a date/time (`422 interview_datetime_required`).
- Separate applications/interviews stay separate.

---

## Presentation contract

`interview.presentation` (`interview_presentation_v1`):

- `interview_type`, `interview_type_label`
- `progress_state`, `progress_label`
- `schedule_state`, `date_time`
- `invitation_state`, `invitation_note`
- `candidate_confirmation`
- `evidence_readiness`, `feedback_complete`
- `interviewer_assignment { assigned, count, names, label }`
- `next_human_action`, `next_human_action_legacy`
- `allowed_actions`
- `display { status_label, type_label, show_datetime, is_async }`

Frontend consumes `presentation` for row status, schedule label, invitation, confirmation, interviewer, next action, and allowed actions. It no longer infers these independently.

---

## Live record proofs (`20260728T010943Z`)

| Interview | Type | Progress | Schedule state | Invitation | Next human action | Evidence-gated actions |
|---|---|---|---|---|---|---|
| `06e4a65d` (Accounting Excel) | Recorded video | `consented` | `not_applicable` | `delivered_confirmed` | `wait_for_video_response` | `mark_completed` removed (0 answers) |
| `8552e251` (HR) | Recorded video | `link_sent` | `not_applicable` | `sent_awaiting_response` | `wait_for_video_response` | `mark_completed` removed (0 answers) |
| `369997d8` (Accounting Excel) | Live video | `completed` | `scheduled` | `not_sent` | `record_feedback` | feedback only |
| `669366ae` (HR) | Recorded video | `ready_for_review` | `not_applicable` | `delivered_confirmed` | `review_video_interview` | `mark_completed` allowed (1 answer) |

Gates proven live:

- Async video with no date/time is never labeled **Scheduled** → **PASS**
- Live `scheduled` without date/time returns **422** → **PASS**
- Opened-but-not-submitted shows `consented`/`opened` + `wait_for_video_response` → **PASS**
- Ready-for-review shows `review_video_interview` → **PASS**
- No `mark_completed` before answers exist → **PASS**
- Interviewer assignment surfaced (unassigned shown) → **PASS**
- Counts/total numerically correct → **PASS**
- No unrelated mutations → **PASS**
- Health 200 → **PASS**
- Rollback/restore → **PASS**

Evidence: `/opt/wathefni/production-evidence/interviews-wave1-canonical-state/20260728T010943Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`, remove presentation authority use) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore (`app.py` + `interview_presentation.py`) | Health **200** |
| Dashboard restore | Health **200**; asset `dashboard-BFlC9AGM.js` |

Artifacts in the stamp directory: `app.py.before|after`, `interview_presentation.py.after`, `wathefni-dashboard.before|after`, `asset.after.txt`, `health.*`, `live-proof.json`.

---

## Remaining limitations

- No-show / cancelled / live scheduled-with-date / live interviewer-assigned scenarios do not exist in current production data; they are covered by the model and local proofs, not live rows.
- Feedback behavior itself was not redesigned in this wave (only evidence gating of review actions).
- UI wording for every progress state is functional, not a full visual redesign.
- Interviewer assignment is surfaced, but there is still no dedicated “assign interviewer” action.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Canonical type separation | **PASS** |
| Async never shown as Scheduled without date/time | **PASS** |
| Live scheduled requires date/time | **PASS** |
| Opened-not-submitted progress correct | **PASS** |
| Invitation/confirmation matrix with explicit drift note | **PASS** |
| Type-aware next human action | **PASS** |
| Interviewer assignment surfaced | **PASS** |
| Counts numerically correct | **PASS** |
| EN/AR/RTL/direct-link/refresh/Back preserved | **PASS** (no navigation changes) |
| No unrelated mutations | **PASS** |
| Health 200 + rollback/restore | **PASS** |

**Stop after Wave 1.**
