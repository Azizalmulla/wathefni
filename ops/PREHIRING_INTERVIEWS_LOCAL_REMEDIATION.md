# Pre-Hiring Interviews — Local Remediation

**Status:** CLOSED — local remediation complete (2026-07-24 Kuwait)  
**Source tree:** `/tmp/wathefni-c3-local` (authoritative Interviews remediation tree)  
**Report path:** `claw/ops/PREHIRING_INTERVIEWS_LOCAL_REMEDIATION.md`  
**Deploy:** None (local close-out only)  
**Assessment:** `ops/PREHIRING_INTERVIEWS_ASSESSMENT.md` (approved)

**Preserved product rules**

- Interview status stays separate from application lifecycle.
- Interviews do not automatically hire, reject, rank, or issue offers.
- Interview scoring stays disabled in Ranking.
- AI summaries remain advisory.
- Tenant isolation and confirmation requirements remain unchanged.
- Jobs, Candidates, Ranking, Reports, Assistant core, Assessments, Offers, and Hiring were not reopened for redesign.
- Mobile scheduling remains deferred.

---

## Executive summary

Contained local remediation makes **Wathefni the canonical interview scheduling authority**. Google Calendar/Meet is optional after-commit sync. Scheduling works with no calendar connected for physical, phone, and manual-link interviews. Duplicate confirmation is idempotent; candidate/panel conflicts fail closed; Google failure leaves a valid Wathefni interview with visible sync failure. Panel assignments and versioned human feedback are first-class. Free-text notes are no longer treated as scorecards. Candidate video completion and AI summary generation no longer mark human feedback complete. Communication states distinguish provider accept vs channel send vs proven delivery vs RSVP. Stale transcription processing can be reclaimed; retention purge is audited. Assistant cancel/reschedule reuse the same backend authority with confirmation.

---

## Changed files

### Orchestrator (`/tmp/wathefni-c3-local/wathefni-orchestrator`)

| File | Change |
|---|---|
| `interview_lifecycle.py` | **New** — schema, status/sync/RSVP normals, conflict checks, operations, reclaim helper, communication truth |
| `interview_service.py` | **New** — schedule / reschedule / cancel, optional Google sync, panel replace, feedback submit/reopen, notes-only, agenda, retention purge, retake cleanup |
| `app.py` | Wire `ensure_interview_schema`; truthful interview summary; company-TZ date filter; panel interviewer filter; cancel/notes/schedule/reschedule/agenda/feedback routes; video completion + AI summary no longer set human scorecard complete; transcript reclaim on worker pass |
| `action_registry.py` | Wathefni-first `schedule_interview`; new `cancel_interview` / `reschedule_interview` ActionSpecs + executors (confirmation + same service) |
| `smoke-test-interviews-remediation.py` | Local unit/registry proof suite |
| `smoke-test-interviews-remediation-unit.py` | Mock-backed schedule/sync/feedback/reclaim proofs (no Postgres) |

### Dashboard (`/tmp/wathefni-c3-local/apps/wathefni-dashboard`)

| File | Change |
|---|---|
| `src/lib/api.ts` | Agenda, schedule, reschedule, feedback client helpers |
| `src/types.ts` | Provider/sync/human feedback/assignment fields |
| `src/lib/recruitingLifecycle.ts` | EN/AR Interviews chrome (tabs, metrics, agenda, panel filter, notes≠scorecard) |
| `src/App.tsx` | Week agenda view; Arabic/RTL Interview queue; tab/row/drawer a11y (roles, Escape, focusable rows); truthful channel/location; sync status |

### Not changed (frozen)

- Ranking formula / interview scoring enablement
- Assessments, Offers, Hiring, Jobs, Candidates redesign
- Mobile schedule/cancel UX (deferred)
- No production/staging deploy

---

## Schema / config delta

Additive only (idempotent `ensure_interview_schema`):

**`candidate_interviews` columns**

- `location`, `duration_minutes`
- `provider_key`, `provider_sync_status`, `provider_sync_error`, `provider_synced_at`
- `channel_send_status`, `rsvp_status`
- `human_feedback_status`
- `retention_expires_at`, `retention_purged_at`
- `schedule_operation_id`

**New tables**

- `interview_schedule_operations` — idempotent schedule/reschedule/cancel ops (`UNIQUE (company_code, idempotency_key)`)
- `candidate_interview_assignments` — normalized panel (user/email, role, organizer/required, RSVP, tenant binding)
- `interview_feedback_definitions` / `interview_feedback_definition_versions`
- `interview_feedback_submissions` / `interview_feedback_submission_revisions`
- `interview_video_retention_operations`

**Constraints / indexes**

