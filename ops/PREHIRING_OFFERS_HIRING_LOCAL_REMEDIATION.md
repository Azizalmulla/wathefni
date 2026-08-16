# Pre-Hiring Offers and Hiring — Local Remediation

**Date:** 2026-07-25 (Kuwait)  
**Mode:** contained local implementation and qualification  
**Deployment:** none  
**Production/staging changes:** none  
**Source worktree:** `/tmp/wathefni-c3-local`  
**Base commit:** `438241b10d5a55cdc8c84a01d2e66d71eac9e2d7`  
**Contained source digest:** `8bcf99cd394236a28e033fd5cd43e2b22a805cba62b70acc5bc0e6ec10c96d09`

## Executive result

The confirmed Offers/Hiring blockers were remediated locally without changing the authority of Jobs, Candidates, Ranking, Reports, Assistant, Assessments, or Interviews.

The contained local proof is green for:

- compensation and document redaction;
- dashboard PDF authorization;
- canonical `sent → expired` processing;
- stale-token revocation and zero compensation disclosure after expiry;
- concurrent send deduplication;
- known provider-failure retry;
- fail-closed unknown provider/DB outcome handling;
- resend token replacement;
- no persisted raw offer token or response URL;
- public-page XSS escaping and restrictive CSP;
- one accepted agreement per application;
- append-only offer versions/events;
- Arabic generated-document rejection and validated uploaded-PDF authority;
- explicit hire-override confirmation and final outcome recording;
- canonical hire-path enforcement;
- dashboard confirmation for approve, send, response recording, resend, and withdrawal;
- preserved atomic/idempotent hire authority;
- preserved AI and Ranking/Assessment/Interview isolation.

No deployment was performed. No production or staging data/provider state was changed.

## Preserved authority

The remediation preserves these boundaries:

- an offer remains a separate lifecycle from the application;
- application stages still do not include offer states;
- when `employment_offers` is enabled, canonical hire requires one accepted offer or an explicitly confirmed, permissioned, audited human override;
- `hire_operations` remains the only runtime employee-creation authority;
- employee creation remains a transactional side effect of the `hired` transition;
- AI cannot mutate offers or invoke hire override;
- Ranking, Assessments, and Interviews do not import into or decide the offer lifecycle;
- Reports remain aggregate consumers and do not receive compensation authority.

## Changed files

Backend:

- `/tmp/wathefni-c3-local/wathefni-orchestrator/offer_lifecycle.py`
  - compensation permission;
  - localization/document-governance columns;
  - delivery-operation schema;
  - accepted-agreement uniqueness;
  - status constraints;
  - append-only triggers;
  - truthful English-only generated PDF behavior.
- `/tmp/wathefni-c3-local/wathefni-orchestrator/offer_service.py`
  - governed draft/version fields;
  - approval validation;
  - expiry authority;
  - durable send/resend;
  - deterministic recoverable token derivation;
  - compensation redaction;
  - accepted-agreement guard;
  - hire-override execution outcome.
- `/tmp/wathefni-c3-local/wathefni-orchestrator/offer_routes.py`
  - localization request fields;
  - send/resend idempotency requests;
  - PDF permission propagation;
  - escaped public HTML;
  - CSP/security headers.
- `/tmp/wathefni-c3-local/wathefni-orchestrator/offer-lifecycle-worker.py`
  - idempotent due-offer expiry worker entrypoint.
- `/tmp/wathefni-c3-local/wathefni-orchestrator/app.py`
  - role grants for `offer.compensation.read`;
  - redacted outbound-delivery audit payload support;
  - legacy direct-hire rejection;
  - explicit hire confirmation default;
  - override outcome finalization.
- `/tmp/wathefni-c3-local/wathefni-orchestrator/action_registry.py`
  - canonical gate result retained;
  - override final outcome recorded;
  - failed execution outcome recorded.

Dashboard:

