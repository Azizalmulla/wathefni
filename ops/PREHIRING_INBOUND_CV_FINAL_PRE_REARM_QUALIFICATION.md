# Pre-Hiring Inbound CV — Final Pre-Rearm Qualification

Date: 2026-07-26  
Production evidence stamp: `20260726T145921Z`  
Scope: final narrow closure for one owner-operated `WATHEFNI` automatic email canary  
Production posture during this phase: **dark; no email sent; no new worker or timer started**

## Verdict

**GO — for one bounded, owner-operated `WATHEFNI` automatic email canary only.**

This is not approval for general rearm, Gmail synchronization, external tenants,
historical backfill, sender acknowledgment, generic classification workers, Job
binding, ranking, outreach, or lifecycle progression.

All authority relevant to this inbound canary is green:

- retention policy is explicit, versioned, tenant-scoped, active, and readable;
- cleanup remained dry-run and selected exactly the eligible qualification objects;
- legal hold and open-review objects were not eligible;
- the existing pre-hire CV timer now fails closed for legacy inbound-email documents
  and requires durable scan, identity, and ownership authority for governed documents;
- invalidated classification runs contribute zero effective suggestions, chips,
  filters, or current profile classification while remaining auditable;
- Noor remains held and isolated; Esraa's July CV remains current;
- inbound, scan, identity, mailbox, classification, communication, tenant,
  permissions, Candidates C0-C3, dashboard, and canonical lifecycle authority passed;
- production health and dashboard return `200`;
- automatic paths remain OFF and synthetic residue is zero.

## Exact artifact identity

