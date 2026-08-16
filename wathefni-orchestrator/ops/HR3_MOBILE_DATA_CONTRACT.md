# HR-3 Operator Mobile Data Contract

Status: backend implementation complete; staging verifier passed 70/70 against
the isolated staging database with dry-run delivery.

## Authority boundary

Every route depends on the HR-1 `operator_mobile` context. Company lifecycle,
module state, current grants, and manager scope are recomputed on every request.
Employee App tokens, browser sessions, and shared legacy authority are rejected
before these handlers run.

Navigation and action visibility must come only from
`GET /dashboard/mobile/me`. HR-task **Mark done** is advertised as
`hr_tasks.actions` including `resolve` when the actor holds
`users.manage` or any post-hire `.manage` grant (same manage gate as web).
Mobile resolve enforces the same manager scope as the open queue
(including hiding `employee_key IS NULL` company-wide tasks from restricted
managers) before calling canonical `resolve_hr_task` and web handoff side
effects. Dismiss / assign remain web-first.

Onboarding `review` (including onboarding-backed document review) is advertised
only while the existing `WATHEFNI_ONBOARDING_HR_MUTATE` dark-launch boundary is
enabled. Compliance-backed document review remains independently governed by
the compliance module and `compliance.manage`.

## Read routes

- `GET /dashboard/mobile/tasks`
  - `items[]`: `task_id`, `task_type`, `source`, `title`, `detail`, safe employee
    identity, `status`, `priority`, timestamps, `allowed_actions`, `destination`.
  - Mobile product default is `status=open` (history stays web-first).
- `GET /dashboard/mobile/tasks/{task_id}`
  - One company/scope-bound task DTO (same manager visibility as the open queue).
- `GET /dashboard/mobile/onboarding`
  - Paged safe employee cards and checklist counts.
- `GET /dashboard/mobile/onboarding/{employee_key}`
  - Safe employee identity, progress counts, and allowlisted checklist items.
- `GET /dashboard/mobile/documents`
  - Paged compliance review queue. Onboarding-only tenants receive the
    authoritative onboarding document queue instead.
- `GET /dashboard/mobile/documents/{employee_key}/{document_type}`
  - One company/scope-bound compliance review DTO.
- `GET /dashboard/mobile/documents/files/{file_id}`
  - Reuses the audited dashboard file handler; local paths and storage internals
    are never returned in metadata DTOs.
- `GET /dashboard/mobile/attendance`
- `GET /dashboard/mobile/attendance/{attendance_id}`
  - Paged/date-filtered allowlisted attendance DTOs.
- `GET /dashboard/mobile/shifts?date=YYYY-MM-DD`
  - One authoritative company-local day. `week` remains accepted for the HR-2
    compatibility window, but its rows are now mobile-safe DTOs.
- `GET /dashboard/mobile/shift-swaps`
- `GET /dashboard/mobile/shift-swaps/{swap_id}`
  - Company/scope-bound request, employee, and shift context without phone,
    source text, or metadata.
- `GET /dashboard/mobile/interviews`
- `GET /dashboard/mobile/interviews/{interview_id}`
  - Candidate/position facts, schedule/status, compact meeting and communication
    state, notes availability, and advisory AI summary on detail. Transcripts,
    invite bodies, calendar IDs, and async-video internals are omitted.

Existing HR-2 leave, candidates, priorities and CV contracts remain registered.
Employee search/quick-profile and delivery alerts now pass through explicit
mobile allowlists rather than returning browser-heavy payloads.

## Writes

- `POST /dashboard/mobile/tasks/{task_id}/resolve`
  - Body: `status` (`done` only on mobile), `expected_status` (`open`).
  - Reuses canonical `resolve_hr_task` + web `candidate_handoff` resume side
    effects and `record_admin_audit`. Not a mobile-only completion workflow.
  - Requires `hr_tasks` feature action `resolve` and the same manage gate as
    web (`users.manage` or any post-hire `.manage`).
  - Loads the task under the open-queue manager scope before mutate (including
    hiding company-wide `employee_key IS NULL` rows from restricted managers).
  - Stale when current status ≠ `expected_status`.
- `POST /dashboard/mobile/onboarding/{employee_key}/review`
  - Body: `item_id`, `outcome` (`received|waived`), optional `note`,
    `idempotency_key`, and confirmation fields.
  - Registry action: `onboarding_mark_item`.
- `POST /dashboard/mobile/documents/{employee_key}/{document_type}/review`
  - Body: optional `note`, `expected_status` (`needs_review`).
  - Registry action: `compliance_mark_reviewed`.
  - This authoritative action is non-sensitive in the existing registry, so it
    executes once through the audited registry path and fails stale if the
    classifier state changed.
- `POST /dashboard/mobile/attendance/{attendance_id}/resolve`
  - Body: target `status`, optional `time`/`notes`, `idempotency_key`, and
    confirmation fields.
  - Registry action: `correct_attendance_record`.
- `POST /dashboard/mobile/shift-swaps/{swap_id}/decision`
  - Body: `action` (`approve|reject`), `idempotency_key`, and confirmation
    fields.
  - Registry actions: `approve_shift_swap` / `reject_shift_swap`.
- `POST /dashboard/mobile/interviews/{interview_id}/notes`
  - Body: `notes`, optional `status`, `generate_summary`.
  - Reuses `dashboard_prehire_interview_notes`, including its event and
    `action_results` audit writes. Mobile does not accept a transcript.

Onboarding, attendance, and shift-swap decisions use the existing HR-2
tenant/operator-bound prepare/confirm store. Confirmation is additionally bound
to the exact route target and registry action. Idempotency conflicts, expiry,
concurrent claims, stale state, replay, and registry-policy changes continue to
fail closed.

## Payload exclusions

Mobile DTOs do not expose company internals, raw JSON, storage URLs/local paths,
source text, employee phones in review queues, interview transcripts, invite
bodies, calendar IDs, or async-video processing payloads.

## Local proof

- `python3 smoke-test-hr3-mobile-data.py`
- `python3 smoke-test-hr2a-mobile-data.py`
- `python3 -m py_compile operator_mobile_data.py smoke-test-hr3-mobile-data.py ops/hr3-staging-verify.py`

## Staging proof

`ops/hr3-staging-verify.py` runs only from the staging orchestrator. It:

- hard-binds the staging env file, workspace, database host/port/name/marker,
  staging app import, and `dry_run` delivery;
- provisions only marker-scoped `HR3MOB` / `HR3OTH` fixtures;
- exercises every new read/write route;
- proves tenant, manager scope, grant revocation, module removal, company
  disable, employee/browser/legacy channel rejection, confirmation,
  idempotent replay, stale decisions, interview audit, and dry-run delivery;
- removes all fixtures in `finally`.

Result: `HR-3 staging: 70 passed, 0 failed`.
