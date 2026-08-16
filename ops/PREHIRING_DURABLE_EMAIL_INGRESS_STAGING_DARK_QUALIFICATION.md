# Pre-Hiring Durable Email Ingress — Staging Dark Qualification

**Status:** STAGING-DARK GREEN  
**Date:** 2026-07-25  
**Host:** `srv1419988` (`76.13.63.68`)  
**Backend:** `wathefni-orchestrator-staging.service` · `127.0.0.1:8011`  
**Database:** `wathefni_staging`  
**Evidence:** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-dark/20260725T123001Z`  
**Production:** untouched

## Verdict

**GO** for the next step: enable **one isolated staging intake address** while **intake workers remain stopped**, sender acknowledgment remains off, and no OCR/candidate/Talent Pool/outbound flows are started from inbound email.

**NO-GO** for starting intake workers, sending production mail, or promoting to production.

This phase deployed durable email-ingress code with inbound dark, qualified without Postmark email, preserved frozen authorities, proved rollback, and restored the deployed dark state.

---

## 1. Source and artifact SHA

| Item | Value |
|---|---|
| Source git commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Patched staging `app.py` SHA256 | `090e82b130cdd83558f5f908bdca7b37ba26ef553a2f9f29b33265dd77283cfb` |
| Modules bundle SHA256 | `a6231710257160762ad1301c7d6c1725919a23913f1c226f1ca3191be5c541ea` |
| Combined artifact SHA256 | `791db8d799e33777fae76249f1fe4383b5d1414c31b2f3678f2cbb1fd083405c` |
| Artifact file | `/opt/wathefni/staging/durable-email-ingress-dark-artifact.sha256` |
| Prior staging `app.py` (pre-deploy) | `b266a0d24ff49659fb8966b03818f32f2e12fc76cf659ea28514ad8a447d7602` |

Deployed files (surgical; Kuwait/foundation baseline preserved):

- `durable_email_ingress.py`
- `intake_quarantine_storage.py`
- `intake_malware_scanner.py`
- `durable-email-ingress-worker.py` (present, **not started**)
- surgically patched `app.py` (ingress hooks only; not local dirty full tree)
- updated `smoke-test-inbound-email.py`

---

## 2. Backup evidence

| Item | Value |
|---|---|
| Backup root | `/opt/wathefni/backups/staging-pre-durable-ingress-20260725T123001Z` |
| DB dump SHA256 | `8cdd048869c6f64280f5e789a9a563302c86e08cb59081f59d7a937d0e47debc` |
| Pre `app.py` snapshot | present (`app.py.pre`) |
| Rollback script | `BACKUP_ROOT/ROLLBACK.sh` |
| Quarantine backup run | `/opt/wathefni/staging/backups/email-quarantine/20260725T123017Z` |
| Quarantine archive SHA256 | `98cee0c7f479d2d2954d79fe421e49031d341245ca844096bb2446a5592f05c4` |
| Quarantine restore compare | `{compared: 1, matched: 1}` |

---

## 3. Migration evidence

Additive schema applied **while old code still running** (`health_after_pre_schema:200`).

Tables present after pre-schema:

- `intake_addresses` (pre-existing)
- `intake_submissions`
- `intake_documents`
- `intake_processing_jobs`
- `intake_processing_job_events`
- `intake_tenant_queue_state`
- `intake_quota_usage`

Scan evidence columns on `intake_documents`: `scan_engine`, `scan_signature_version`, `scanned_at`, `scan_result`, `scan_evidence`.

Post-migration counts (no work created by migration alone):

```text
intake_submissions=0
intake_documents=0
intake_processing_jobs=0
inbound_with_submission=0
```

---

## 4. Configuration manifest (secrets redacted)

```text
WATHEFNI_INBOUND_EMAIL=off
WATHEFNI_SENDER_ACKNOWLEDGMENT=off
WATHEFNI_POSTMARK_INBOUND_SECRET=***REDACTED***
WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET=***REDACTED***
WATHEFNI_INTAKE_QUARANTINE_BACKEND=local_volume
WATHEFNI_INTAKE_QUARANTINE_DIR=/opt/wathefni/staging/quarantine/email-intake
WATHEFNI_INTAKE_MALWARE_SCANNER=clamav
WATHEFNI_INTAKE_CLAMD_HOST=127.0.0.1
WATHEFNI_INTAKE_CLAMD_PORT=3310
WATHEFNI_INTAKE_SCAN_TIMEOUT_SECONDS=120
WATHEFNI_INTAKE_MAX_WEBHOOK_BYTES=25165824
WATHEFNI_INTAKE_MAX_ATTACHMENTS=12
WATHEFNI_INTAKE_MAX_FILE_BYTES=8388608
WATHEFNI_INTAKE_MAX_TOTAL_BYTES=12582912
WATHEFNI_INTAKE_MAX_PDF_PAGES=40
WATHEFNI_INTAKE_TENANT_CONCURRENCY=2
WATHEFNI_INTAKE_JOB_LEASE_SECONDS=180
WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS=5
WATHEFNI_INTAKE_RETRY_BASE_SECONDS=5
WATHEFNI_INTAKE_RETRY_MAX_SECONDS=900
WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS=86400
WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA=0
WATHEFNI_INTAKE_MONTHLY_MESSAGE_QUOTA=0
WATHEFNI_INTAKE_DAILY_SOURCE_BYTES_QUOTA=0
WATHEFNI_INTAKE_MONTHLY_SOURCE_BYTES_QUOTA=0
WATHEFNI_INTAKE_DAILY_PROCESSING_JOB_QUOTA=0
```

Systemd drop-in: `wathefni-orchestrator-staging.service.d/durable-email-ingress.conf` loads the EnvironmentFile above. Inbound remains **off**.

---

## 5. Infrastructure readiness evidence (pre-deploy confirmed)

| Check | Result |
|---|---|
| Encrypted quarantine mount | active (`LUKS` mapper → `/opt/wathefni/staging/quarantine/email-intake`) |
| ClamAV container | healthy |
| Signature line | `ClamAV 1.5.3/28071/Sat Jul 25 06:24:03 2026` (~6h age) |
| Signing + Postmark inbound secrets | present |
| Inbound | `off` |
| Worker service | `inactive` / `disabled` |

---

## 6. Deployment evidence

1. Modules copied; additive schema applied under old code.  
2. Patched `app.py` deployed; staging restarted.  
3. Health `200`.  
4. Worker unit remained stopped/disabled.  
5. No Postmark route configured/activated.  
6. No email sent.

Webhook dark proof (local HTTP only, not Postmark):

```text
no_auth=401 {"detail":{"error":"unauthorized"}}
auth_inbound_off=503 {"detail":{"error":"inbound_disabled"}}
```

---

## 7. No-email qualification results

Internal readiness (`/orchestrator/debug/intake-readiness`):

- `inbound_enabled=false`
- storage writable + fsync OK on encrypted volume
- ClamAV OK over TCP `127.0.0.1:3310`
- clean PDF → `clean`
- EICAR → `malware_detected`
- signing secret configured
- approved limits loaded (24 MiB / 12 / 8 MiB / 12 MiB / 40 pages / concurrency 2)

Dark qualify harness: **9/9 passed** (`ops/durable-email-ingress-staging-dark-qualify.py`)

| Case | Result |
|---|---|
| Additive schema | PASS |
| Deploy created no synthetic work | PASS |
| Quarantine storage adapter | PASS |
| Malware scanner adapter | PASS |
| Signed access tenant-scoped / cross-tenant fail | PASS |
| Synthetic queue (claim/lease/retry/DLQ/replay) | PASS |
| Orphan report | PASS |
| Zero residue | PASS |
| Inbound still off | PASS |

Synthetic queue used in-process handler only; **systemd intake worker never started**.

---

## 8. Scanner and storage adapter proof

| Adapter | Backend | Proof |
|---|---|---|
| `QuarantineStorage` | `local_volume` on LUKS mount | write/verify/fsync; object key `{COMPANY}/{UUID}/{ORDINAL}/{SHA256}.bin` |
| `MalwareScanner` | isolated ClamAV/`clamd` | health PONG; clean OK; EICAR FOUND; fail-closed |
| Signed access | HMAC company\|document\|exp | same-tenant accept; cross-tenant reject |

---

## 9. Synthetic queue matrix

Observed statuses after dark qualify passes:

- completed / retrying / waiting_quota / dead_letter
- expired lease reclaimed by second worker id
- dead-letter replay → pending → processed
- orphan report empty after cleanup
- residue cleaned to zero (`DARKINGA`/`DARKINGB`)

No candidate creation, OCR, classification, Ranking, or outbound from these fixtures.

---

## 10. Frozen regressions

| Suite | Result | Notes |
|---|---|---|
| Inbound email smoke (durable) | PASS | process-local env only; staging inbound remains off |
| Bulk CV import | PASS | |
| Tiered intake | PASS | |
| Candidates registry parity | PASS | |
| Recruiting lifecycle | PASS | |
| Assistant HR reads | PASS | |
| Assistant pre-hire parity | PASS | |
| Summary / Reports counts | PASS | |
| Ranking R0–R3 staging matrix | PASS | |
| Ranking result presentation | PASS | |
| Offers hiring staging matrix | **38/38** | |
| Interviews staging matrix | **45/45** | |
| Jobs pagination | **22/22** | |
| Jobs phase2 stage A unit | PASS | |
| Jobs phase2 stage B unit | PASS | |
| Offer hire-override | PASS | |
| Dashboard Vitest | **49/49** | local |
| Dashboard `tsc` + Vite build | PASS | existing chunk-size warning only |
| Jobs phase1 smoke | FAIL | pre-existing publish-requirements drift (`assert_job_publishable`); unchanged by ingress surgical patch |
| Job close/reopen smoke | FAIL | same publish-requirements class |
| Interview workflow unit smoke | FAIL | outdated Meet-link assertion; superseded by interviews matrix 45/45 |

Existing product HTTP health remained `200` throughout. Frozen Ranking/Reports/Assistant/Offers/Interviews/lifecycle authorities were not redesigned.

---

## 11. Zero-residue proof

Dark qualify cleanup:

```json
{"removed":{"rows":26,"objects":1},"left":{"submissions":0,"documents":0,"jobs":0,"events":0,"messages":0},"objects":[]}
```

Rollback sentinel (`DARKROLL`) cleaned after restore. No lasting synthetic intake residue.

---

## 12. Rollback proof

| Step | Result |
|---|---|
| Execute `ROLLBACK.sh` (prior `app.py`, remove ingress modules, drop EnvironmentFile) | done |
| Health after rollback | `200` |
| Existing product (`/dashboard/prehire/summary`) | `200` |
| Durable sentinel submission/document/message preserved | **yes** (`durable_sentinel` / `scan_pending` / `durable`) |
| Quarantine mount preserved | yes |
| Additive intake tables not dropped/rewritten | yes |
| Restore deployed artifact + EnvironmentFile | yes |
| Restored `app.py` SHA | `090e82b1…` match |
| Final readiness inbound off | yes |
| Workers still stopped | yes |

---

## 13. Unresolved risks

1. **Jobs phase1 / close-reopen smokes** need fixture updates for current publish requirements (language/location). Not caused by this ingress deploy.  
2. **Interview unit smoke** Meet-link assertion is stale; canonical interviews matrix is green.  
3. **LUKS reboot persistence** still not live-booted from the readiness phase.  
4. **Next inbound enablement** will accept durable receipts only if `WATHEFNI_INBOUND_EMAIL` is turned on; workers must stay stopped to keep OCR/candidate creation dark.  
5. **Internal `/orchestrator/debug/intake-worker/run`** can process jobs if invoked; keep operator discipline / token control.  
6. **Quarantine offsite** still dedicated staging backup, not yet unified into production `backup-wathefni` offsite.

None of these block enabling one isolated staging intake address with workers stopped.

---

## 14. GO / NO-GO for next step

Next step under consideration: **enable one isolated staging intake address while workers remain stopped.**

| Gate | Status |
|---|---|
| Dark code deploy complete | Pass |
| Additive schema only | Pass |
| Inbound currently off | Pass |
| Workers stopped/disabled | Pass |
| Adapter readiness (storage + ClamAV) | Pass |
| Durable queue mechanics proven synthetically | Pass |
| Frozen core regressions green (or superseded by matrices) | Pass |
| Rollback preserves ledger + quarantine | Pass |
| Deployed dark state restored | Pass |
| Postmark address enabled | **No (by design)** |
| Email sent | **No** |
| Production changed | **No** |

### Final call

- **GO** to enable one isolated staging intake address with:
  - workers still **stopped**
  - sender acknowledgment **off**
  - no OCR / candidate creation / classification / Talent Pool / Role Profile / outbound from inbound
  - explicit owner approval of the Postmark staging route for that single address only
- **NO-GO** to start workers, send production traffic, or deploy production.

---

## Explicit non-actions honored

- Postmark intake not enabled
- No email sent through Postmark
- Intake worker not started
- Production not deployed
- No candidate/OCR/Talent Pool/outbound enablement from inbound