- Unique active live interview per `(company_code, app_key)` where status ∈ `{scheduled,rescheduled}` and not `async_video`
- Soft `NOT VALID` CHECKs for status / feedback / human_feedback / time order
- Default GLOBAL feedback definition `default_v1` (1–5 criteria)

**Config**

- `WATHEFNI_GOOGLE_CALENDAR_ENABLED` / `GOG_ACCOUNT` — optional Google
- `WATHEFNI_VIDEO_INTERVIEW_RETENTION_DAYS` (default 90)

---

## Scheduling authority

Wathefni owns:

- candidate/application binding
- interview type / meeting type
- start, end, duration, IANA timezone (company timezone default)
- location or meeting link
- interviewer/panel assignments
- scheduling status
- conflicts (candidate overlap + panel overlap)
- reschedule (in-place active row)
- cancellation (idempotent)
- audit via `candidate_interview_events` with actor context

**Flow:** claim/load idempotency operation → conflict checks → commit Wathefni interview → optional external sync → mark operation completed.

**Modes without Google**

- `in_person` + location
- `phone`
- `manual_link` + link  
`google_meet` without connection falls back to phone (or manual link if supplied).

Retries with the same idempotency key replay the completed operation and do not create a second interview.

---

## Optional calendar sync

Provider model is open (`provider_key`: `none` | `google` | future outlook/teams).

Sync states: `not_configured` | `pending` | `synced` | `update_pending` | `cancellation_pending` | `failed` | `retrying`.

Contract:

1. Commit Wathefni interview first.
2. Sync externally only when configured and meeting type requires it.
3. Google failure → interview remains `scheduled` with `provider_sync_status=failed` and visible error.
4. Reschedule updates the **same** external event when an event id exists (update path; no second active create on update failure).
5. Cancel syncs delete when an event id exists; cancel remains idempotent on Wathefni.

Automatic Google Meet only when Google is connected and meeting type is `google_meet`.

---

## Panel authority

`candidate_interview_assignments` replaces the misleading filter that matched `created_by_phone` / `updated_by_phone`.

Dashboard `interviewer` filter now matches assignee email / name / user id / phone on assignments.

Assignments carry organizer/required flags and RSVP state for later provider attendee sync.

---

## Feedback authority

- Free-text notes API (`save_notes_only`) saves notes + optional advisory AI summary and **does not** set `human_feedback_status=feedback_complete`.
- Version-pinned submissions via `submit_feedback` / controlled `reopen_feedback` with revision audit.
- Finalized submissions are immutable until reopen with reason.
- Two raters can each hold a version-pinned submission.
- Candidate video completion and AI summary generation update transcript/summary only — they no longer mark human feedback complete.
- Service returns `ranking_updated: false`; no interview evidence is pushed into Ranking.

---

## Retention and recovery

- Retention expiry stamped on schedule (`retention_expires_at`).
- `purge_expired_video_files` deletes local files, clears response registry fields, attempts `file_registry` delete/mark, audits `interview_video_retention_operations`.
- `cleanup_retake_files` removes superseded response media.
- `reclaim_stale_transcript_processing` resets stale `processing` → `pending`.
- Worker `process_pending_video_interview_transcripts` reclaims before claiming new work so a crashed worker cannot leave responses permanently stuck.

---

## Communication state model

Summary fields (truthful):

| Field | Meaning |
|---|---|
| `provider_accepted` / `provider_sync_status` | External calendar provider accept / sync |
| `channel_send_status` | Channel send accepted (not proven delivery) |
| `delivered` | Only when channel status is `delivered` |
| `failed` | Channel or provider failed |
| `rsvp_status` | accepted / declined / tentative / pending / not_requested |
| `candidate_confirmation` | Not inferred from calendar create alone |
| `communication_status` | Compatibility mirror — never claims delivery from calendar alone |

Calendar creation is **not** presented as confirmed delivery or candidate acceptance.

---

## Audit / timezone / Arabic / accessibility proof

- Schedule, reschedule, cancel, notes, feedback, and status updates pass `actor_user_id` / `actor_phone` / `actor_role` into events.
- Date filter uses `(scheduled_start AT TIME ZONE company_iana)::date`.
- Company IANA timezone used for parse/display/agenda week bounds.
- Dashboard Interviews EN/AR copy completed for tabs, metrics, agenda, panel filter, notes≠scorecard, sync label.
- Queue tabs expose `role="tab"` / `aria-selected`; rows are keyboard-activatable; drawer is `role="dialog"` with Escape-to-close; pagination announces via `aria-live`.

---

## Test results

### Suite A — `smoke-test-interviews-remediation.py`