- `/tmp/wathefni-c3-local/apps/wathefni-dashboard/src/components/OfferPanel.tsx`
  - permission-aware compensation presentation;
  - country/legal-entity/document governance inputs;
  - approved uploaded-PDF input;
  - explicit critical-action confirmations;
  - resend action.
- `/tmp/wathefni-c3-local/apps/wathefni-dashboard/src/lib/offers-api.ts`
  - localization fields;
  - redaction type;
  - idempotent send/resend calls.
- `/tmp/wathefni-c3-local/apps/wathefni-dashboard/src/App.tsx`
  - effective permissions passed to the offer panel.

Proof:

- `/tmp/wathefni-c3-local/wathefni-orchestrator/test_offers_hiring_local_remediation.py`
- `/tmp/wathefni-c3-local/apps/wathefni-dashboard/src/components/OfferPanel.test.tsx`
- `/Users/azizalmulla/Desktop/claw/ops/PREHIRING_OFFERS_HIRING_LOCAL_REMEDIATION.md`

The worktree already contained frozen-module changes from prior approved work. No commit was created, and no unrelated file was intentionally modified by this remediation.

## Schema delta

### `employment_offers`

Added:

- `country_of_employment`;
- `employing_legal_entity`;
- `document_language`;
- `template_id`;
- `template_version`;
- `template_approval_ref`;
- `employer_policy_version`;
- `authorized_signatory`;
- `configuration_effective_date`.

Added database controls:

- status `CHECK` covering only `draft`, `pending_approval`, `approved`, `sent`, `accepted`, `declined`, `expired`, and `withdrawn`;
- partial unique index allowing at most one `accepted` offer for `(company_code, app_key)`.

### `employment_offer_delivery_operations`

New durable operation table:

- one operation ID;
- tenant, offer, and exact offer version;
- `send` or `resend`;
- `prepared`, `processing`, `sent`, `failed`, or `manual_review`;
- caller idempotency key;
- recipient/channel/document hash;
- token hash and token-row reference;
- delivery-row reference;
- safe provider result only;
- attempt count, timing, error, and actor.

Controls:

- unique `(company_code, idempotency_key)`;
- one initial `send` operation per offer version;
- status and operation-kind constraints;
- recovery index for nonterminal operations.

No raw token, response URL, or candidate message containing the URL is stored in this table.

### `employment_offer_hire_override_audits`

Added:

- `execution_status`: `pending`, `completed`, or `failed`;
- `executed_at`;
- `execution_error`;
- `hire_operation_id`;
- `employee_key`.

The audit now records both authorization and final execution truth.

### Append-only controls

`employment_offer_versions` and `employment_offer_events` reject direct update and direct delete.

Parent/retention deletion must use the parent-offer retention authority. A session-scoped `wathefni.offer_retention_delete=on` escape hatch exists for an explicit retention/privacy transaction; ordinary lifecycle code cannot rewrite legal history.

## Configuration delta

New optional secret:

- `WATHEFNI_OFFER_TOKEN_SECRET`.

If absent, the service uses the existing protected assessment-link secret authority. Production has no insecure random-token persistence fallback.

New optional company setting:

- `employment_offer_document_defaults`.

Supported keys:

- `country_of_employment`;
- `employing_legal_entity`;
- `document_language`;
- `currency`;
- `template_id`;
- `template_version`;
- `template_approval_ref`;
- `employer_policy_version`;
- `authorized_signatory`;
- `configuration_effective_date`.

These are company defaults only. The exact resolved values are copied onto every offer and its terms snapshot.

The expiry worker is:

`python offer-lifecycle-worker.py --loop --sleep 60 --limit 100`

No service/unit was installed or started locally as part of this remediation.

## Permission model

New dedicated scope:

- `offer.compensation.read`.

Default grants:

- owner;
- HR manager;
- recruiter;
- hiring manager.

Not granted:

- viewer;
- generic `prehire.read`;
- AI;
- candidate/session actors on dashboard routes.

Without the scope, offer DTOs retain non-sensitive workflow identity/status but return:

