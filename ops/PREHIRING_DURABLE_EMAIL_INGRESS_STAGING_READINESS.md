# Pre-Hiring Durable Email Ingress — Staging Readiness

**Status:** INFRA READY — CODE NOT DEPLOYED  
**Date:** 2026-07-25  
**Host:** `srv1419988` (`76.13.63.68`)  
**Evidence:** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-readiness/20260725T122157Z`  
**Scope:** Staging infrastructure provisioning and readiness validation only

## Verdict

**GO** to deploy durable email-ingress **application code** to staging **with inbound still disabled**.

**NO-GO** for enabling the Postmark intake address, sending any staging test email, or starting intake workers until after that code deploy is verified and a separate inbound-enablement gate is approved.

This phase did **not** deploy application code, did **not** enable Postmark inbound, and did **not** send email.

---

## Architecture clarification (approved)

This is permanent production contract work with replaceable infrastructure adapters:

| Concern | Permanent contract | Staging adapter | First real production adapter |
|---|---|---|---|
| Quarantine | `QuarantineStorage` | Encrypted local volume (`local_volume`) | Encrypted S3-compatible object storage |
| Malware | `MalwareScanner` | Isolated ClamAV container via `clamd` TCP | Same contract; engine replaceable |
| Queue | Postgres leased queue | Postgres leased queue | Postgres leased queue (not temporary) |

Local contract modules prepared (not deployed to staging yet):

- `wathefni-orchestrator/intake_quarantine_storage.py`
- `wathefni-orchestrator/intake_malware_scanner.py`
- wiring/defaults in `wathefni-orchestrator/durable_email_ingress.py`

---

## 1. Provisioned resources

| Resource | Location / identity | State |
|---|---|---|
| Encrypted quarantine image | `/opt/wathefni/staging/var/quarantine-email-intake.luks` (8 GiB sparse) | Present, mode `600` |
| LUKS mapper | `wathefni-staging-email-quarantine` | Active (AES-XTS, 512-bit) |
| Quarantine mount | `/opt/wathefni/staging/quarantine/email-intake` | Mounted `0700` root:root |
| Unlock unit | `wathefni-staging-email-quarantine-unlock.service` | Enabled |
| Mount unit | `opt-wathefni-staging-quarantine-email\x2dintake.mount` | Enabled |
| ClamAV container | `wathefni-staging-clamav` (`clamav/clamav:stable`) | Running, healthy |
| Clamd bind | `127.0.0.1:3310` | Listening (host-local only) |
| ClamAV data volume | `/opt/wathefni/staging/var/clamav` | Present |
| Intake secrets/env | `/root/.openclaw/secrets/wathefni-intake.staging.env` | Present, mode `600` |
| LUKS key | `/root/.openclaw/secrets/wathefni-intake-quarantine.staging.luks.key` | Present, mode `600` |
| Internal token | `postgres.staging.env` (`WATHEFNI_INTERNAL_TOKEN`) | Present |
| Worker unit | `wathefni-intake-worker-staging.service` | Loaded, **disabled**, **inactive** |
| Worker timer | `wathefni-intake-worker-staging.timer` | Disabled |
| Readiness probe | `wathefni-intake-readiness-staging.timer` | Enabled (every 15m) |
| Quarantine backup tool | `/usr/local/bin/backup-wathefni-staging-email-quarantine` | Present |
| Quarantine backups | `/opt/wathefni/staging/backups/email-quarantine/` | First run proven |
| Ops check | `/opt/wathefni/staging/ops/bin/intake-readiness-check.sh` | Present |

---

## 2. Exact configuration manifest (secrets redacted)

Source: `/root/.openclaw/secrets/wathefni-intake.staging.env`

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

Approved safety controls encoded above:

| Control | Value |
|---|---:|
| Webhook body | 24 MiB |
| Attachments / message | 12 |
| Individual decoded file | 8 MiB |
| Decoded total attachments | 12 MiB |
| PDF pages / CV | 40 |
| Tenant worker concurrency | 2 |

Accepted formats (application contract): PDF, DOCX, JPG/JPEG, PNG, WebP. Legacy DOC, RTF, and arbitrary ZIP remain rejected.

These limits are configurable safety controls, not temporary architecture. Over-limit messages must fail visibly with an explicit recorded outcome (never silent ack / silent partial process).

**Webhook feature state now:** inbound remains `off`. The running staging orchestrator does **not** yet load this EnvironmentFile (by design until code deploy).

---

## 3. Storage and scanner adapter contracts

### `QuarantineStorage`

Permanent behaviors preserved across backends:

- object key shape `{COMPANY}/{INBOUND_UUID}/{ORDINAL}/{SHA256}.bin`
- checksum + size verification
- idempotent write / conflict on digest mismatch
- manifest authority stays in Postgres (`intake_documents`)
- signed access keyed by company + object key
- orphan sweep / deletion / audit remain authority-side

Adapters:

- **Staging:** `LocalVolumeQuarantineStorage` (`backend=local_volume`) on the encrypted mount
- **First real production:** `S3CompatibleQuarantineStorage` (`backend=s3_compatible`) with SSE; same keys and authority

Switching backends must not change intake, candidate, application, queue, or lifecycle authority.

### `MalwareScanner`

Permanent evidence fields:

- engine
- signature version
- scan timestamp
- result (`clean` / `malware` / `unavailable`)
- evidence payload

Approved initial engine: **ClamAV** as isolated container/`clamd`, fail closed. Replacing or adding scanners must not change intake authority.

Staging transport: `tcp://127.0.0.1:3310` to `wathefni-staging-clamav` (not inside the Wathefni web process).

