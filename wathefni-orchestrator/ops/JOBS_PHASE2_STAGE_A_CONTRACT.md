# Jobs Phase 2 — Stage A Contract

**Status:** APPROVED, CLOSED, and FROZEN on staging.

| Pin | Value |
|---|---|
| Authority commit | `674562231c40687029bdce1b37b094ce847890b2` |
| Share-surface remediation commit | `62f13c997bb96f24f7625fe248ab7a7832a305cc` |
| Staging-green artifact | `faab36196cd5a74ee4aa0cfdf32950b2b8e470ac32ec396064a50afd10c093ce` |
| Production | Unchanged. No production promotion from Stage A. |

Stage B / production promotion remain out of scope for this document. See `JOBS_PHASE2_STAGE_B_ASSESSMENT.md` for the design-only Stage B plan.

## Closure contract (frozen)

- Exact APPLY resolution only; no fuzzy substitution.
- Initial APPLY creates a temporary `candidate_job_contexts` row, never an application.
- CV media may be held temporarily in `candidate_pending_media`, but Stage A creates **zero** applications.
- External eligibility is backend-owned and fail-closed.
- Draft, internal, paused, closed, expired, full, or content-ineligible jobs are not externally shareable.
- Candidate `application_link` / `qr_value` are exposed only when backend `shareable` is true.
- Dashboard and Assistant never construct candidate links independently of that authority.
- Publishing requires one approved candidate language pack and the canonical minimum operational fields.
- Assistant-created jobs remain drafts.
- No tenant fallback on candidate APPLY paths.
- Production remains unchanged.

## Product boundary

- WhatsApp-native hiring; no public job webpage / web CV upload.
- Initial `APPLY` binds a temporary job context and renders a deterministic preview stub (`preview_rendered_at`).
- Stage B owns preview-sent truth (`preview_sent_at`), Luna Q&A over approved fields, and application creation after explicit apply intent.
- Postgres is authority. Fail closed.

## Schema (idempotent via `ensure_jobs_schema`)

**`positions` additions:** `visibility` (`public|share_only|internal`), `title_en`, `short_summary_en/ar`, `content_approved_*`, `benefits_*`, unique `upper(apply_code)`.

**New tables:** `candidate_job_contexts`, `candidate_pending_media`.

## Publish / eligibility

Publish requires approved EN **or** AR pack, vacancies ≥ 1, employment type, apply identity, company display name, WhatsApp number, and location **or** `fully_remote`.

Eligibility requires explicit `open` status, visibility by access mode, Asia/Kuwait-inclusive deadline, remaining vacancies, and complete approved content.

## External share surface

Backend `shareable` is authoritative. `application_link` / `qr_value` are emitted only when the job is currently eligible for external intake (`public` or `share_only` via exact APPLY). Internal and otherwise ineligible jobs keep stable `apply_code` identity but return null share surfaces.

## Validation pins

- Unit: `smoke-test-jobs-phase2-stage-a-unit.py` (authority + shareability)
- Guarded staging matrix (22 cases): `smoke-test-jobs-phase2-stage-a.py` with `WATHEFNI_STAGE_A_SMOKE_ACK=staging-only`
- Owner UX marker retained on staging: `OWNERUX-07210122`