- `base_salary = null`;
- empty allowances;
- no start/probation terms;
- empty canonical terms;
- no English/Arabic wording;
- no internal notes;
- no document hash, filename, source, or download availability;
- `compensation_redacted = true`.

The dashboard document endpoint independently enforces the scope and returns `403` without it.

## Document and GCC/Kuwait contract

Every offer records:

- country of employment;
- employing legal entity;
- document language;
- currency;
- approved template ID and version;
- template approval reference;
- employer policy version;
- authorized signatory;
- governing configuration effective date.

Submission for approval fails closed if any field or validated document is missing.

No Kuwait or GCC-wide legal template is hardcoded. `KWD` is no longer a service/API default for new drafts. Company defaults may provide it, but the resolved value is recorded explicitly.

Wathefni does not claim legal compliance. The employer remains responsible for approving its terms, policy, template, signatory, country pack, and effective date.

## Arabic document proof

The old renderer could silently replace Arabic with `?`. That behavior is removed.

Current contract:

- Wathefni-generated documents are English-only;
- any non-ASCII generated document request fails closed;
- Arabic documents require a company-approved uploaded PDF;
- the upload must be explicitly confirmed as matching the canonical terms;
- template/version/approval/policy/signatory/configuration metadata must be complete;
- the exact uploaded bytes and SHA-256 are retained as the versioned artifact.

Local proof:

- Arabic draft without an uploaded PDF was rejected with `arabic_upload_required`;
- confirmed uploaded PDF bytes were preserved exactly;
- the version reported `document_source=uploaded`;
- approval succeeded only after upload/governance validation.

This is the approved fallback from the assessment, not a claim that Wathefni now generates shaped Arabic PDFs.

## Expiry contract

Authority:

- only a `sent` offer can expire;
- due comparison uses the persisted `expires_at`;
- transition is a conditional `sent → expired` update under row lock;
- all unused tokens are revoked in the same transaction;
- one append-only `expired` event is written;
- repeated expiry is a no-op;
- `expired` is excluded from the open-offer uniqueness index, enabling replacement.

Enforcement:

- worker-driven expiry;
- lazy expiry before manual response;
- lazy expiry before candidate token response;
- lazy expiry before public preview;
- expiry check before send/resend claim.

Stale public links return `410` and no compensation payload.

## Send contract

1. Lock the offer.
2. Validate tenant, status, permission, document version, expiry, and idempotency.
3. Create the durable operation.
4. Create the hashed token row.
5. Create the pending delivery row.
6. Transition the offer to `sent`.
7. Commit this authority before provider delivery.
8. Claim the operation for processing.
9. Deliver once.
10. Record safe provider outcome.

Concurrent behavior:

- same idempotency key returns the same operation;
- a second request rechecks after waiting for the offer row lock;
- only one request can change `prepared/failed → processing`;
- one initial-send partial unique index prevents a second initial operation.

The candidate link is valid before provider delivery. A successful provider call cannot produce an unpersisted/broken token.

Known provider rejection:

- operation becomes `failed`;
- no successful message is claimed;
- retry with the same idempotency key reuses the same token and operation.

Unknown provider/DB outcome:

- operation becomes `manual_review`;
- automatic replay is prohibited;
- the already-authorized token remains valid if the provider accepted the message;
- a repeated call with the same key does not send again.

## Resend contract

Resend requires:

- current offer status `sent`;
- `offer.send`;
- a new caller-supplied idempotency key.

The claim transaction:

- revokes every prior unused token;
- creates one deterministic replacement token hash;
- creates one replacement delivery operation;
- preserves the exact approved offer version and document hash.

The old link returns `410`. Replaying the same resend key does not create another message.

## Secret-handling proof

Raw response tokens are derived in memory from a protected HMAC secret and operation ID. Only SHA-256 token hashes are stored.

Persistence surfaces were checked:

- token table;
- delivery metadata;
- operation provider result;
- lifecycle event payload;
- outbound delivery `message_text`;
- outbound delivery provider payload.

The live local dry-run audit proof confirmed:

