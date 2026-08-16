# Interviews Wave 4 — HR Table & Drawer UX Cleanup

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T015419Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Preserved:** Wave 1 canonical state authority, Wave 2 allowed-actions contract, Wave 3 canonical feedback authority, backend contracts, lifecycle rules, system colors, unrelated pages

---

## Final verdict

**PASS — Wave 4**

The Interviews table and drawer now present one calm, coherent HR surface driven entirely by backend `presentation` and canonical feedback. Async video is never shown as Scheduled; live scheduled requires a real date/time; completed-with-feedback-pending reads as two separate truths; feedback-complete exposes view feedback only; operational dialogs are wired to `allowed_actions` with validation, confirmation, and refresh.

---

## Before / after

| Area | Before | After |
|---|---|---|
| Row status | Raw `status` (async showed “Scheduled”) | Interview type + canonical progress (Link sent / Opened / Submitted / Ready for review / Reviewed) |
| Schedule column | Raw date or “not set” | Date/time only when applicable; async shows type instead |
| Interviewer | Not shown | Unassigned / assignee label |
| Feedback | Legacy mixed labels | Canonical feedback badge |
| Drawer | One long crowded drawer | Tabs: Overview / Interview evidence / Feedback / Communication / Activity |
| Actions | Coarse buttons + More menu | Primary next action + dialogs (Set date/time, Assign interviewer, Resend/retry, Cancel, No-show, Mark completed/reviewed) |
| Async wording | “Conduct the interview” | Wait for candidate / Resend video link / Review submitted video |

---

## Table structure (per row)

- Candidate (+ contact)
- Job
- Interview type / canonical progress
- Date/time (only when applicable)
- Interviewer assignment
- Canonical feedback state
- Next human action
- Open

Video interviews tab is labeled as a **type filter**, not a status. Counts come from backend canonical authorities.

---

## Drawer / workspace structure

- **Overview** — type, progress, schedule (when applicable), interviewer, candidate confirmation, invitation state, next human action, application stage, canonical feedback state.
- **Interview evidence** — AI summary + video questions/answers/review state; no false completion copy when 0 answers exist.
- **Feedback** — canonical feedback state, notes kept separate from structured feedback, write/continue/view per allowed actions; reviewed vs feedback-complete kept separate.
- **Communication** — invite delivery, invitation state, candidate confirmation, channel, sent message.
- **Activity** — chronological timestamps only.

Empty/irrelevant sections are hidden by default.

---

## Operational dialogs

| Action | Validation / safety |
|---|---|
| Set / reschedule date and time | Requires date/time; uses `reschedule_interview`; refreshes presentation |
| Assign interviewer | Requires assignee; uses canonical panel/assignment authority |
| Send / retry / resend invitation | Idempotent video create/resume or live invite path; no duplicate interviews |
| Cancel / no-show / mark completed/reviewed | Confirmation copy; audited PATCH; only when allowed |

All dialogs render only when the action exists in `presentation.allowed_actions`.

---

## Live scenario proof (`20260728T015419Z`)

| Scenario | Result |
|---|---|
| Opened async video, 0 answers (`06e4a65d`) | Progress `consented`, next `wait_for_video_response`, no review UI/actions |
| Link sent, 0 answers (`8552e251`) | Progress `link_sent`, resend/cancel/open only |
| Ready-for-review, feedback complete (`669366ae`) | Progress `reviewed`, feedback `complete`, allowed `view_feedback` + `open_candidate` only |
| Live completed, feedback pending (`369997d8`) | Progress `completed`, feedback `not_started`, `write_notes` only |
| Set date/time dialog for missing-date live | Present via `set_interview_datetime` (no live missing-date row in current data; validated by model + dialog) |
| Assign interviewer dialog for unassigned | Present via `assign_interviewer` |
| Async never “Scheduled” / never “Conduct interview” | PASS |
| Counts numeric | PASS |
| Health 200 | PASS |
| Rollback / restore | PASS |

Backend canonical proof: `backend-canonical-proof.json` in the stamp directory. Dashboard asset: `dashboard-BpZgUFnx.js`.

---

## Navigation & accessibility

- Direct links / refresh / Back / URL tabs (`status`/`tab` filters) preserved (no navigation changes).
- Dialogs are modal (`role="dialog"`, `aria-modal`) with backdrop close, labeled buttons, and required-field validation.
- Drawer uses tab buttons with `aria-current`.
- EN/AR copy for primary actions; `dir` follows locale (RTL preserved).
- Layout uses responsive grid (desktop/tablet/mobile).

---

## Rollback / restore

| Step | Result |
|---|---|
| Dashboard rollback → previous asset | `dashboard-BtxR3V_8.js`; health **200** |
| Dashboard restore → Wave 4 asset | `dashboard-BpZgUFnx.js`; health **200** |

Artifacts: `wathefni-dashboard.before|after`, `asset.*.txt`, `health.*`, `bundle-markers.txt`, `backend-canonical-proof.json`.

---

## Remaining limitations

- Set date/time / assign interviewer dialogs use simple inputs (no rich calendar/person picker yet).
- Resend/retry dialogs rely on backend idempotency; no custom message editing in this wave.
- Activity tab shows timestamps only (not a full event stream) because the drawer does not fetch the interview events feed yet.
- No-show / cancelled / expired / live-assigned rows are still not present in current production data; they are supported by the contract and dialogs.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Table shows type + canonical progress, not raw status | **PASS** |
| Async never shown as Scheduled / Conduct interview | **PASS** |
| Live scheduled only with real date/time | **PASS** |
| Completed + feedback pending reads as two truths | **PASS** |
| Feedback-complete exposes view feedback only | **PASS** |
| Drawer tab sections with hidden empties | **PASS** |
| Dialogs wired to presentation.allowed_actions + refresh | **PASS** |
| No false/contradictory labels | **PASS** |
| Counts from canonical authorities | **PASS** |
| Navigation/refresh/Back/URL stability | **PASS** |
| EN/AR + RTL + responsive | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations / no system color change | **PASS** |

**Stop after Wave 4.**
