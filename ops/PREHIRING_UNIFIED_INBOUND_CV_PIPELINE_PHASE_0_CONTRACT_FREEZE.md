# Pre-hiring Unified Inbound CV Pipeline — Phase 0 Contract Freeze

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260726T232921Z`  
Scope: freeze and qualify current channel contracts before Phase 1  
Production mutations: **none**  
Phase 1 started: **no**

Prerequisite accepted: `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_ARCHITECTURE_REVIEW.md`

Local qualification artifacts:

- `wathefni-orchestrator/fixtures/unified_inbound_cv_phase0.py`
- `wathefni-orchestrator/test_unified_inbound_cv_phase0_contracts.py`
- Result: **40/40 PASS** (`.venv/bin/python -m unittest test_unified_inbound_cv_phase0_contracts.py`)

## Executive verdict

| Gate | Result |
|---|---|
| Current channel contracts frozen and reproducible offline | **PASS** |
| Deterministic scenario coverage for Phase 0 list | **PASS** |
| Three named current risks reproduced | **PASS** |
| Zero-downstream-mutation contracts for held/unbound records | **PASS** |
| Production behavior changed | **NO** (none) |
| Phase 1 additive intake envelope implementation | **not started** |

### GO / NO-GO for Phase 1

| Decision | Result |
|---|---|
| **Phase 1 additive generic intake-envelope implementation** | **GO — with blockers recorded below** |
| Big-bang channel cutover / production behavior change from Phase 0 | **NO-GO** |
| Treating current WhatsApp/manual paths as already unified | **NO-GO** |
| Using single-item Link-to-Job as a production promotion path before SQL fix | **NO-GO** |

Phase 1 may begin as an **additive, production-dark, email dual-write only** extraction of a generic intake envelope. It must not reroute WhatsApp or manual upload, must not change live email outcomes, and must carry the three documented risks as explicit Phase 1 entry constraints rather than silent assumptions.

## Frozen production posture (read-only)

Effective `wathefni-orchestrator` environment on host `76.13.63.68` at freeze:

```text
WATHEFNI_INBOUND_EMAIL=on
WATHEFNI_INTAKE_MALWARE_SCANNER=clamav
WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=on
WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=WATHEFNI
WATHEFNI_TALENT_POOL_CLASSIFICATION=on
WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=on
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=on
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=on
WATHEFNI_CANONICAL_LIFECYCLE=true
WATHEFNI_STAGE_B_ENABLED=1
WATHEFNI_STAGE_B_CANARY_ONLY=0
```

Workers:

| Unit | State |
|---|---|
| `wathefni-inbound-intake-worker.timer` | active / enabled |
| `wathefni-talent-pool-auto-email-classification.timer` | active / enabled |
| `wathefni-ck-index.service` | active / enabled |
| `wathefni-prehire-cv-process.timer` | inactive / disabled |

## Frozen local module fingerprints

| Module | SHA-256 |
|---|---|
| `app.py` | `eddf2ff6b6fb4230df096f79c591c0d58890c37d54cdb00b528f235e176f4270` |
| `durable_email_ingress.py` | `0257f8fb4ebc5bc70e33b2775ae7338f1a06b67f1cdceea18042365f54d0ab66` |
| `inbound_cv_authority.py` | `8e1b843f211c73a2c917e514d9caa9da05b52a5d96eda6d31e2bcb57d5affd92` |
| `jobs_phase2_stage_b.py` | `2dda3a101d8fe55b30d85e2d7bfc089740d8141b45be1f258de98f189c588479` |
| `candidate_knowledge_authority.py` | `73e02350e9ee1388683b43533aec8c711c4ab7f826a41be1e77bd290e69110a9` |
| `candidate_record_state_policy.py` | `e93b4580ecccbb0d53fabdde74b74367bdb8774e865a100af58d762be3405e89` |
| `candidate_communication_authority.py` | `8a3949eac6d72c7f18514810171298615e1fded40e81afba2ee91239305aab53` |
| `recruiting_lifecycle.py` | `dc7ead5774517cfb8513667aa874ee78f03a70e3179b28a79512d6eb452a8560` |
| `talent_pool_classification.py` | `f3869c101b80138c954df02498a4698ee85156fd7f6f3e606b0b436419d77c77` |
| `talent_pool_auto_email_classification.py` | `f1503ab5216e4977f8aa874cdedc00dc36d5259ad2ae083599425577e95a193e` |
| `unified_candidates.py` | `945feb810285e1ae14e78f68432cf7c64d00b506519b442fbbcd11f23f165421` |
| `candidate_identity.py` | `ce21ed97a55e54a24bf3f99d029d3e115c6d8c83c3888cc522d44b9ef3248b3a` |
| `candidate_ranking.py` | `f0e838d03d5dc1dc8180e3c7cb75a83558a490f596c8fc5986dbf93d95fdad65` |

These hashes are the Phase 0 baseline. Phase 1 dual-write work must keep email-observable outcomes byte-stable against this baseline unless a separately authorized remediation is approved.

## Exact current production behavior by channel

### Inbound email (reference authority)

```text
Postmark webhook
  -> durable quarantine + intake_submissions/documents/jobs
  -> intake_validation
  -> file_safety_scan (ClamAV + MIME/PDF/DOCX/image preflight)
  -> cv_identity_resolution (inbound_cv_authority)
  -> accepted_intake_preparation (register_imported_cv with identity_resolution)
  -> cv_extraction
  -> optional auto classification (WATHEFNI only)
  -> Candidate Knowledge index for held apps
