# Pre-Hiring Inbound CV Scan + Identity — Production-Dark Promotion and Noor/Esraa Correction

Date: 2026-07-26 (UTC stamp `20260726T142301Z`)  
Scope: exact production-dark promotion of staging-qualified durable scan and candidate-identity authority; governed Noor/Esraa correction; dark proofs; rollback proof  
Automation: **OFF throughout — not rearmed**

## Verdict

**Production-dark authority: GO (deployed, corrected, requalified, left dark).**

**Bounded owner-operated `WATHEFNI` automatic email canary: NO-GO.**

Do not rearm automatic inbound enqueue, bounded worker/timer, Gmail/mailbox sync,
or classification workers. Broader quarantine/audit retention SLA remains unset
(blocker for automation). Residual unrelated frozen-matrix gaps remain (offers
dashboard source on host, optional-boundary WhatsApp env gate, Ranking Terra 429).

Evidence root:

`/opt/wathefni/production-evidence/inbound-cv-authority-dark/20260726T142301Z`

---

## Phase A — exact production-dark promotion

### Source revision

Staging-qualified remediation source:

`40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

Production was patched in place with
`ops/patch-production-app-inbound-cv-authority.py` because production lacked
durable-ingress anchors required by the staging patcher.

### Runtime changed-file allowlist

| File | SHA-256 |
|---|---|
| `app.py` (patched production) | `be3811e2e4353deb64ec4bac6db40f97a8b668d8b2bdda99eac15a55dcf8bc32` |
| `durable_email_ingress.py` | `0257f8fb4ebc5bc70e33b2775ae7338f1a06b67f1cdceea18042365f54d0ab66` |
| `inbound_cv_authority.py` | `8e1b843f211c73a2c917e514d9caa9da05b52a5d96eda6d31e2bcb57d5affd92` |
| `intake_malware_scanner.py` | `25022b8c0eaf84f10ce1a1aeee1bd61d17a316aa722479ae224c5feefc340c70` |
| `intake_quarantine_storage.py` | `96f914e36d5e50b60eccd1988d3d5cde8e11604f0b525f1f064793c65ab9000e` |

Module hashes match staging-qualified authority bytes. Staging harness / synthetic
fixture code was **not** promoted into runtime.

### Final composite SHA

`f162db5b94dc7dac309f5ed5a8645d201c5c1657abb2cf784789e25096c18145`

(SHA-256 over the five runtime file digests above, concatenated in allowlist order.)

### Pre-promotion runtime

| Item | Value |
|---|---|
| Pre `app.py` | `eb49fbb9a40349812293e57f1e9c660e51641034b15af097e1b91c6d37f90acb` |
| Legacy behavior | Postmark sync used sender email as identity meta |

### Database migration identity

Additive authority/intake schema applied before app cutover. Tables present:

- `inbound_attachment_scan_decisions`
- `inbound_cv_identity_extractions`
- `inbound_cv_identity_resolutions`
- `inbound_cv_identity_reviews`
- `inbound_cv_identity_events`
- `candidate_identity_keys`
- `candidate_classification_run_invalidations`
- `intake_addresses`, `intake_submissions`, `intake_documents`
- `intake_processing_jobs`, `intake_processing_job_events`
- `intake_quota_usage`, `intake_tenant_queue_state`

Evidence: `migration-pre-app.json` (`ok: true`).

### Configuration manifest (dark)

Exact configured values:

| Key | Value |
|---|---|
| `WATHEFNI_INBOUND_EMAIL` | `off` (intake.env, postgres.env, systemd drop-in) |
| `WATHEFNI_SENDER_ACKNOWLEDGMENT` | `off` |
| `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION` | `off` |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS` | `off` |
| `WATHEFNI_INTAKE_QUARANTINE_BACKEND` | `local_volume` |
| `WATHEFNI_INTAKE_QUARANTINE_DIR` | `/opt/wathefni/quarantine/email-intake` |
| `WATHEFNI_INTAKE_MALWARE_SCANNER` | `clamav` |
| `WATHEFNI_INTAKE_CLAMD_HOST/PORT` | `127.0.0.1:3311` |
| `WATHEFNI_INTAKE_SCAN_REUSE_HOURS` | `168` |
| `WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS` | `86400` |
| `WATHEFNI_INTAKE_SERVICE_IDENTITY` | `wathefni-orchestrator-production` |
| Intake quotas (daily/monthly message, bytes, jobs) | `0` (fail-closed for automation volume) |

