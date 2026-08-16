# Leave Wave 3 — Partial-day, unpaid boundary, evidence workflows

**Stamp:** `20260802T164307Z`  
**Evidence:** `ops/evidence/leave-wave3-workflow-20260802T164307Z/`  
**Scope:** local/staging only. No production deploy. `enforced=false`, `legal_reviewed=false`.

## Verdict

| Gate | Result |
|------|--------|
| Staging Wave 3 smoke | **58/58 PASS** |
| Employees 360 freeze | **57/57 PASS** |
| Onboarding freeze | **54/54 PASS** |
| Attendance freeze | **26/26 PASS** |
| Production synthetic canary | **NO-GO** (not requested / not run) |
| Controlled real HR leave operation | **NO-GO** |

## Request and duration model

| Field | Values | Notes |
|-------|--------|-------|
| `duration_unit` | `full_day` \| `half_day` \| `hourly` | Default `full_day` (legacy compatible) |
| `half_portion` | `am` / `pm` | Half-day only |
| `start_time` / `end_time` | `time` | Hourly; overnight windows supported |
| `shift_id` | optional uuid | Prefer effective scheduled shift |
| `chargeable_days` | `numeric(8,4)` | Fractional; stored on request |
| `chargeable_hours` | `numeric(8,2)` | Deterministic from shift length |

- Partial-day is **single calendar day** only.
- Chargeable hours/days use **effective Shift authority** (`shift_assignments` for that date; overnight + split-shift aware).
- Overlap detection spans full-day ↔ partial-day (full-day collides with any partial on shared dates; AM/PM halves do not collide; hourly uses time intervals).
- Reservations/consume/reversal prefer stored `chargeable_days` (Wave 2 `chargeable_days_for_leave`) so partial leave cannot silently bypass fractional reservations.
- Status additions: `needs_info`, `withdrawn` (pre-decision). Approve remains `requested`/`needs_review` only.

Workflow actions (Wave 3 flag `WATHEFNI_LEAVE_WORKFLOW_WAVE3`, default on non-prod):

- `request_leave` (duration fields)
- `return_leave_for_info` → `needs_info` (reservation kept)
- `resubmit_leave_request` → `requested`
- `withdraw_leave_request` → `withdrawn` + reservation release
- `cancel_leave_request` — future approved OK + reverse; **started** → `leave_already_started` (unless `allow_cancel_started`); **taken** → `leave_already_taken`
- Attachment upload / replace / reject / list (masked)

## Unpaid-leave boundary

- Catalogue type `unpaid` with Wave 2 `payroll_boundary`.
- Reserve/consume **skipped** (`unpaid_payroll_boundary`).
- On request/approve: `build_unpaid_payroll_handoff` + `leave_payroll_handoff_events`.
- Payload = classification + duration only (`chargeable_days`/`hours`, dates, type).  
  **No** `salary_deduction`, `pay_fraction`, amounts, or KD fields.
- Leave never calculates salary deductions; Payroll owns monetary impact.

## Attachment / privacy model

Tables: `leave_request_attachments` (versioned, replace chain, provenance), `leave_attachment_audit`.

| Concern | Behavior |
|---------|----------|
| Versioning | Replace bumps `version`, prior → `replaced` |
| Sensitive categories | `medical` / `sick` / `sensitive` / `confidential` |
| Masking | Non-privileged viewers get `[redacted]` filename, no `storage_ref` |
| Access | Self / denied viewers masked; HR privileged or non-self manager scope may see sensitive |
| Reject | `status=rejected` + audit row |

## Staging proofs covered

- Half-day and hourly requests  
- Overnight and split-shift partial leave  
- Full-day vs partial-day overlap  
- Concurrent partial reservations (AM+PM threads)  
- Approve, reject, withdraw, cancel reversal  
- Already started / taken denial  
- Unpaid Payroll handoff with `monetary_fields_present=false`  
- Attachment upload, replace, reject, audit  
- Sensitive-document masking  
- Stale concurrency + self-approval denial  
- Attendance derivation on approve; reverse event-before-delete ordering fix  
- Frozen E360 / Onboarding / Attendance regressions green  

## Sources

- `wathefni-orchestrator/leave_workflow_wave3.py` (v3.0.0)
- `leave_authority_wave1.py` — `needs_info` / `withdrawn`
- `leave_policy_wave2.py` — `chargeable_days_for_leave`
- `app.py` — request/approve/reject/cancel + Wave 3 workflow/attachment APIs
- `smoke-test-leave-workflow-wave3.py`
- `ops/migrate-leave-workflow-wave3.sh`
- `ops/qualify-leave-workflow-wave3-staging.sh`

## Remaining blockers

1. **Production Wave 3 not deployed** — explicit local/staging only.
2. **`enforced=false` / `legal_reviewed=false`** — balance enforcement and legal sign-off still deferred.
3. **WhatsApp/UI surface** — duration/attachment/RFI actions are API/callable only; no Leave UI redesign.
4. **Partial attendance semantics** — approve still stamps `approved_leave` for the day with duration metadata path; finer half/hourly attendance banding not in this wave.
5. **Real balance mutation / Payroll money path** — intentionally out of scope.
6. **Prod synthetic canary script** — not written; blocked until staging GO is accepted for a Wave 3B canary plan.

## GO / NO-GO

| Target | Decision |
|--------|----------|
| Staging Wave 3 workflows | **GO** (observe-only) |
| Production synthetic canary | **NO-GO** until explicit Wave 3B deploy + canary plan |
| Controlled real HR leave operation | **NO-GO** (`enforced=false`, no real balance enforcement, attachments/privacy not prod-hardened) |
