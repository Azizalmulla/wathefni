# Interviews End-to-End State Audit

**Date:** 2026-07-28 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Mode:** Read-only. No UI, lifecycle, status, action, data, or messaging changes were made.

---

## Final verdict

**FAIL — Interviews experience is not coherent yet.**

The model is layered correctly in theory (interview status ≠ type ≠ feedback ≠ invitation ≠ confirmation), but live production data shows multiple systemic contradictions. A scheduled async video can have no date/time, say “Conduct the interview”, show “Candidate answered the full question list” with **0 answers**, and allow **Mark reviewed / Save feedback** before any evidence exists. Completed and Needs feedback overlap on the same rows, and one record disagrees with itself on whether feedback is complete.

---

## Source-of-truth map

| Field | Source of truth |
|---|---|
| Interview status | `candidate_interviews.status` (`scheduled` / `rescheduled` / `completed` / `no_show` / `cancelled`) |
| Interview type | `candidate_interviews.interview_type` + `source` (`live` vs `async_video`) |
| Async progress | `candidate_interviews.async_status`, `consent_accepted_at`, `completed_at`, `candidate_video_interview_responses` |
| Feedback authority | `human_feedback_status` first, then legacy `feedback_status`, then `interview_feedback_submissions` |
| Notes (not scorecard) | `candidate_interviews.notes` / `notes_status` (derived) |
| Invitation | `channel_send_status`, `candidate_notified`, `calendar_invite_sent`, `provider_sync_status` |
| Candidate confirmation | `rsvp_status`, `consent_accepted_at` |
| Schedule | `candidate_interviews.scheduled_start` / `scheduled_end` |
| Interviewer | `candidate_interview_assignments` |
| Next human action | `interview_lifecycle.next_human_action(row, truth)` |
| Allowed actions | Backend-computed in `dashboard_interviews_payload` from `interview.manage` permission + status |

---

## Contradictions found (live data)

### 1. `Scheduled` while date/time is not set — **Systemic**

| Layer | Finding |
|---|---|
| DB | 2 async video rows have `status='scheduled'` and `scheduled_start IS NULL` |
| API | Same rows returned with `status: scheduled`, `scheduled_start: null` |
| Table | Shows **Scheduled** badge + “Date and time not set” |
| Drawer | Status “Scheduled”, Next human action **Conduct the interview** |
| Layer responsible | Backend state model + frontend wording |
| Isolated or systemic | **Systemic** — async video reuses `scheduled` as a container state even though nothing is scheduled |

Root cause: async video lifecycle treats `scheduled` as “link created / flow active”, while HR reads `scheduled` as a live interview with a time. There is no required schedule guard.

**Best long-term correction:** separate async-video state from live schedule state; do not label async link flow as `Scheduled` for HR, and do not allow live `scheduled` without `scheduled_start`.

---

### 2. Invitation `Pending` while candidate confirmation is `Confirmed` — **Partially present**

| Layer | Finding |
|---|---|
| DB/API | For row `06e4a65d`: `channel_send_status='send_accepted'`, `consent_accepted_at` set → `invitation_status='send_accepted'`, `candidate_confirmation='confirmed'` |
| Current production rows | No live `pending + confirmed` pair in the 4 current rows |
| Code path | `communication_truth` can still produce `candidate_confirmation='confirmed'` while `invitation_status='pending'` if consent exists but channel stays `pending` |
| Layer responsible | Backend mapping |
| Isolated or systemic | **Systemic risk** — independent channels can drift |

Root cause: invitation is channel-send truth; confirmation is RSVP/consent truth. They are allowed to disagree because they are derived from different columns without a combined state rule.

**Best long-term correction:** derive one invitation/confirmation matrix with explicit combined states (e.g. `sent_pending_response`, `delivered_confirmed`), not two loosely coupled labels.

---

### 3. Candidate opened/started video flow but no answers — **Confirmed live**

| Layer | Finding |
|---|---|
| DB | `06e4a65d`: `async_status='consented'`, consent set, **0 rows** in `candidate_video_interview_responses` |
| API | `video_review_state='started'`, `video_answers: 0` |
| Table | Video interviews tab shows it; status **Scheduled** |
| Drawer | Badge **Opened**, but next action still **Conduct the interview** |
| Layer responsible | Backend next-action + frontend wording |
| Isolated or systemic | **Systemic** for async video |