- stored message text was `[employment offer secure link redacted]`;
- neither the raw token nor response URL appeared in the audit payload;
- the synthetic outbound audit row was deleted.

## Public-page security contract

All rendered values are HTML escaped, including:

- position title;
- candidate name;
- salary;
- currency;
- start date;
- status;
- version;
- prior decision;
- error message;
- token path attribute.

Security headers:

- `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`;
- `Referrer-Policy: no-referrer`;
- `X-Content-Type-Options: nosniff`;
- `Cache-Control: no-store`.

The page contains no script authority.

## Sole hire authority

Removed executable legacy behavior:

- direct `update_application_status(app, "hired")`;
- separate `transition_hire(app)` after application mutation.

Both legacy `hire_candidate` handlers now fail closed with:

- `canonical_hire_required`;
- `required_authority=hire_operations`.

Runtime search found:

- no remaining direct `update_application_status(..., "hired")`;
- no remaining direct runtime call to `transition_hire(app)`;
- the canonical `to_stage="hired"` call remains in `hire_operations`;
- it includes `_employee_transaction` as the transactional side effect.

The registry/dashboard canonical paths still:

- enforce the offer gate first;
- require backend confirmation and prepared operation ID;
- execute `hire_operations`;
- create/link one employee atomically;
- report failure without a half-hire.

## Accepted-agreement authority

Two controls enforce one governing accepted agreement:

- transactional precheck before manual/token acceptance;
- partial unique database index on `(company_code, app_key) WHERE status='accepted'`.

No supersede operation was introduced. Therefore a second accepted offer is always rejected with `accepted_offer_exists`.

A future supersede feature must be explicit, human-confirmed, append-only, and audited; it is not implied by this remediation.

## Hire override contract

`DashboardHireRequest.confirm` now defaults to `false`.

Override requires:

- human actor;
- grant-only `offer.hire_override`;
- meaningful reason;
- explicit confirmation;
- canonical hire operation reference;
- persisted authorization audit.

After execution, the same audit records:

- completed or failed;
- execution time;
- operation ID;
- employee key on success;
- final error on failure.

An exception during hire execution records failed outcome before propagating.

## Dashboard confirmation UX

Explicit dialogs now precede:

- approval;
- send;
- resend;
- manual acceptance;
- manual decline;
- withdrawal.

The send dialog states one secure link will be issued. Resend states that the previous link will be revoked. Manual response dialogs require independent evidence for the exact decision/version. Withdrawal is destructive.

## Local proof

Focused remediation:

- `test_offers_hiring_local_remediation.py`: **PASS**.
- schema creation: **5 constraints, 2 append-only triggers**.
- Python compile for all changed backend/proof files: **PASS**.
- IDE diagnostics: **0 errors**.

Focused proof covered:

- generic-reader redaction;
- PDF denial/authorized read;
- Arabic upload gate;
- concurrent send;
- one delivery operation/row;
- known provider failure retry;
- post-provider DB finalization failure;
- manual-review no-auto-retry;
- working link after uncertain DB outcome;
- no token persistence;
- resend revocation;
- idempotent expiry;
- one expiry event;
- XSS escaping/CSP;
- append-only protection;
- one accepted agreement;
- override final outcome;
- sole-hire source authority;
- no offer-service dependency on Ranking, Assessments, or Interviews.

Existing Offers/Hiring:

- `smoke-test-offer-lifecycle.py`: **PASS**.
- `smoke-test-offer-hire-override.py`: **PASS**.
- pre-hire registry parity’s atomic-hire assertions: **PASS**, including one atomic operation, no half-hire, and confirmation fail-closed.

Frozen unit regressions:

- Candidates/Ranking/Reports Python unit pack: **141/141 PASS**.
- Interviews focused frozen tests: **14/14 PASS**.
- Jobs focused frozen tests: **10/10 PASS**.
- Assistant pre-hire parity: **PASS**.
- dashboard full suite, including offer confirmations: **74/74 PASS** across **19/19 files**.
- dashboard TypeScript/Vite production build: **PASS**.
- frozen shared Python modules compile: **PASS**.