Local Git baseline: `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

The closure is represented by exact file hashes because the working tree contains
accepted uncommitted production-authority work.

| Runtime artifact | SHA-256 |
|---|---|
| `/opt/wathefni/orchestrator/app.py` | `b4a9a4b032abee27e75ec6b4fc382b0797889a935af4d6529af29bf6574a7dd5` |
| `inbound_retention_policy.py` | `63a7a1fa699ff6d644bc28916f012010957c05b4cb3f40a8eac3ae275c52011d` |
| `talent_pool_classification.py` | `f3869c101b80138c954df02498a4698ee85156fd7f6f3e606b0b436419d77c77` |
| `talent_pool_classification_routes.py` | `ff81a2134eba77c96691212cf46f21c484ed9ab671dc52ae1df943d27676168a` |
| `CandidateClassificationSection.tsx` | `7bdbe9932588915cf656a387078a9fe0fcffea910d26781283a16d09efcf2383` |
| Live dashboard JS | `8974aab5934058bae961b722f1a681e642c2143f9759cc4f316cf6b86a80f1b7` |

Runtime composite SHA-256:
`7cdb2c4de06b92f5da9a1a25c17c6ce2b278267780e1f6f82777c638eecfe9ce`.

Backup and rollback:

- backup: `/opt/wathefni/backups/production-pre-final-pre-rearm-20260726T145921Z`;
- database dump: `db.dump` with a validated `pg_restore -l` manifest;
- rollback: `ROLLBACK.sh`;
- prior backend, env, drop-in, dashboard source, mirror dist, and live dist are preserved;
- additive policy/audit schema and existing correction records are not destructively
  rolled back.

## Active retention policy

Tenant: `WATHEFNI`  
Stable policy version: `inbound-retention-ops-v1`  
Assignment actor: `wathefni-final-pre-rearm-qualification`

| Object or authority | Active value |
|---|---|
| Clean quarantine object | 30 days |
| Malware-detected or scan-failed object | 90 days |
| Open identity review | Retain while open |
| Resolved identity review | 90 days after resolution |
| Withdrawn/deleted held-candidate source | 90-day recovery period |
| Scan and identity audit | 7 years |
| Identity correction and classification invalidation audit | 7 years |
| Clean scan reuse | 168 hours |
| Orphan grace | 86,400 seconds |
| Legal hold | Suspends deletion |
| Cleanup scheduler | OFF |

Configuration is explicit in
`/root/.openclaw/secrets/wathefni-intake.env`; the active tenant assignment is
readable in `inbound_retention_policy_assignments` joined to
`inbound_retention_policies`. A missing tenant assignment or any unset, malformed,
non-positive, or invalid versioned value raises a fail-closed retention error.

Tenant scoping is enforced by `(company_code, policy_version)` definitions and one
active assignment per company. Qualification proved an unconfigured tenant cannot
obtain a fallback policy.

Policy definitions are append-only by version. Changing a value requires a new
policy version; attempting to reuse the same version with different values is
rejected.

### Legal hold, deletion audit, and source/audit separation

- Legal holds may scope to an intake document or content hash.
- Active holds override every age/state rule.
- An open identity review overrides every age/state rule.
- Withdrawn/deleted recovery applies only to held application states with no Job
  position; other withdrawn sources fail closed.
- Source-object cleanup updates storage state but does not delete intake,
  scan, identity, correction, or invalidation ledgers.
- Each executed deletion records company, intake document, content SHA-256,
  quarantine reference, reason, actor, policy version, object-delete result, and
  database timestamp.
- The unique `(company_code, intake_document_id, policy_version)` ledger and
  already-deleted storage state make cleanup idempotent.
- The deletion ledger is append-only.

## Dry-run cleanup proof

The production qualifier created six isolated metadata-only source records, selected
against the production policy, and removed all synthetic database rows afterward.
No quarantine file was created and no delete operation was executed.

| Qualification case | Expected | Result |
|---|---|---|
| Clean, 31 days old | eligible | selected |
| Clean, 29 days old | blocked | blocked |
| Non-clean, 100 days old, legal hold | blocked | blocked by legal hold |
| Non-clean, 100 days old, open review | blocked | blocked by open review |
| Scan-failed, 91 days old | eligible | selected |
| Resolved review, 91 days after resolution | eligible | selected |

Proof:

- exact expected eligible set: `3/3`;
- synthetic deletion-ledger rows after dry-run: `0`;
- all six synthetic objects still had `storage_status='stored'` before cleanup of
  fixtures;
- open-review blocked count was `2` because the real held Noor review was also
  correctly visible and protected;
- legal-hold blocked count: `1`;
- final synthetic residue: `0`.

Evidence:
`/opt/wathefni/production-evidence/final-pre-rearm/20260726T145921Z/final-pre-rearm-qualification.json`.

## Existing pre-hire CV timer decision

Decision: **keep the existing timer enabled; inbound-email documents are now
explicitly gated and fail closed.**

`wathefni-prehire-cv-process.timer` remains the existing one-minute timer and invokes:

`POST /orchestrator/prehire/cv/process?dry_run=false&limit=10&force=false&send_screening=true`

The endpoint itself forces candidate screening delivery OFF.

The candidate-document loader now resolves both:

1. the linked `intake_documents` authority row; and
2. the originating `import_batches.source`.

If a document is linked to durable intake, carries governed identity provenance, or
originated from `email`/`email_inbound`, processing occurs only when:

- an intake document ID is present;
- an identity resolution ID is present;
- the latest durable scan is `clean` for the exact content hash and scan policy;
- identity outcome is accepted;
- `ownership_confirmed=true`;
- candidate and application binding match the resolution.

Legacy inbound-email rows without the new authority return
`inbound_email_authority_provenance_missing` before lease acquisition or extraction.
The retained Noor document was used as the production-dark probe and returned that
exact error. It did not extract, become current, classify, rank, progress, or send.

This closes the prior bypass risk without creating another processing path.

Timer evidence:
`/opt/wathefni/production-evidence/final-pre-rearm/20260726T145921Z/prehire-timer-proof.txt`.

## Native classification invalidation

`candidate_classification_run_invalidations` is now authoritative in:

- latest/current run selection;
- bulk Candidates row projections;
- classification chips;
- classification node filters and confidence filters;
- unclassified filters;
- profile current-classification selection;
- automatic/current suggestion selection;
- search evidence derived from effective suggestions.

Every effective suggestion query excludes a run with a matching tenant-scoped
invalidation. Immutable run and suggestion rows remain available as audit history.
Profile history marks the run `invalidated` and returns reason, actor, and timestamp;
the live dashboard renders those fields.

### Active-suggestion invalidation proof

An isolated synthetic run was deliberately given one `active`, High-confidence
suggestion and then invalidated.

| Projection | Result |
|---|---|
| Current run | `null` |
| Effective AI suggestions | `0` |
| Row chip | `null` |
| Invalidation count | `1` |
| Immutable suggestions retained for audit | `1` |

### Noor/Esraa proof

Invalid run: `a48f3779-3abc-41fb-bec1-92c36ff24587`

- effective AI suggestions: `0`;
- current classification run: `null`;
- chip: `null`;
- active suggestions from invalid run: `0`;
- original run remains present;
- invalidation reason: `identity_misbinding`;
- actor: `wathefni-orchestrator-production-dark-correction`;
- invalidated at: `2026-07-26T14:32:12.749931+00:00`;
- historical reject events preserved: `17`.

The live dashboard source and built bundle both contain the invalidation reason,
actor, and timestamp display. `https://api.wathefni.ai/dashboard/` returns `200`.

