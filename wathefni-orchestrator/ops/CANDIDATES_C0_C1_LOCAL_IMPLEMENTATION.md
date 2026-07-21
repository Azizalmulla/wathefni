# Candidates C0/C1 — Local implementation contract

Date: 2026-07-21  
State: implemented locally; not deployed to staging or production

## Boundary

This change implements Candidates Phase C0 and C1 only. It does not add tags,
bulk candidate decisions, merge UX, privacy workflows, or visual product
expansion.

## Authority and transaction decisions

### Canonical lifecycle

- `applications.status` is the canonical application lifecycle field.
- `applications.current_step` is a compatibility mirror written only by the
  canonical service.
- `applications.lifecycle_version` is a monotonic stale-write boundary.
- `recruiting_lifecycle.transition_application` is the sole transition writer.
- A Postgres trigger rejects direct updates to lifecycle status/current_step
  unless the transaction sets the canonical authority marker.
- Intake-only moves among `needs_role`, `import_review`, and `import_archived`
  remain orthogonal intake state. Admission to Candidates goes through
  `intake_admit`.
- `candidates.current_status` remains for compatibility, is updated in the same
  transaction as the application, is marked derived in profile metadata, and is
  not consulted for lifecycle decisions. The column receives an explicit
  database comment declaring it non-authoritative.

### Durable confirmation

- The backend mints a random one-time confirmation capability.
- Only its SHA-256 digest is stored.
- The durable row binds company, app key, action, observed stage, observed
  lifecycle version, exact target payload/reason, actor identity, channel,
  idempotency key, and bounded expiry.
- Execution locks and re-reads the application, rechecks current permission,
  validates the capability, validates actor/payload/stage/version, claims the
  confirmation, commits the lifecycle event, and consumes the confirmation in
  one transaction.
- AI actors are rejected at the lifecycle boundary.
- Missing `human_confirmed` defaults to false in registry executors.
- Dashboard, mobile, and Assistant flows converge on the same backend-issued
  confirmation. The dashboard no longer treats a client dialog alone as proof.

### Structured reasons

- Rejection requires `reason_code`; `note` is optional.
- HR withdrawal requires `reason_code` and source `hr`; candidate self-withdrawal
  records source `candidate`.
- Hire requires a durable hiring operation/reference.

### CV contract

- Initial accepted CV: `awaiting_cv → cv_processing`.
- Successful extraction: `cv_processing → ready_for_review`.
- Failed extraction: `cv_processing → awaiting_cv`.
- Worker retries use document-scoped lifecycle idempotency keys.
- Facet/document writes no longer directly update application lifecycle fields.
- CV replacement is stored as `awaiting_confirmation`; only a state-bound
  candidate confirmation releases it to extraction. Failed replacement does not
  replace the current authoritative CV.

### Interview contract

- Draft preparation, async video interview creation, and invite preparation do
  not advance the application.
- A successfully created, explicitly confirmed live schedule advances
  `ready_for_review|shortlisted → interview` through the canonical service.
- Calendar creation failure does not advance application stage.
- Reschedule keeps an existing `interview` stage idempotently.
- Cancel, no-show, and completed interview update the interview facet only; they
  do not silently regress or revive the application.
- Drift between open interview records and application stage is reported for
  reconciliation; it is not silently overwritten.

### Hiring contract

- `hire_operations` is the durable operation record.
- Offer/hire gate runs before execution.
- Application transition, lifecycle event, employee upsert/link, application
  employee reference, compliance/onboarding seed, and operation completion share
  one Postgres transaction.
- Application cannot commit as `hired` if employee creation/linking fails.
- A repeated completed operation returns the committed result without creating a
  second employee.
- A prepared operation is recoverable; a committed operation has the employee
  key and confirmation reference.
- External sheets or delivery mirrors are not part of the committed success
  statement.

### Active same-role duplicate contract

- Transitional identity key: `(phone, company_code, position_code)`.
- The partial unique index covers all active lifecycle states.
- `rejected`, `withdrawn`, `hired`, `needs_role`, `import_review`, and
  `import_archived` are excluded, so valid historical reapplication remains
  possible.
- Installation is explicitly gated by a read-only collision report. No row is
  deleted or merged automatically.

## Lifecycle-writer inventory and disposition

- `recruiting_lifecycle.transition_application`: retained as sole authority.
- `app.update_application_status`: changed to an unconditional canonical facade;
  legacy CLI fallback and `WATHEFNI` fallback removed.
- `app.register_candidate_cv_file`: lifecycle writes removed; document/facet only.
- `app.process_candidate_cv_document`: direct success write and forged event
  removed; canonical CV success/failure calls added.
- `app.handle_candidate_screening_turn`: direct `screening_complete` lifecycle
  write removed.
- `action_registry._send_screening_questions_executor`: direct lifecycle write
  removed and company scope required.
- `action_registry._status_mutation_executor`: confirmation default false;
  canonical confirmation envelope required.
- `action_registry._schedule_interview_executor`: confirmation default false;
  canonical transition after durable schedule only.
- `action_registry._hire_candidate_executor`: routes to durable atomic hire.
- Dashboard shortlist/reject/hire: routes through backend mint/consume.
- Mobile candidate decisions: existing server confirmation wraps the shared
  registry flow, which now mints/consumes the candidate confirmation.