### Queue

PostgreSQL leased queue remains the approved **production** queue architecture. Redis/managed queues are out of scope until documented operational evidence requires them.

---

## 4. Permission and encryption proof

| Check | Evidence |
|---|---|
| LUKS2 active | `cryptsetup status` → AES-XTS 512-bit, mapper in use |
| Header | `luks-dump.txt` (UUID `1f485845-58dc-43b0-98b5-b2e14d045cb0`) |
| Mount perms | `0700` `root:root` |
| Object perms | `0600` `root:root` for proof `.bin` |
| Secrets perms | intake env `600`, LUKS key `600`, LUKS image `600` |
| Clamd exposure | bound to `127.0.0.1:3310` only |

---

## 5. ClamAV health and safe test-file evidence

| Check | Result |
|---|---|
| Container | `running` / Docker health `healthy` |
| `zPING` | `PONG` |
| Signature line | `ClamAV 1.5.3/28071/Sat Jul 25 06:24:03 2026` |
| EICAR via INSTREAM | `stream: Eicar-Test-Signature FOUND` |
| Clean PDF via INSTREAM | `stream: OK` |
| Fail-closed posture | unavailable/ambiguous → no clean promotion |
| Isolation | scan performed against container `clamd`, not Wathefni web process |

---

## 6. Signature freshness

- Observed version: `ClamAV 1.5.3/28071/Sat Jul 25 06:24:03 2026`
- Freshness relative to readiness date (2026-07-25): **same day** (~6 hours old at check time)
- Container image includes freshclam update path; data persisted under `/opt/wathefni/staging/var/clamav`
- Readiness probe alerts if ClamAV becomes unreachable

---

## 7. Storage write / read / fsync proof

Proof object written under the encrypted mount:

- key: `STAGINGA/.../0001/63bf66e4…bab025ff.bin`
- sha256 write == sha256 read
- `fsync_ok=true`
- modes `0600` file / `0700` parent

---

## 8. Signed-access and cross-tenant rejection proof

Crypto-layer contract proof (application signed-download route still undeployed):

- message format `company|object_key|exp`
- HMAC-SHA256
- same-tenant accept: **true**
- cross-tenant token mismatch: **true**
- foreign tenant object for proof key did not exist
- signing secret provisioned as `WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET`

---

## 9. Backup and restore evidence

### Database (staging)

| Step | Result |
|---|---|
| `pg_dump -Fc` | SHA-256 `90aae2dc0ff62fa6365107740cad92fa951193b344f3f06381d79c3d4ab5b193` |
| Restore to temp DB | `pg_restore` exit `0` via `postgres` superuser |
| Public tables restored | **194** |
| Live staging tables | **194** (match) |
| Temp DB dropped | yes |
| Live DB mutated | no |

### Quarantine

| Step | Result |
|---|---|
| Backup tool | `/usr/local/bin/backup-wathefni-staging-email-quarantine` |
| Run | `/opt/wathefni/staging/backups/email-quarantine/20260725T122312Z` |
| Archive SHA-256 | `98cee0c7f479d2d2954d79fe421e49031d341245ca844096bb2446a5592f05c4` |
| Restore compare | `{compared: 1, matched: 1}` |
| Retention policy | last 7 local runs |
| Production later | same object keys on S3; versioning/replication are adapter concerns |

---

## 10. Monitoring and alert evidence

Probe: `/opt/wathefni/staging/ops/bin/intake-readiness-check.sh`  
Timer: `wathefni-intake-readiness-staging.timer` (enabled, 15 minutes)

