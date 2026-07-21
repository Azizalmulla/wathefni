# Jobs Phase 2 — Stage A Contract

**Status:** Staging-green authority cut only. Stage B / production promotion are out of scope.

## Product boundary

- WhatsApp-native hiring; no public job webpage / web CV upload.
- Initial `APPLY` binds a temporary `candidate_job_contexts` row and renders a deterministic preview stub.
- Initial `APPLY` and temporarily held CV media create **zero** canonical `applications` rows.
- Stage B owns preview-sent truth, Luna Q&A, and application creation after explicit apply intent.
- Postgres is authority. Fail closed. No default tenant on candidate APPLY paths. No fuzzy APPLY substitution.

## Schema (idempotent via `ensure_jobs_schema`)

**`positions` additions:** `visibility` (`public|share_only|internal`), `title_en`, `short_summary_en/ar`, `content_approved_*`, `benefits_*`, unique `upper(apply_code)`.

**New tables:** `candidate_job_contexts`, `candidate_pending_media`.

## Publish / eligibility

Publish requires approved EN **or** AR pack, vacancies ≥ 1, employment type, apply identity, company display name, WhatsApp number, and location **or** `fully_remote`.

Eligibility requires explicit `open` status, visibility by access mode, Asia/Kuwait-inclusive deadline, remaining vacancies, and complete approved content.

## External share surface

Backend `shareable` is authoritative. `application_link` / `qr_value` are emitted only when the job is currently eligible for external intake (`public` or `share_only` via exact APPLY). Internal, draft, paused, closed, expired, full, and incomplete-content jobs keep stable `apply_code` identity but return null share surfaces. Dashboard and Assistant share actions must use this authority and must not invent candidate links.

## Validation

- Unit: `smoke-test-jobs-phase2-stage-a-unit.py`
- Guarded staging matrix (22 cases): `smoke-test-jobs-phase2-stage-a.py` with `WATHEFNI_STAGE_A_SMOKE_ACK=staging-only`
