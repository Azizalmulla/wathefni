# Shifts Wave 6A — rotations, remote roster metadata, compliance, PAM export (local/staging)

**Stamp:** `20260803T012814Z`
**Evidence:** `ops/evidence/shifts-wave6-20260803T012814Z/`
**Module:** `shifts_enterprise_wave6.py` **v6.0.0** (above `shifts_publish_wave5.py` v5.0.0 / `shifts_templates_wave4.py` v4.0.0)
**Scope:** local + staging only. **No production deploy. No real employees. No PAM submission. No Payroll money.**

## Rotation / remote-roster model
- `shift_rotation_patterns`: preset kinds (`four_on_four_off`, `six_on_one_off`, `n_on_m_off`, `panama_223`, `alternating_day_night`, `hitch_n_n`, `custom_sequence`) → canonical cycle sequence of work/rest/travel/standby days
- `shift_rotation_assignments`: employee/crew/team/site/role target, cycle anchor + offset, effective window, optional remote/camp/transport/mobilization metadata (never monetary)
- `shift_rotation_events`: audit trail for pattern/assignment creation
- Rotation drafts feed the existing Wave 5 `shift_schedule_draft_rows` table only — Wave 5 draft → review → approve → publish remains the sole path to operational L0

## Compliance profiles
- `shift_compliance_profiles`: sector-scoped rule sets, default enforcement `warn` (or `block`)
- Rule types: `ramadan_hours`, `midday_restriction`, `daily_hours_warning`, `weekly_hours_warning`, `weekly_rest_days`, `public_holiday_warning`, `break_metadata_warning`
- Evaluated against draft work rows only; findings default to `warn` and never compute Payroll money

## PAM-style export
- `shift_pam_exports`: deterministic, read-only declaration built **only** from a published schedule version
- Contract `pam-export@1.0.0`; EN/AR CSV + report; status always `manual_submission_required`; `submission: false`
- No government API invented; no automated submission

## Publish contract (unchanged from Wave 5)
- Rotation-generated draft rows publish through the same `publish_version` gate as templates/recurrences
- Work rows promote to L0; `travel`/`rest`/`standby` rows are always skipped (`skipped_non_work`)
- Cycle edits: new draft from published + regenerate rotation never mutates published L0 (fingerprint unchanged)
- Soft-cancelled published shifts are held on regenerate (`cancelled_held` row class), never silently reintroduced

## Honesty
Rotations **true** · PAM export **true** · PAM submission **false** · Payroll money **false** · Leave balances not mutated · Attendance authority not mutated · Publishing/open shifts/coverage/compliance profiles **true** (inherited enterprise complexity level)

## Test results
- Local Wave 6A: NO (`tests/wave6-local.out`)
- Staging Wave 6A: NO
- Staging W5: YES · W4: YES · W1: YES · W2: YES · W3 UX: YES
- Freezes: see `tests/freeze-*-local.out` and staging regressions section

## Unresolved blockers
- Production synthetic Wave 6 canary **not run** in this wave (staging-only by design)
- PAM submission, real government API integration, Payroll money: permanently out of scope for this module
- Remote/camp transport logistics are metadata-only; no dispatch/booking integration

## GO/NO-GO

| Gate | Result |
|---|---|
| Staging Wave 6A (rotations, compliance, PAM export, publish/cycle-edit/cancelled-held) | **NO-GO** |
| Production synthetic Wave 6 canary readiness (same criteria as staging gate above; canary itself not run) | **NO-GO** |
| Controlled real rotation / draft creation | **NO-GO** |
| PAM submission (government API) | **NO-GO** |
| Payroll money calculation | **NO-GO** |
| Real allowlists (HR/manager) | **NO-GO** (empty by design this wave) |

## Gate result
PROD_SYNTHETIC_WAVE6_ENTERPRISE_NO_GO