Root cause: `next_human_action` only looks at `status`/`truth`, not `async_status`/response presence. It returns `conduct_interview` for a candidate-controlled recorded flow.

**Best long-term correction:** async next action should be evidence-based (`wait_for_video_response`, `review_video`, `retry_summary`), not `conduct_interview`.

---

### 4. “Candidate answered the full question list” while no answers exist — **Confirmed live**

| Layer | Finding |
|---|---|
| DB | `06e4a65d`: 4 questions, **0 answers** |
| API | `video_questions: 4`, `video_answers: 0` |
| UI code | `singleVideo = response_mode === 'single_video' || answers.some(...)`; when questions exist and `singleVideo` true, UI renders “Candidate answered the full question list in one video.” |
| Actual UI | Can show that copy even when `answers.length === 0` |
| Layer responsible | **Frontend presentation** |
| Isolated or systemic | **Isolated UI bug** |

Root cause: “answered the full question list” is derived from `singleVideo && questions.length`, not from `answers.length > 0`.

**Best long-term correction:** only claim completion when at least one answer exists; otherwise show “No video answers have been submitted yet.”

---

### 5. “Conduct the interview” for an asynchronous recorded video interview — **Confirmed live**

| Layer | Finding |
|---|---|
| API | `06e4a65d`, `8552e251`: `next_human_action='conduct_interview'` |
| UI | Next human action renders **Conduct the interview** |
| Reality | Candidate records asynchronously; HR cannot “conduct” it |
| Layer responsible | Backend mapping (`next_human_action`) + wording |
| Isolated or systemic | **Systemic** for async video |

**Best long-term correction:** use async-specific next actions (`Review submitted video`, `Wait for candidate video`, `Resend video link`, `Retry summary`).

---

### 6. `Mark reviewed` and `Save feedback` available before answers exist — **Confirmed live**

| Layer | Finding |
|---|---|
| API | `06e4a65d` / `8552e251` allowed_actions: `mark_completed`, `write_notes`, `open_candidate`, etc. with **0 answers** |
| UI | Drawer shows **Mark reviewed** + **Save feedback** for video interviews even when no answers |
| Layer responsible | **Action eligibility (backend)** + drawer logic |
| Isolated or systemic | **Systemic** |

Root cause: allowed actions are driven by permission + coarse status (`scheduled` → `mark_completed`), not by async evidence readiness. `write_notes` is also allowed whenever notes are not “complete”.

**Best long-term correction:** gate video review actions on evidence state (`answers > 0` / ready_for_review), and separate “Save HR note” from “Mark reviewed”.

---

### 7. Completed and Needs feedback showing the same records — **Confirmed live**

| Layer | Finding |
|---|---|
| DB/API | `369997d8` and `669366ae` appear in both `completed` and `needs_feedback` tabs |
| Root row `369997d8` | `feedback_status='feedback_complete'` but `human_feedback_status='notes_pending'` |
| UI | Completed count 2, Needs feedback count 2, same rows |
| Layer responsible | Database state + backend feedback authority |
| Isolated or systemic | **Systemic** |

Root cause: legacy `feedback_status` says complete while authoritative `human_feedback_status` says pending. Backend correctly prefers `human_feedback_status`, so the row is still “needs feedback”; but the table also surfaces the legacy complete state in the same row. Two feedback columns disagree.

**Best long-term correction:** one feedback authority column, with legacy `feedback_status` migrated/derived only; never show two different feedback truths for the same interview.

---

### 8. Video interviews mixing type and status without clear wording — **Confirmed live**

| Layer | Finding |
|---|---|
| DB/API | `interview_type='async_video'` with `status='scheduled'` or `completed`; `async_status` separately tracks link/open/consent/submit |
| UI | Badge uses main `status` (“Scheduled”) while video panel uses `asyncVideoDisplayStatus` (“Opened”, “Submitted”, “Ready for review”) |
| Result | Same row can read **Scheduled** and **Opened** / **Ready for review** at once |
| Layer responsible | Frontend presentation + state model |
| Isolated or systemic | **Systemic** |

**Best long-term correction:** one interview type label (“Recorded video interview”) plus one progress state (“Opened”, “Submitted”, “Ready for review”, “Reviewed”), instead of live-schedule wording on async rows.

---

## Scenario audit results