## Noor and Esraa final state

| Authority | Final state |
|---|---|
| Esraa current CV | July document `71a889fd-7e45-4825-bd2e-da15d00888ba`, `latest=true` |
| Noor document | `5608a4ef-87d2-49d8-9c7a-9ec5666a92ef`, `latest=false` |
| Noor identity | one open `held_new_candidate_pending_clean_scan` review |
| Noor scan | historical authority remains unavailable/non-clean; fail closed |
| Noor Job binding | none |
| Lifecycle events | `0` |
| Ranking evaluations | `0` |
| Outbound events | `0` |
| Interviews/hiring | `0` |
| Active intake jobs | `0` |
| Active classification jobs | `0` |

No historical OCR was run to manufacture missing evidence.

## Relevant authority matrices

| Pack | Result | Notes |
|---|---|---|
| Final retention/timer/invalidation qualifier | PASS | exact selection; zero residue |
| Final closure + classification units | PASS | 25 tests |
| Inbound email durable smoke | PASS | durable intake and cleanup |
| Mailbox sync smoke | PASS | fail closed |
| Gmail mailbox smoke | PASS | fail closed |
| Scan/quarantine/identity authority | PASS | full matrix |
| Unified Candidates | PASS | frozen pack |
| Classification | PASS | native invalidation included |
| Held communication authority | PASS | no sender acknowledgment/outreach |
| Candidates C0/C1 production matrix | PASS | authority path |
| Candidates C0/C1 integration authority | PASS | 5 tests |
| Candidates C2 units + production matrix | PASS | authority path |
| Candidates C3 units + production matrix | PASS | authority path |
| Optional module/tenant/permission boundary | PASS | WhatsApp env supplied to harness |
| Canonical recruiting lifecycle | PASS | no inbound authority mutation |
| Dashboard | PASS | 60 tests, TypeScript clean, live HTTP 200 |

There is no failure in an authority relevant to inbound automatic CV intake.

## Residual regression disposition

Each pre-existing gap has one disposition:

| Gap | Disposition | Basis |
|---|---|---|
| C0/C1 registry source-contract mismatch | **harness-only** | Production C0/C1 matrix and five authority integration tests pass. One source assertion still expects `create_candidate_interview_from_schedule` in `action_registry.py`; it does not exercise inbound, scan, identity, classification, tenant, or communication authority. |
| Offers dashboard source unavailable on dist-only host | **harness-only** | Offers source test cannot run from the production artifact layout; dashboard authority is tested locally and the live bundle is healthy. No Offers behavior changed. |
| Optional-module test missing WhatsApp export | **fixed** | The qualification process supplied `WATHEFNI_APPLY_WHATSAPP_NUMBER`; the optional boundary matrix passed without weakening production. |
| Ranking external provider HTTP 429 | **environmental** | Provider rate limiting is external and unrelated; inbound canary has no Job and invokes no ranking. |
| Quarantined mobile lifecycle harness | **harness-only** | The quarantined fixture-write harness is not production authority. Canonical recruiting lifecycle authority passed and no lifecycle behavior changed. |

An additional legacy production lifecycle smoke was run only with a process-local
feature flag. Its 17 safety assertions passed and four stale assertions expected
direct transitions where production now correctly requires confirmation. It cleaned
all fixtures and is classified harness-only; the canonical lifecycle pack is green.

## Exact production leave-state

| Control | State |
|---|---|
| Orchestrator health | `200`, service active |
| Dashboard | `200` |
| Automatic inbound enqueue | OFF |
| Bounded inbound worker service | inactive |
| Bounded inbound timer | inactive/not installed |
| Gmail/mailbox live synchronization | OFF by default; no Gmail/mailbox unit |
| Generic classification workers | OFF |
| Automatic email classification | OFF |
| Automatic classification tenant allowlist | empty |
| Sender acknowledgment | OFF |
| Retention cleanup worker/timer | OFF/not installed |
| Historical backfill | not running |
| External inbound tenants | none; one active recipient, `WATHEFNI` only |
| Existing pre-hire CV timer | active/enabled, now authority-gated |
| Synthetic residue | `0` |
| Post-deploy journal errors | `0` |