Drop-in:

`/etc/systemd/system/wathefni-orchestrator.service.d/durable-email-ingress.conf`

### Production backup + rollback artifact

| Item | Path / value |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-inbound-cv-authority-dark-20260726T142301Z` |
| DB dump SHA | `f69b376f8fa2a3534fe29a635f2bdf6c62648b40984cc3a8a5a1633ea373232d` |
| Pre `app.py` SHA | `eb49fbb9a40349812293e57f1e9c660e51641034b15af097e1b91c6d37f90acb` |
| Rollback | `bash /opt/wathefni/backups/production-pre-inbound-cv-authority-dark-20260726T142301Z/ROLLBACK.sh` |

---

## Phase B — production infrastructure dark validation

### Quarantine

| Check | Result |
|---|---|
| Path exists | `/opt/wathefni/quarantine/email-intake` |
| Backend | LUKS mapper `wathefni-production-email-quarantine` mounted ext4 |
| Mode | `0700` (`drwx------ root root`) |
| Mount service | `wathefni-production-email-quarantine.service` active/exited |
| Tenant boundary | write under `QPRODA/...` does not create sibling under `QPRODB/...` |
| Hash preserved | SHA-256 of written bytes matches content digest in object key |
| Canonical escape | infected/failed paths remain quarantine-scoped; no promotion without durable `clean` |

### ClamAV

| Check | Result |
|---|---|
| Service | Docker `wathefni-production-clamav` healthy on `127.0.0.1:3311` |
| Version recorded | `ClamAV 1.5.3/28073/Sun Jul 26 06:25:14 2026` |
| Freshness | signature daily `28073` dated 2026-07-26 (within same-day policy) |
| Clean | durable `clean` |
| Infected (EICAR in `/tmp` only) | durable `malware` / `malware_detected` |
| Timeout / unavailable / malformed / missing | authority matrix → non-`clean` → fail closed (`scan_failed`) |
| Policy | anything other than durable `clean` fails closed |

EICAR used only under isolated `/tmp/prod-dark-clam-*`; not placed in candidate storage.

### Service identity

Runtime process:

`root` / uid `0` / uvicorn `app:app` on `127.0.0.1:8010`

Configured authority actor:

`wathefni-orchestrator-production`

Roles covered by that service identity (no additional OS users introduced):

- inbound webhook
- quarantine write
- scanner access
- extraction
- identity resolution
- classification enqueue (gated; workers OFF)

No broader filesystem/database privilege expansion was added beyond the LUKS
quarantine mount and ClamAV localhost port.

### Retention (exact; no invention)

Configured:

- `WATHEFNI_INTAKE_SCAN_REUSE_HOURS=168`
- `WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS=86400`

**Unset (blocker for automation):**

- quarantine retention days/years
- scan/identity/audit retention SLA
- candidate-document retention for held identity-review objects

Automation remains OFF because these production retention values are not set.

### Durable journey-evidence fields proven

Authority matrix + correction records include:

- inbound ID
- attachment/document ID
- content hash
- scan engine / signature version (when scanner ran)
- scan timestamps and result
- quarantine object reference
- identity-resolution decision + evidence/reason codes
- selected provisional app key or held review
- conflict/review state
- actor/service identity

---

## Phase C — governed Noor/Esraa correction

Actor: `wathefni-orchestrator-production-dark-correction`  
Script: `ops/correct-production-noor-esraa-identity.py`  
Proof: `noor-esraa-before.json`, `noor-esraa-after.json`, `noor-esraa-correction-proof.json`, `classification-exclusion-proof.json`

### Before

| Subject | State |
|---|---|
| Esraa app | `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT` |
| Current CV | Noor Tahat PDF `5608a4ef-87d2-49d8-9c7a-9ec5666a92ef` (`latest=true`) |
| Misbound classification run | `a48f3779-3abc-41fb-bec1-92c36ff24587` (`classified_multi`, 17 active suggestions) |

### After — Esraa

| Requirement | Result |
|---|---|
| Restore legitimate latest CV | July `71a889fd-7e45-4825-bd2e-da15d00888ba` (`latest=true`, SHA `b137161b…`) |
| Preserve June + July sources | June `d47f6c3f-…` kept (`latest=false`, historical) |
| Preserve June text limitation | no historical OCR manufactured |
| Noor no longer current for Esraa | Noor doc `latest=false`, `invalidated_identity_misbinding=true` |
| July text/evidence/facts current | all `is_current=true` |

### After — Noor (held; fail-closed on missing historical clean scan)

| Requirement | Result |
|---|---|
| Separate provisional/held record | identity resolution `ba5050f9-…` outcome `new_candidate` with provisional key `imp-wathefni-b8653e5efe86bb2e-WATHEFNI-IMPORT` **not materialized** |
| Open identity review | `b03491a6-…` status `open`, type `held_new_candidate_pending_clean_scan` |
| Source in quarantine | `WATHEFNI/809f5c46-…/0001/d951c3e2….bin` hash-verified |
| Historical scan truth | decision `3ac16be2-…` state `scan_failed`, reason `historical_scan_authority_missing` (no manufactured clean) |
| No Job / outreach / lifecycle / ranking | protected counts unchanged (`lifecycle=0`, `ranking=0`, `outbound=0`) |
| No silent candidate mint | `noortahat3@gmail.com` candidate count `0` |

Document row remains under prior Esraa `app_key` with invalidation markers because
authority refuses current rebinding without durable clean scan. Held Noor path is
the intake identity resolution + open review + quarantine object, not a promoted
candidate application.

### Incorrect classification run

| Requirement | Result |
|---|---|
| Preserve original run | run `a48f3779-…` immutable; status unchanged |
| Invalidate for identity misbinding | `candidate_classification_run_invalidations` row; actor correction service |
| Exclude from Esraa effective classification | 17 append-only `reject` review events + suggestions marked `stale`; effective AI suggestions from that run = `0` |
| No silent rewrite of run | run row not mutated; invalidation + review events append-only |

---

## Phase D — dark authority proof

`qualify-inbound-cv-scan-identity-authority.py` on production DB with temp quarantine:

**passed=true**, zero synthetic residue.

| Proof | Result |
|---|---|
| Sender is provenance only | pass |
| Exact email/phone resolves within one tenant | `safe_exact_reuse` |
| Name-only / conflict cannot auto-merge | `possible_match` / `conflict` + reviews |
| Same sender, different candidates | distinct candidates kept |
| Gmail/mailbox cannot bypass authority | `durable_scan_and_identity_authority_required` |
| Missing scan evidence fails closed | pass |
| Document cannot become current before clean+safe identity | pass |
| Classification cannot enqueue before gates | `unsafe_downstream_jobs=0` |
| Noor-like input cannot attach to Esraa | conflict isolation |
| Duplicate resend idempotent | pass |
| Cross-tenant matches fail closed | pass |
| No Job/lifecycle/ranking/outbound/hiring/intake-admit mutation | protected deltas zero |

Infra dark proof (`infra-dark-proof.json`): quarantine, ClamAV clean+EICAR,
mailbox fail-closed, retention asserts, inbound OFF — **ok=true**.

---

## Frozen regressions

### Authority / inbound / mailbox (required green)

| Pack | Result |
|---|---|
| Durable inbound email smoke (qualified) | PASS |
| Mailbox sync fail-closed smoke | PASS |
| Gmail/mailbox smoke | PASS |
| Authority matrix | PASS |
| Classification units | PASS |
| Held communication authority | PASS |
| Unified Candidates units | PASS |
| Candidates C0/C1 authority classes (excl. pre-existing registry contract) | PASS |
| Candidates C2 units | PASS |
| Candidates C3 units + contracts | PASS |
| Candidates C01 production matrix | PASS |
| Candidates C2 production matrix | PASS |
| Candidates C3 production matrix | PASS |
| Interviews production matrix | PASS |
| Assessments on/off production matrix | PASS |
| Ranking result presentation matrix | PASS |
| Reports v1 matrix | PASS |
| Assistant A0–A3 matrix | PASS |
| Assistant Jobs/Ranking UX matrix | PASS |
| Dashboard Vitest (local repo; host is dist-only) | **13 files / 60 tests PASS** |
| HR mobile `tsc --noEmit` (local) | PASS |
| Synthetic cleanup / zero residue (authority) | PASS |

### Residual non-authority gaps (do not rearm)

| Pack | Result | Notes |
|---|---|---|
| Full `test_candidates_c01` incl. source-contract | 11/12; 1 FAIL | Pre-existing: `create_candidate_interview_from_schedule` absent in prod+staging `action_registry.py` (unrelated to this promote) |
| Offers/Hiring production matrix | 37/38; 1 FAIL | `dashboard_confirmations_present` — dashboard source panel not on host dist tree |
| Optional-module boundary matrix | REFUSE | needs `WATHEFNI_APPLY_WHATSAPP_NUMBER` in matrix env (value exists in systemd; not exported to harness) |
| Ranking R0–R3 matrix | FAIL on Terra live | `HTTP 429 Too Many Requests` (environmental); forced-failure preservation still PASS |
| Mobile lifecycle production proof | quarantined harness | pre-existing lifecycle fixture write block |

No unintended production residue from authority synthetic tenants (`INBOUND*`,
`AUTHORITYQ*`, mailbox smoke companies cleaned).

---

## Rollback proof

Executed `ROLLBACK.sh` then redeployed the exact dark artifact.

| Step | Evidence |
|---|---|
| Restore previous runtime `app.py` | `eb49fbb9…` |
| Remove authority modules + drop-in | confirmed |
| Keep automation OFF via env files | `WATHEFNI_INBOUND_EMAIL=off` in postgres.env + intake.env |
| Health after rollback | `200` |
| Preserve additive schema | scan/identity/invalidation tables remain |
| Preserve Noor/Esraa correction | invalidation count `1`; July `latest=true`; Noor `latest=false` |
| Redeploy dark artifact hashes | match allowlist exactly; composite `f162db5b…` |
| Health after redeploy | `200` |
| Infra requalify | `ok=true`, inbound still `off` |
| Authority requalify | `passed=true`, zero residue |

Rollback evidence: `…/20260726T142301Z/rollback/proof-summary.json`

---

## Gmail / mailbox fail-closed proof

- Legacy `_import_process_one_file(..., meta={"email": ...})` → `durable_scan_and_identity_authority_required`
- Live `run_mailbox_sync` → same error; no import batch; cursor unchanged
- Qualified mailbox + Gmail smokes: PASS
- Runtime inbound email remains OFF; no provider email sent during this engagement

---

## Final leave-state

| Control | State |
|---|---|
| Orchestrator | active, health `200` |
| Dark artifact | composite `f162db5b…` deployed |
| Automatic inbound enqueue | OFF |
| Tenant allowlist / external tenants | none enabled |
| Bounded inbound worker/timer | not-found / inactive / disabled |
| Generic classification workers | OFF |
| Auto email classification | OFF |
| Sender acknowledgment | OFF |
| Gmail/mailbox sync live mutation | fail-closed |
| Historical backfill | not run |
| Pre-existing `wathefni-prehire-cv-process.timer` | still active (non-email CV processor; not inbound enqueue) |
| Classification UI / manual review | available for internal `WATHEFNI`; automatic classification not executing |
| Esraa current CV | July restored |
| Noor | held pending durable clean scan; not current on Esraa |

---

## Unresolved risks

1. **Retention SLA incomplete** — only scan-reuse `168h` and orphan-grace `86400s` are set; quarantine/audit retention unset → **automation blocker**.
2. **Noor historical scan** — retained as `scan_failed` / `historical_scan_authority_missing`; cannot become current or mint candidate without a future governed clean-scan admit.
3. **Noor document physical `app_key`** — still prior Esraa app with invalidation markers; held authority is intake/review/quarantine, not a promoted Noor application.
4. **Effective-classification filter** — exclusion uses append-only rejects + stale suggestions; `talent_pool_classification` does not yet read `candidate_classification_run_invalidations` natively (ledger exists; projection exclusion proven via review path).
5. **Unrelated frozen gaps** — offers dashboard source-on-host, optional-boundary env export, Ranking Terra 429, C01 registry contract drift.
6. **Pre-existing prehire CV timer** — still fires `/orchestrator/prehire/cv/process` every minute; not inbound email automation, but should be reviewed before any intake rearm.

---

## GO / NO-GO for bounded `WATHEFNI` automatic email canary

| Decision | Verdict |
|---|---|
| Leave production on dark scan/identity authority | **GO** |
| Start owner-operated bounded automatic email canary | **NO-GO** |

Required before any canary rearm (separate authorization):

1. Owner-approved quarantine + audit retention SLA values set explicitly.
2. Confirm prehire CV timer posture relative to intake dark invariants.
3. Clear residual unrelated matrix gaps or explicitly waive them.
4. Keep first rearm `WATHEFNI`-only, start-time bounded, worker/timer owner-operated, no Gmail live sync, no external tenants, no historical backfill.

**Stop. Automation remains OFF.**