```

Frozen contracts:

- supported extensions: `.pdf .docx .png .jpg .jpeg .webp`
- safety states include `unsupported_type`, `invalid_corrupt`, `password_protected`, `malware_suspicious`
- identity outcomes: `safe_exact_reuse`, `new_candidate`, `possible_match`, `conflict`
- accepted ownership outcomes only: `safe_exact_reuse`, `new_candidate`
- sender email is provenance only
- governed email never auto-admits; held statuses are `needs_role` / `import_review`
- malware/non-clean never reaches OCR/candidate ownership

### Unsolicited WhatsApp CV

```text
Octopus download
  -> whatsapp-turn claim
  -> handle_candidate_file_turn
  -> no Job/app binding
  -> hold_candidate_pending_media (2h local-path hold)
  -> cv_held_needs_role message
```

Frozen contracts:

- no candidate / application / Talent Pool row
- no `needs_role` application status
- no scan/identity/OCR
- not HR-visible in Talent Pool
- not Ranking-eligible

### Job-specific WhatsApp CV

```text
apply code / job context preview
  -> preview_sent_at
  -> convert_job_context_to_application(trigger=apply_confirm|qualifying_cv)
  -> register_candidate_cv_file on real phone-backed application
```

Frozen contracts:

- CV-then-apply-code does not itself consume the held CV into an application
- apply-code-then-CV can convert after preview via `qualifying_cv`
- Stage B is enabled with `WATHEFNI_STAGE_B_CANARY_ONLY=0`
- WhatsApp attach path bypasses inbound quarantine/identity authority

### Manual dashboard upload

```text
POST /dashboard/prehire/import/upload
  -> process_bulk_cv_import / _import_process_one_file
  -> register_imported_cv (surrogate phone, no inbound_cv_authority)