Exact active production recipient:
`92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`
(`WATHEFNI`, intake ID `2493b577-09e3-45c2-b923-b0c382c251df`).

## Final canary posture — prepared, not executed

The authorized future canary is one owner-operated test with:

- only the exact production recipient above;
- tenant allowlist exactly `WATHEFNI`;
- an explicit UTC canary start timestamp;
- durable intake worker `limit=1`;
- `WATHEFNI_INTAKE_TENANT_CONCURRENCY=1`;
- automatic classification worker `--limit 1`;
- no historical jobs before the canary start;
- no Gmail/mailbox live sync;
- no external tenant;
- sender acknowledgment OFF;
- held Talent Pool only, with no position/Job;
- classification only after durable clean scan, safe identity, confirmed ownership,
  canonical extraction, current immutable evidence/facts, and exact recipient/start
  checks;
- immediate flag disable and worker stop controls.

## Exact rearm sequence if owner authorizes the canary

Do not execute this sequence without a separate owner instruction.

1. Verify the runtime composite SHA above, health `200`, active policy version,
   one active `WATHEFNI` recipient, zero active intake/classification jobs, and zero
   external recipient rows.
2. Record an exact UTC `CANARY_STARTED_AT`; snapshot database counters and the
   canary recipient queue.
3. Set only:
   - `WATHEFNI_INBOUND_EMAIL=on`;
   - `WATHEFNI_INTAKE_TENANT_CONCURRENCY=1`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=on`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=WATHEFNI`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_STARTED_AT=<CANARY_STARTED_AT>`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_RECIPIENT=92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_MAX_ATTEMPTS=1`.
4. Explicitly keep mailbox sync, generic classification workers, sender
   acknowledgment, retention cleanup, external tenants, and backfill OFF; restart
   only the orchestrator and recheck health.
5. Start a time-bounded owner-controlled intake runner that invokes
   `/orchestrator/debug/intake-worker/run?limit=1` with the internal token. It must
   terminate after one job per invocation and have a short absolute runtime limit.
6. Send exactly one owner test email to the exact recipient.
7. Process the resulting durable queue one job at a time. Stop immediately on any
   non-clean scan, unsafe identity, missing ownership, wrong tenant/recipient,
   duplicate anomaly, or unexpected mutation.
8. After canonical extraction creates the bounded classification job, run:
   `talent_pool_auto_email_classification.py --limit 1`.
9. Verify held Talent Pool state, no Job/lifecycle/ranking/outbound/hiring mutation,
   no acknowledgment, exact document/scan/identity/classification audit, and no
   unrelated queue claims.
10. Disable immediately after the one test, even if successful.

## Exact rollback/disable sequence

The first response is a kill-switch rollback, not destructive data rollback:

1. Stop the owner-controlled intake and classification runners.
2. Set:
   - `WATHEFNI_INBOUND_EMAIL=off`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=off`;
   - `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=`.
3. Keep sender acknowledgment, mailbox sync, generic workers, cleanup, and backfill
   OFF; restart the orchestrator and require health `200`.
4. Mark any unclaimed canary-start jobs `cancelled` through governed queue authority;
   preserve all intake, scan, identity, extraction, classification, and cancellation
   audit records.
5. Confirm the bounded worker/timer is inactive, active queue counts are zero, and
   protected mutation counts remain unchanged.
6. Only if the closure runtime itself is defective, execute:
   `/opt/wathefni/backups/production-pre-final-pre-rearm-20260726T145921Z/ROLLBACK.sh`.
   This restores prior runtime/env/dashboard bytes while keeping automatic paths OFF.

## Evidence index

Evidence root:
`/opt/wathefni/production-evidence/final-pre-rearm/20260726T145921Z`

Key files:

- `final-pre-rearm-qualification.json`
- `final-service-posture.json`
- `final-db-posture.txt`
- `prehire-timer-proof.txt`
- `dashboard-content-proof.json`
- `runtime-manifest.json`
- `deployed.sha256`
- `rollback.sha256`
- `orchestrator-journal.txt`
- `regressions/`

## Stop state

The final bounded canary is prepared but **not executed**. Automation remains OFF.
No worker or timer was started, no email was sent, and no next product phase began.