| Scenario | DB says | API returns | Table shows | Drawer shows | Actions enabled | Next human action correct? |
|---|---|---|---|---|---|---|
| Scheduled, no date/time | `scheduled`, `scheduled_start=null` | same | Scheduled + “Date and time not set” | Scheduled + Conduct interview | mark_completed, mark_no_show, cancel, write_notes, open_candidate | **No** |
| Opened video, not submitted | `async_status='consented'`, 0 answers | `video_review_state='started'` | Scheduled | Opened + Conduct interview | mark_completed, write_notes | **No** |
| Completed, needs feedback | `completed`, human feedback pending | `notes_pending` | Completed | Feedback pending + record_feedback | write_notes, open_candidate | Yes |
| Completed, feedback complete | none currently (only legacy complete) | `feedback_complete` count 0 | — | — | — | — |
| No-show | none currently | — | — | — | — | — |
| Cancelled | none currently | — | — | — | — | — |
| Invitation pending / sent / failed | `send_accepted` present; no pending/failed rows | invitation_status mirrors channel | Pending/Sent wording via `communicationLabel` | same | — | mostly, but can contradict confirmation |
| Confirmed / not confirmed | consent drives confirmed | candidate_confirmation correct per row | not shown | Confirmed / Not confirmed | — | partially (independent of invitation) |
| Interviewer assigned / unassigned | 2 scheduled rows have **0 assignees** | no assignee surfaced in list | not shown | not shown | — | not modeled as a next action |

---

## System answers

- **Interview type vs status separate authorities?** Yes in DB (`interview_type` + `status` + `async_status`), but UI mixes them.
- **One coherent model for async video / live / phone / in-person?** No. Async video is bolted onto live scheduling states.
- **Feedback separate from completion?** Yes, but two feedback columns can disagree (`feedback_status` vs `human_feedback_status`).
- **Invitation vs confirmation derived correctly?** Separately, not jointly; they can drift.
- **Date/time required before `scheduled`?** No.
- **Allowed actions backend-authoritative?** Mostly backend-computed, but too coarse (permission + status only), letting review actions appear before evidence exists.
- **Counts/tabs/table match?** Status counts and totals match rows, but Completed and Needs feedback overlap by design on the same records.
- **Repeated rows valid?** Yes — Hamad has separate interviews for separate applications/jobs; not duplicates.
- **EN/AR, RTL, direct links, refresh, Back?** Locale/RTL and tab filters are wired (`status`/`tab` in URL); not re-proven in this audit.

---

## Layer responsibility summary

| Issue | DB state | Backend mapping | Frontend presentation | Stale/legacy data | Action eligibility |
|---|---|---|---|---|---|
| Scheduled with no time | X | X | X |  |  |
| Conduct interview for async video |  | X | X |  |  |
| Opened video, no answers |  | X | X |  | X |
| “Answered full question list” with 0 answers |  |  | X |  |  |
| Mark reviewed / Save feedback before answers |  | X | X |  | X |
| Completed + Needs feedback same rows | X | X | X | X |  |
| Feedback complete vs pending same row | X | X |  | X |  |
| Invitation pending + confirmed |  | X |  |  |  |
| Interviewer unassigned not surfaced |  |  | X |  | X |

**Most issues are systemic**, not isolated to one row.

---

## Best long-term correction (not implemented)

1. Split **interview type** from **interview progress** explicitly in UI and next-action logic.
2. Make async video use its own progress states (`link_sent` → `opened` → `submitted` → `ready_for_review` → `reviewed`), not live `Scheduled`.
3. Require `scheduled_start` for live `scheduled`.
4. Collapse feedback to one authority (`human_feedback_status` + submissions); treat legacy `feedback_status` as read-only legacy.
5. Gate review actions on evidence existence.
6. Derive invitation + confirmation as one matrix.
7. Add interviewer assignment to drawer/next action when required.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| One coherent interview model | **FAIL** |
| No schedule/status contradiction | **FAIL** |
| No invitation/confirmation drift | **FAIL (risk)** |
| Video evidence required before review actions | **FAIL** |
| Feedback authority unambiguous | **FAIL** |
| Completed ≠ Needs feedback semantics clear | **FAIL** |
| Counts/tabs/table internally consistent | **PASS (numeric)** |
| Repeated rows valid | **PASS** |
| Backend-authoritative actions | **PASS (but too coarse)** |
| EN/AR/RTL/navigation wiring present | **PASS (not contradicted)** |

**Stop after the audit. No changes were made.**