```

Frozen contracts:

- no ClamAV/quarantine
- surrogate identity `imp-{company}-{hash}`
- auto-admit formula:
  `auto_admitted = auto_admit AND position_code AND NOT governed_identity`
- `company_auto_admit_imports()` returns **True when setting unset**
- statuses:
  - auto-admit + explicit role → `review_pending`
  - explicit role + auto-admit off → `import_review`
  - no role → `needs_role`

### Person Registry

- additive C3 tables exist (`persons`, memberships, contacts, merge/privacy)
- inbound create path does **not** insert persons
- not the Phase 0 Talent Pool membership authority
- partial production adoption remains a Phase 1+ migration risk

### Candidate Knowledge

- refs remain `app:<app_key>`
- held Talent Pool apps are readable and indexed
- held actionability denies contact / lifecycle / Job Ranking
- sibling aggregation uses `_strictest_actionability` (AND across phone siblings)

### Talent Pool classification

- independent of Jobs, Ranking, outreach, and `intake_admit`
- auto-email classification live for WATHEFNI
- generic classification workers remain **off**

### Lifecycle and Ranking

- held statuses: `needs_role`, `import_review`, `import_archived`
- lifecycle transitions from held require `trigger="intake_admit"`
- communication authority blocks held records
- `production_application_predicate` excludes held statuses from Ranking/live pipeline
- Unified Candidates `link_to_job` remains stubbed (`enabled: false`)
- credible promotion path today: bulk Import assign/confirm + `intake_admit`

## Deterministic test results

Command:

```text
cd wathefni-orchestrator
.venv/bin/python -m unittest test_unified_inbound_cv_phase0_contracts.py -v
```

Result: **40 tests, 0 failures, 0 errors**.

| Coverage area | Tests | Result |
|---|---:|---|
| Scenario catalog / Phase 0 fixture pack | 1 | PASS |
| Held status / communication / lifecycle / Ranking predicates | 5 | PASS |
| Email unsupported / corrupt / password / MIME / malware boundary | 7 | PASS |
| Identity possible_match / conflict / reuse / new_candidate | 6 | PASS |
| WhatsApp CV-only / CV-then-apply / apply-then-CV | 3 | PASS |
| Manual auto-admit unset/false/true + governed email no-admit | 2 | PASS |
| Single-item vs bulk promotion parity + Link-to-Job stub | 3 | PASS |
| CK sibling over-denial + app-keyed refs | 3 | PASS |
| Duplicate/replay contracts | 3 | PASS |
| Person Registry / classification separation | 2 | PASS |
| Zero-downstream mutation + fingerprint | 3 | PASS |
| Channel divergence pins | 2 | PASS |

Scenarios covered by fixtures and assertions:

- CV only (WhatsApp unsolicited hold)
- CV then apply code
- apply code then CV
- identical and changed CV contracts (email replay/idempotency + sender-not-person)
- multiple files (email multi-attachment contract)
- unsupported, corrupt, password-protected, malicious boundaries
- duplicate/replay/concurrent submission contracts
- possible identity match and conflict
- mixed held and live sibling applications
- manual explicit-role imports with auto-admit unset / false / true
- single-item versus bulk Link-to-Job parity
- zero downstream mutations without verified Job binding

## Three current risks — reproduced

### 1. Single-item promotion SQL parameter and tenant-predicate defect

Authority: `app.py::dashboard_prehire_import_assign`

Reproduced by source AST/regex pin:

- `UPDATE applications ... WHERE app_key=%s` has **8** `%s` placeholders
- argument tuple has **9** values and ends with trailing `company`
- tenant predicate is missing from the UPDATE (`company_code=%s` absent)
- preceding SELECT is tenant-scoped; bulk path correctly uses
  `WHERE app_key=%s AND company_code=%s`

Phase 0 status: **current defect frozen**. Not fixed in this task.

Blocker for any Link-to-Job work: do not wire production promotion through the single-item endpoint until placeholders, args, and tenant predicate match and a Postgres parity test passes against the bulk path.

### 2. Manual explicit-role auto-admit default

Authority: `app.py::company_auto_admit_imports` + `register_imported_cv`

Reproduced matrix:

| Setting | Explicit role | Governed identity | Resulting status |
|---|---|---|---|
| unset (`None` → True) | yes | no | `review_pending` |
| false | yes | no | `import_review` |
| true | yes | no | `review_pending` |
| true | no | no | `needs_role` |
| true | yes | yes | `import_review` (email never auto-admits) |

Phase 0 status: **current contract frozen**. Not changed in this task.

Phase 1 constraint: unified-source admission must default held; preserve legacy manual default only behind an explicit compatibility path until owner approval.

### 3. Candidate Knowledge sibling over-denial

Authority: `candidate_knowledge_authority._strictest_actionability`

Reproduced with live+held siblings under one phone:

- live `ready_for_review` alone → Ranking/contact/lifecycle allowed
- held `needs_role` alone → all denied
- combined subject actionability → contact, lifecycle, and Job Ranking **all false**
- row-level Ranking SQL still excludes held statuses independently

Phase 0 status: **current contract frozen**. Not changed in this task.

Phase 1/6 constraint: person-level discovery may remain non-actionable, but exact `app:<app_key>` Job capabilities must not be AND-collapsed across held siblings.

## Blockers for Phase 1

These are entry constraints, not Phase 0 failures:

1. **Do not change live email outcomes** while extracting the generic envelope.
2. **Do not reroute WhatsApp or manual upload** in Phase 1.
3. **Do not enable** the disabled generic CV timer as a substitute for governed workers.
4. **Carry the three risks** into Phase 1 design notes and tests; do not “fix later.”
5. **Person Registry remains additive only**; do not make `persons` the inbound create authority yet.
6. **Candidate Knowledge remains `app:`-keyed** in Phase 1; person/subject refs are later phases.
7. **External tenants remain off** for CK/classification canaries unless separately authorized.
8. Single-item assign SQL defect remains open; Link-to-Job must not depend on it.

## What Phase 1 may do next

When separately authorized:

1. Add additive `intake_source_events` / `intake_items` / subject sidecars.
2. Extract `inbound_cv_intake.py` from durable email without changing Postmark ack or job outcomes.
3. Dual-write live email into the generic envelope.
4. Compare counts, checksums, route snapshots, jobs, identity outcomes, and artifact IDs.
5. Keep all readers and user-visible behavior on the current email path.

## What Phase 0 did not do

- no production code/config/flag/worker changes
- no Phase 1 schema or module extraction
- no WhatsApp/manual cutover
- no fix for the single-item SQL defect
- no change to auto-admit default
- no change to CK sibling actionability
- no Role Profiles / iOS / Android / post-hiring work

## Final Phase 0 verdict

**PASS / GO for Phase 1 additive generic intake-envelope work under the blockers above.**

Current behavior is now frozen by deterministic offline tests and production-read contract evidence. The three named risks are reproduced and must remain explicit until remediated under separate authorization.

**Stop.** Do not start Phase 1 in this task. Do not change production behavior from this report.