- Assistant `pending_actions`: stores the backend confirmation envelope at
  preview and injects it only after matching human approval.
- Candidate withdrawal: backend confirmation is minted at the first request and
  consumed on the explicit second turn.
- Import assignment/bulk admission: role/intake facets update first; admission
  uses canonical `intake_admit`.
- Initial application creation remains an insert, not a lifecycle transition.
- `candidates.current_status` writes on creation remain compatibility seed data;
  transition-time truth is derived from `applications.status`.
- Historical smoke/proof utilities still containing direct fixture updates:
  `smoke-test-bulk-cv-import.py`,
  `ops/mobile-lifecycle-authority-staging-proof.py`,
  `ops/mobile-lifecycle-authority-production-proof.py`,
  `ops/offer1-owner-review.py`, and
  `ops/offer1-production-cutover-proof.py`. These are not runtime handlers or
  workers. The new database trigger blocks their direct status updates; they
  must be migrated to canonical fixture preparation before reuse.

## Additive schema

- `applications.lifecycle_version bigint NOT NULL DEFAULT 0`
- database comment marking `candidates.current_status` as a derived mirror
- `candidate_action_confirmations`
- lifecycle confirmation indexes
- application lifecycle direct-write guard function and trigger
- `hire_operations`
- hire operation idempotency/open-operation/reconciliation indexes
- guarded installer for `applications_one_active_same_role_uq`
- guarded installer for `employees_company_app_key_uq`

## Current collision evidence (read-only)

Production database `wathefni`:

- active same-role collisions: 0
- duplicate employee links by company/app key: 0
- hired applications without an employee link: 0

Staging database `wathefni_staging`:

- active same-role collisions: 0
- duplicate employee links by company/app key: 0
- hired applications without an employee link: 1
- affected staging fixture: `WATHEFNI / smoke-B74F3E8F`

The staging half-hire is not deleted or auto-repaired. It must be classified and
cleaned or forward-reconciled before the hiring proof and guarded index install.

## Changed files

- `recruiting_lifecycle.py`
- `hire_operations.py`
- `action_registry.py`
- `tool_call_orchestrator.py`
- `app.py`
- `cv_extraction.py`
- `cv_docx.py`
- `test_candidates_c01.py`
- `smoke-test-canonical-recruiting-lifecycle.py`
- `ops/deploy.sh`
- `ops/wathefni-orchestrator-production-environment.conf`
- `apps/wathefni-dashboard/src/App.tsx`
- `apps/wathefni-dashboard/src/lib/api.ts`
- `apps/wathefni-dashboard/src/types.ts`
- `apps/wathefni-dashboard/src/lib/lifecycle-labels.test.ts`
- `ops/CANDIDATES_C0_C1_LOCAL_IMPLEMENTATION.md`

## Local verification

- Python compile: passed for all changed backend modules and tests.
- C0/C1 authority suite: 12/12 passed.
- Canonical lifecycle smoke: all local matrix checks passed; Postgres section
  skipped because local `psycopg2`/Postgres is unavailable.
- Dashboard tests: 49/49 passed.
- Dashboard TypeScript/Vite production build: passed.
- Changed-file IDE diagnostics: no errors.
- Scoped dashboard ESLint is red on three existing `App.tsx` mailbox-import
  `react-hooks/set-state-in-effect` findings (lines 5927, 5934, 5954), plus nine
  existing hook-dependency warnings. None is in a C0/C1 changed hunk; dashboard
  build and tests pass.
- `npm ci` reports four existing dependency advisories (one low, three high);
  dependency remediation is outside C0/C1.

## Remaining risks

- The new Postgres schema, trigger, partial indexes, and atomic hire transaction
  have not yet run in staging.
- The staging half-hire fixture must be resolved before hire qualification.
- Historical proof scripts that directly update fixture lifecycle stages are
  now intentionally blocked by the authority trigger and must be updated before
  they are reused.
- The active-role and employee-link unique indexes are implemented but are
  intentionally not installed automatically before a clean collision gate.
- CV replacement confirmation and Assistant/mobile adapter behavior need real
  Postgres and end-to-end staging proof.
- Existing production rows begin at lifecycle version zero after migration; this
  is expected and additive.
- No production or staging deployment was performed in this phase.

## Proposed guarded staging plan

1. Take a staging DB backup and capture `wathefni_staging` identity.
2. Re-run active-role, employee-link, and half-hire collision reports.
3. Resolve only `smoke-B74F3E8F` through an explicit cleanup or forward-repair
   decision; do not delete/merge unknown records.
4. Deploy the exact local artifact to staging only.
5. Run additive schema creation and verify lifecycle trigger.
6. Install active-role and employee-link unique indexes only when both collision
   gates are clean.
7. Run the full required C0/C1 matrix with dedicated staging company, users,
   applications, jobs, documents, interviews, offers, and idempotency keys.
8. Simulate hire crashes around operation preparation and the atomic commit;
   verify one employee and replay recovery.
9. Verify dashboard, mobile, and Assistant allowed actions and English/Arabic
   confirmation text from the same fixtures.
10. Verify OpenClaw and production services/config/artifacts remain unchanged.
11. Produce cleanup SQL keyed by staging company/app/document/operation IDs.
12. Stop for owner approval before any production change.