**Result:** 22 passed, 0 failed  
Live Postgres proofs **SKIPPED** on this laptop (`psycopg2` unavailable). Unit/registry proofs covered.

Covered:

- Physical / phone / manual-link meeting resolution without Google
- Google Meet connected → pending sync; disconnected → safe fallback
- Provider sync state vocabulary
- Communication truth (calendar ≠ delivered)
- Notes ≠ human feedback complete
- Panel normalize/dedupe
- Assistant `schedule_interview` / `cancel_interview` / `reschedule_interview` registered with confirmation

### Suite B — `smoke-test-interviews-remediation-unit.py`

**Result:** 9 passed, 0 failed (mock DB)

Covered:

- Schedule with no external calendar
- Duplicate idempotency key → one interview / replay
- Google failure leaves valid Wathefni interview + failed sync
- Google success path yields one external event id
- Two raters submit; finalized feedback immutable
- Stale transcription reclaim
- Cancel path does not enable hire side effects

### Proof matrix status

| Proof | Local status |
|---|---|
| Scheduling works with no external calendar | PASS (unit + mock) |
| Physical / phone / manual-link | PASS |
| Duplicate confirmation → one interview | PASS (mock idempotency) |
| Concurrent scheduling one winner | Schema unique index + conflict errors; live race to confirm in staging DB |
| Candidate/panel conflicts fail closed | Implemented; live DB confirm in staging |
| Google-connected creates one external event | PASS (mock); live gog confirm in staging |
| Google failure keeps valid interview + visible sync failure | PASS |
| Reschedule → one active interview + one active external event | Implemented (in-place + update); live gog confirm in staging |
| Cancellation idempotent + external sync when configured | Implemented; mock cancel idempotency path covered in service design; staging for gog delete |
| Two raters version-pinned feedback | PASS |
| Finalized feedback immutable unless reopened | PASS |
| Candidate completion / AI summary ≠ human feedback complete | Code PASS (app.py paths corrected) |
| No interview evidence → Ranking | PASS (`ranking_updated: false`; no ranking writes) |
| No automatic offer / hire / reject | PASS (cancel uses `run_hire_side_effects=False`; no offer hooks) |
| Stale transcription reclaimed | PASS |
| Retention purge removes files + registry refs | Implemented; live file purge confirm in staging |
| Arabic/RTL + a11y Interviews chrome | Code PASS |
| Reports / Assistant / mobile / frozen-module regressions | Assistant wrappers added without duplicating logic; Ranking/Assessments/Offers not reopened; mobile scheduling still deferred |

---

## Remaining defects

1. **Live Postgres + live `gog` proofs** not executed on this workstation (no `psycopg2` / no Google account in local env). Required in staging.
2. **Concurrent schedule race** relies on unique index + conflict handling; needs multi-worker staging stress.
3. **Outlook/Teams** provider keys are reserved only — not implemented.
4. **Mobile scheduling** still deferred (list/detail/notes only).
5. **RSVP from Google attendees** is modeled on assignments but not yet polled from provider webhooks.
6. **`create_candidate_interview_from_schedule` legacy helper** remains for older paths; live Assistant/dashboard schedule now goes through `interview_service`. Staging should confirm no remaining calendar-first callers in production traffic.
7. Dashboard schedule **form UX** is API + agenda ready; full in-drawer schedule composer can be thin-followed in staging if product wants click-path beyond Assistant/API.

None of the above reopen frozen modules or block local remediation close-out.

---

## Guarded staging plan

**Do not deploy from this step.** Next promotion only after owner approval:

1. Build isolated staging artifact from `/tmp/wathefni-c3-local` exactly (include new `interview_lifecycle.py` / `interview_service.py` in deploy file list).
2. Run Tenant ON/OFF matrix for Interviews without enabling Ranking interview scoring.
3. Staging proof checklist:
   - No-Google physical/phone/manual-link schedule
   - Idempotent duplicate confirmation
   - Concurrent schedule race
   - Candidate + panel conflict fail-closed
   - Google connected: one event; failure leaves Wathefni row + failed sync UI
   - Reschedule/cancel sync same event; no duplicate active events
   - Dual rater feedback + reopen audit
   - Video completion / AI summary leave `human_feedback_status=notes_pending`
   - Transcript reclaim after killed worker
   - Retention purge dry-run then real purge on fixture files
   - Arabic/RTL + keyboard/Escape a11y smoke
   - Assistant cancel/reschedule confirmation + idempotent replay
   - Confirm Ranking/Reports/Assessments/Offers/Hiring unchanged
4. Only then consider production promotion with rollback notes for schema (additive; safe to leave).

---

## Stop

Local Interviews remediation is complete. **No deploy performed.**