Environment-only harness note:

- DB-backed Assessment pagination, full canonical-lifecycle, Assistant HR-read, and final registry fixture harnesses require the repository’s pre-existing full application baseline schema.
- The isolated local PostgreSQL service had no such baseline. Attempts stopped before their product assertions with missing environment/base-table errors.
- They did not expose a remediation defect and were not pointed at staging or production.
- Their corresponding source modules were not changed; dashboard/unit/compile authority checks are green.
- These DB-backed matrices remain mandatory staging gates and must not be represented as locally executed.

## Local cleanup

- focused proof used a unique PostgreSQL schema and dropped it;
- integration-audit proof deleted its outbound row;
- isolated regression database `wathefni_offers_regression` was dropped;
- temporary DB environment file was deleted;
- PDF fixtures used a temporary directory and were removed;
- no provider send occurred;
- no staging or production row/file/message was created.

## Residuals

Contained residuals:

1. Arabic generation remains intentionally unsupported. Validated company-uploaded PDF is mandatory.
2. Unknown provider outcomes require human review because the current provider does not expose a trusted idempotency/reconciliation API.
3. The expiry worker exists but is not installed; installation belongs to staging deployment approval.
4. Old staging/owner proof scripts expect returned raw tokens. They must be migrated to test-only token derivation or a test-only fixture hook before staging; production APIs must not restore raw-token responses.
5. Existing synthetic cleanup scripts that directly delete version/event rows must use parent deletion or the explicit retention session flag.
6. No audited supersede operation exists; multiple accepted offers remain prohibited.
7. DB-backed frozen integration matrices require the full isolated staging schema and remain staging gates.

## Kuwait/GCC fields still too generic

The contained offer record is now country/legal-entity/version aware. Broader downstream models remain too generic for a full country-pack claim:

- canonical employee creation copies only name, phone, email, position, company, and application link;
- employee creation does not explicitly copy employment country, employing legal entity, offer currency, accepted offer/version, policy version, or governing effective date;
- onboarding seeding is company-template based, not country-pack/effective-date based;
- compliance-document seeding is not proven to select by employment country/legal entity;
- employee keys are company/phone based rather than legal-employer scoped;
- probation and compensation are not established here as governed employee-record fields;
- authorized signatory authority does not flow into onboarding/employee records;
- end-of-service, leave, notice, visa/work-permit, social-insurance, payroll, and statutory-document rules are outside this remediation.

These are inputs to a separate Kuwait/GCC country-pack assessment. They do not justify expanding this contained patch.

## Staging qualification plan

Do not deploy until owner approval.

For isolated staging:

1. build one artifact from the exact contained source digest;
2. verify only the listed files are included;
3. back up and validate the staging database;
4. apply schema idempotently and inspect all constraints/indexes/triggers;
5. configure a staging-only offer token secret;
6. configure one synthetic company’s document defaults for a specific country/legal entity;
7. install the expiry worker in staging only;
8. keep delivery dry-run for the first matrix;
9. run permission redaction and PDF-route probes for viewer/authorized roles;
10. run English generated and Arabic approved-upload document checks;
11. run concurrent send and same-key replay;
12. run known provider failure, unknown outcome, and DB-finalization failure injection;
13. run live isolated one-message send only after dry-run gates;
14. run resend and prove old-link revocation;
15. expire the offer and prove replacement draft creation;
16. run public XSS/CSP probes;
17. run canonical dashboard, registry, mobile, and Assistant hire-path checks;
18. run atomic one-employee and override success/failure outcome checks;
19. run all frozen production-green module matrices;
20. update legacy offer proof harnesses so they never depend on production raw-token responses;
21. clean all DB rows, files, audit artifacts, and provider messages;
22. prove zero residue;
23. stop for owner approval before production.

## Final status

The confirmed blockers have one contained local remediation with green focused proof and green executable frozen unit suites.

The module is **not deployed**, **not staging-green**, and **not production-green** from this work.

Stop here.