Observed probe fields:

- quarantine disk + inode use
- root disk + inode use
- ClamAV health + signature version
- queue depth / lease / retry / dead-letter query hook
- worker active state
- Docker ClamAV status

Alert thresholds encoded:

- `clamav_unhealthy`
- `quarantine_disk_high` (≥85%)
- `quarantine_inodes_high` (≥85%)

Queue query currently returns “relation does not exist” — **expected** until ingress schema is deployed with application code. Monitoring hook is installed and ready.

---

## 11. Worker definitions (stopped) and webhook disabled

```text
worker service enabled? disabled
worker service active? inactive
worker timer enabled? disabled
WATHEFNI_INBOUND_EMAIL=off
WATHEFNI_SENDER_ACKNOWLEDGMENT=off
staging orchestrator does NOT load intake EnvironmentFile yet (code undeployed).
```

Worker unit points at future `durable-email-ingress-worker.py` under staging orchestrator and remains stopped until an explicit enablement after code deploy.

---

## 12. Rollback and reconciliation procedure

1. Keep `WATHEFNI_INBOUND_EMAIL=off`. Do not enable Postmark address.
2. Keep workers stopped: `systemctl disable --now wathefni-intake-worker-staging.service`
3. On application rollback:
   - restore prior orchestrator artifact
   - **do not** delete quarantine objects under `/opt/wathefni/staging/quarantine/email-intake`
   - **do not** truncate durable receipt tables (`inbound_messages`, `intake_*`)
4. Reconcile:
   - compare `intake_documents.quarantine_key` to on-volume objects
   - requeue scan/validation only after schema/code compatibility is confirmed
   - retain orphans beyond grace for operator review
5. ClamAV rollback replaces the container/image only; scanner contract unchanged.
6. Future storage cutover (`local_volume` → `s3_compatible`) copies identical keys before switching; authority tables unchanged.

---

## 13. Unresolved risks

1. **Reboot persistence not live-booted:** unlock + mount units are enabled, but a full host reboot was not executed in this phase.
2. **Queue metrics await schema deploy:** readiness probe cannot count depth/lease/DLQ until `intake_processing_jobs` exists.
3. **Intake env not attached to running orchestrator yet:** intentional until code deploy; attach EnvironmentFile as part of that deploy while keeping inbound `off`.
4. **Signed-download HTTP route undeployed:** crypto contract proven; end-to-end route proof waits for code deploy.
5. **Quarantine offsite/unified backup:** dedicated staging quarantine backup is proven locally; not yet folded into production `backup-wathefni` offsite pipeline.
6. **Same physical disk:** LUKS protects quarantine at rest, but the ciphertext file still resides on the root disk device.
7. **Worker binary path:** unit is ready; worker script arrives only with the undeployed application tree.
8. **Sender acknowledgment** remains correctly disabled for first staging qualification.

None of these block a **code deploy with inbound disabled**.

---

## 14. GO / NO-GO for deploying code (inbound still disabled)

| Gate | Status |
|---|---|
| Encrypted quarantine volume provisioned | Pass |
| Backend-neutral storage contract defined | Pass (local code ready; undeployed) |
| Isolated ClamAV service | Pass |
| Backend-neutral scanner contract defined | Pass (local code ready; undeployed) |
| freshclam / signature freshness evidence | Pass |
| Ownership / service-only permissions | Pass |
| Quarantine signing secret | Pass |
| Postmark inbound auth secret | Pass (generated; unused) |
| Intake env configuration | Pass (`inbound=off`) |
| Worker definitions stopped | Pass |
| Ops/readiness access | Pass |
| DB backup/restore proof | Pass |
| Quarantine backup/restore policy + proof | Pass |
| Disk/inode monitoring | Pass |
| ClamAV health monitoring | Pass |
| Queue monitoring hooks | Pass (await schema) |
| Rollback preserves receipts + quarantine | Pass (documented) |
| Application code deployed | **Not done (by design)** |
| Postmark address enabled | **No** |
| Test email sent | **No** |

### Final call

- **GO** to deploy durable email-ingress code to staging with `WATHEFNI_INBOUND_EMAIL=off`, workers still stopped, and Postmark address still disabled.
- **NO-GO** to enable inbound mail or send any staging test email in this phase.

---

## Explicit non-actions completed as required

- No application code deployed to staging/production
- Postmark intake address not enabled
- No email sent through Postmark
- Sender acknowledgment remains disabled
- Intake workers remain stopped
