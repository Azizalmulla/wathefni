# Pre-Hiring Durable Email Ingress — Owner Decisions & Staging Readiness

**Status:** OWNER DECISION REQUIRED  
**Date:** 2026-07-25  
**Inputs:** local-green durable ingress remediation; current single-VPS Wathefni staging/production layout  
**Deployment:** None  
**Code/config changes in this phase:** None

## Purpose

Convert the accepted local remediation into exact owner choices and a staging
configuration manifest that matches how Wathefni already runs:

- one VPS;
- staging orchestrator on `127.0.0.1:8011`;
- production on `8010` behind Caddy;
- Postgres on localhost;
- workspace files under `/opt/wathefni/staging/workspace` and production workspace;
- secrets under `/root/.openclaw/secrets/`;
- systemd oneshot/timer workers for delivery sweep, document-storage reconcile,
  and daily `backup-wathefni`.

This report recommends pilot values only. It does not invent commercial quotas
or enable real inbound mail.

---

## 1. Malware scanning

### Recommended selection

**ClamAV on the same VPS**, using the already-wired `clamscan`/`clamav` adapter
path (`WATHEFNI_INTAKE_MALWARE_SCANNER=clamav`).

Deployment model for staging:

| Item | Choice |
|---|---|
| Package | OS ClamAV (`clamav`, `clamav-freshclam`, optional `clamd`) |
| Invocation | `clamscan --no-summary <quarantine-path>` from the intake worker |
| Scope | Quarantined source files only, after durable receipt and before OCR |
| Privilege | Orchestrator/worker user; no HR dashboard access to scanner |
| Network | Offline local scan; no third-party cloud AV for the first phase |

Why not a cloud malware API yet:

- source CVs stay on Wathefni-controlled storage;
- current infra is single-VPS and already fail-closed when scanner is unavailable;
- ClamAV matches the implemented adapter without new vendor contracts.

### Fail-closed behavior

Approve the implemented policy:

1. Scanner unavailable / timeout / non-zero unexpected exit → document stays
   `scan_pending`; job retries; **no OCR**.
2. Signature hit → `malware_suspicious`; no accepted preparation; no OCR.
3. Clean scanner result still requires MIME/extension/PDF/DOCX/image preflight
   before `clean`.
4. Never treat `test_clean` as a staging or production scanner.

### Timeout and retries

| Control | Pilot value | Rationale |
|---|---:|---|
| Scanner process timeout | **120 s** | Matches the local adapter timeout |
| Queue attempts for scan jobs | **5** | Same as intake job max attempts |
| Retry base / max | **5 s / 900 s** with jitter | Already implemented |
| Lease | **180 s** | Long enough for ClamAV + preflight; reclaimable |

### Signature update schedule

| Environment | Schedule |
|---|---|
| Staging | `freshclam` at least **every 6 hours**; verify status before enabling the first test email |
| Production later | **hourly** `freshclam` timer, or `clamd` with freshclam daemon |

Ops check before inbound enablement:

```text
clamscan --version
freshclam --version
# confirm definitions are not older than 7 days on staging pilot
```

### Evidence retained

Retain only redacted operational evidence:

- safety state (`scan_pending`, `clean`, `malware_suspicious`, …);
- reason code (`clamav_signature_match`, `clamscan_unavailable`, …);
- job event rows with redacted error detail;
- content SHA-256 and quarantine key.

Do **not** retain:

- full ClamAV stdout/signature names in HR-facing UI;
- decoded file bodies in job payloads;
- sender email in error strings beyond already-redacted detail.

### Scanner outage behavior

| Condition | Behavior |
|---|---|
| ClamAV missing / broken | Jobs retry while documents remain `scan_pending` |
| Definition update lag | Still scan with current defs; ops alert if defs older than 7 days |
| Sustained outage past max attempts | Job enters `dead_letter`; source object and ledger remain; explicit replay after restore |
| Owner emergency | Keep inbound webhook enabled only if durability is intact; stop scan/OCR workers or leave them fail-closed |

**Owner decision:** approve ClamAV local fail-closed as the staging malware provider.

---

## 2. Quarantine storage

### Recommended selection

**Encrypted persistent disk on the VPS for staging and first production phase.**

Do **not** introduce S3-compatible object storage for the first staging cut.

Why:

- the local remediation already uses a filesystem quarantine adapter;
- Wathefni already stores company files on disk and backs them up with
  `backup-wathefni`;
- staging is localhost-only and single-host;
- S3 adds credentials, network failure modes, and a second durability plane
  before the durable ingress path is proven with attachments + ClamAV + OCR.

### Staging design

```text
Mount/path:
  /opt/wathefni/staging/quarantine/email-intake

Permissions:
  owner: root or orchestrator service user
  mode: 0700 directories / 0600 objects
  not world-readable; not under dashboard static paths

Env:
  WATHEFNI_INTAKE_QUARANTINE_DIR=/opt/wathefni/staging/quarantine/email-intake
```

Separate this root from:

- `/opt/wathefni/staging/workspace` HR/candidate files;
- employee document storage;
- dashboard dist.

### Production design (later, same model)

```text
/opt/wathefni/production/quarantine/email-intake
```

Move to S3-compatible storage only if one of these appears:

- more than one orchestrator host needs shared quarantine;
- local disk backup/restore time for quarantine exceeds the accepted RTO;
- capacity planning shows quarantine growth that disk backup cannot meet.

### Tenant isolation

Keep the implemented key shape:

```text
{COMPANY_CODE}/{INBOUND_UUID}/{ORDINAL}/{SHA256}.bin
```

Rules:

- never put original filenames in the path;
- never allow HR tools to list quarantine as normal candidate files;
- signed download must include `company_code` and fail for cross-tenant signatures;
- internal download remains behind `WATHEFNI_INTERNAL_TOKEN`.

### Encryption

| Layer | Pilot choice |
|---|---|
| At rest | VPS volume encryption (LUKS or provider disk encryption) for the quarantine filesystem |
| In transit | Local path only on staging; later HTTPS to object storage if introduced |
| Application | Existing SHA-256 integrity verification; no additional envelope encryption required for staging |

### Backup and restore

Include quarantine in staging/production backup scope separately from “normal”
workspace restore drills:

1. Daily `backup-wathefni` must cover the quarantine directory.
2. Pre-deploy snapshots must note quarantine path and size.
3. Restore drill: restore one known synthetic object by key and verify SHA-256.
4. DB restore without quarantine, or quarantine without DB, is a reconciliation
   case — do not auto-delete either side during rollback.

### Signed access

Use the implemented HMAC contract:

- secret: `WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET` in
  `/root/.openclaw/secrets/`;
- short TTL (300 s default);
- company + document + expiry bound;
- internal auth still required for the download route in this phase.

### Orphan lifecycle

| Stage | Pilot value |
|---|---|
| Grace before sweep eligibility | **72 hours** staging / **24 hours** only if disk pressure forces it |
| Default sweep mode | Report-only |
| Apply delete | Explicit internal operator action |
| After malware | Keep object until owner retention decision; do not HR-expose |

### Rollback reconciliation

On code rollback:

1. Disable inbound webhook / leave `WATHEFNI_INBOUND_EMAIL=off`.
2. Stop intake workers.
3. **Keep** ledger rows and quarantine objects.
4. Reconcile with ops summary + orphan report.
5. Do not wipe quarantine as part of app rollback.

**Owner decision:** approve encrypted local disk quarantine for staging and first
production; defer S3.

---

## 3. Technical limits — safe pilot values

These are technical safety caps for one isolated staging tenant, not commercial
plan limits.

| Limit | Pilot value | Env |
|---|---:|---|
| Webhook body | **16 MiB** | `WATHEFNI_INTAKE_MAX_WEBHOOK_BYTES=16777216` |
| Attachments per email | **8** | `WATHEFNI_INTAKE_MAX_ATTACHMENTS=8` |
| Per-file decoded size | **8 MiB** | `WATHEFNI_INTAKE_MAX_FILE_BYTES=8388608` |
| Total decoded attachments | **12 MiB** | `WATHEFNI_INTAKE_MAX_TOTAL_BYTES=12582912` |
| PDF pages | **40** | `WATHEFNI_INTAKE_MAX_PDF_PAGES=40` |
| Image pixels | **20,000,000** | `WATHEFNI_INTAKE_MAX_IMAGE_PIXELS=20000000` |
| Archive members (DOCX package) | **200** | keep default |
| Archive expanded bytes | **32 MiB** | keep default |
| Global worker claim batch | **25**/pass | worker `--limit 25` |
| Per-tenant concurrency | **2** | `WATHEFNI_INTAKE_TENANT_CONCURRENCY=2` |
| Max attempts | **5** | `WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS=5` |
| Lease duration | **180 s** | `WATHEFNI_INTAKE_JOB_LEASE_SECONDS=180` |
| Orphan grace | **72 h** | `WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS=259200` |
| Commercial quotas | **disabled (0)** | leave day/month quotas at 0 |

Notes:

- Attachment count **8** is tighter than the local default of 12 for a safer
  first pilot.
- PDF pages **40** is tighter than the local default of 80 until OCR cost and
  latency are measured on staging.
- Commercial quotas remain owner-commercial decisions and stay off.

---

## 4. Accepted formats

### Initial allowlist — confirm

| Format | Accept | Notes |
|---|---|---|
| PDF | Yes | After encryption/page/EOF checks + clean scan |
| DOCX | Yes | Valid OOXML package only; encrypted members rejected |
| JPG/JPEG | Yes | Dimension/pixel caps |
| PNG | Yes | Dimension/pixel caps |
| WebP | Yes | Detected MIME required |

### Keep rejected

| Format | Decision | Reason |
|---|---|---|
| Legacy `.doc` | Reject | No safe local parser in current foundation; OLE risk |
| RTF | Reject | Not in allowlist; weak CV signal vs risk |
| Arbitrary ZIP | Reject | Zip-bomb and nested-archive risk; DOCX is handled as a constrained package |
| EXE/bin/unknown | Reject | Unsupported / MIME mismatch paths |

There is **no strong evidence** in the current Wathefni stack to accept legacy
DOC, RTF, or arbitrary ZIP safely for the first staging qualification.

**Owner decision:** confirm the five-format allowlist and keep the rejections.

---

## 5. Queue and capacity

### PostgreSQL leased queue for first production phase

**Confirm: yes.**

Reasons aligned to current infra:

- staging/production already depend on local Postgres;
- the remediation proves `FOR UPDATE SKIP LOCKED`, leases, dead letters, fairness,
  and observability;
- the architecture target explicitly chose Postgres for the first release;
- Wathefni does not currently operate Redis/Celery for orchestrator intake.

### Evidence that would justify Redis or another managed queue later

Move only if **measured** on staging/production:

1. Claim latency or lock wait regularly exceeds **100 ms p95** under sustained
   intake load while Postgres CPU is the bottleneck.
2. Queue depth for `pending`/`retrying` grows for **> 30 minutes** while workers
   are healthy and not provider-throttled.
3. More than one app host needs a shared queue without sticky DB claim locality.
4. Intake job volume sustains **> ~50 completed jobs/sec** with attachment scan +
   OCR still on the same DB primary and harms OLTP latency for dashboard/HR.
5. Operational need for independent queue autoscaling separate from Postgres.

Until then, keep the Wathefni-owned Postgres queue.

### Realistic staging load test

The local 1,000-message burst proved receipt durability only. Staging must use
attachments and real downstream stages.

Recommended isolated staging load profile:

| Phase | Volume | Workers enabled | Pass criteria |
|---|---:|---|---|
| A. Durable receipt only | 200 emails × 1 small PDF | none / validation only | 200 durable; 0 candidates until prepare; 0 silent loss |
| B. Scan | same 200 | validation + safety scan | all terminal safety or clean; scanner outage drill remains fail-closed |
| C. Accepted prepare | 50 clean PDFs | + accepted preparation | held `needs_role` only; sender email not candidate key |
| D. OCR | 20 clean PDFs | + CV extraction | no OCR before clean; provider timeouts retry/DLQ visibly |
| E. Mixed burst | 100 emails over 10 min, 1–3 attachments, include unsupported/password/oversize | all intake workers | zero silent loss; fairness across 2 synthetic tenants |
| F. Provider throttle | force Mistral/OCR slow or 429 | extraction on | jobs wait/retry; webhook stays fast; no sync OCR in request |

Throttle assumptions to encode in the test plan:

- Postmark redelivery for 503s;
- Mistral OCR rate limits;
- Voyage embedding only if extraction path triggers it;
- never point the load at production DB or a shared non-synthetic tenant.

---

## 6. Privacy and sender acknowledgment

### First staging qualification

**Keep sender acknowledgment disabled.**

Configured behavior already returns a disabled/reserved result for
`sender_acknowledgment`. Do not enqueue live sender email for staging.

### Decisions required before enabling acknowledgment later

1. **Legal basis / privacy notice** for unsolicited CVs and agency submissions.
2. **Notice text** in English and Arabic, including retention summary.
3. **Sender identity rule:** acknowledge the SMTP sender only as a mail
   correspondent, never as the candidate person key.
4. **When to send:** only after durable receipt? only after clean scan? never on
   malware/unknown recipient/spam?
5. **Bounce handling:** Postmark outbound bounce/complaint linkage and
   suppression list.
6. **Suppression:** honor prior opt-out, abuse complaints, and repeated bounces.
7. **Consent record:** what is stored, where, and for how long.
8. **Agency case:** one acknowledgment per email vs per CV; avoid leaking other
   candidates’ names.
9. **Rate limit:** max acknowledgments per sender/domain/day.
10. **Dry-run proof:** staging must prove copy and suppression with
    `WATHEFNI_DELIVERY_MODE=dry_run` before any live send.

---

## 7. Deployment readiness — before one isolated staging test email

Do not enable real inbound mail until every item below exists.

### Secrets

| Secret | Location / form |
|---|---|
| Staging DB URL + identity marker | `/root/.openclaw/secrets/postgres.staging.env` |
| `WATHEFNI_POSTMARK_INBOUND_SECRET` | dedicated staging secret file or EnvironmentFile |
| `WATHEFNI_INTERNAL_TOKEN` | staging internal ops token |
| `WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET` | random 32+ byte secret |
| Mistral OCR key | existing `/root/.openclaw/secrets/mistral.env` (only when OCR stage enabled) |
| Voyage key | existing voyage secret (only if extraction/embed stage enabled) |
| Postmark inbound webhook Basic/`token` match | same as inbound secret |

### Storage / host resources

| Resource | Required state |
|---|---|
| Quarantine directory | `/opt/wathefni/staging/quarantine/email-intake` exists, `0700`, on encrypted disk |
| Backup coverage | quarantine path included in backup inventory |
| Disk headroom | enough for pilot corpus + 72h orphans (recommend ≥ 20 GiB free) |
| ClamAV packages + definitions | installed; freshclam recent |
| Staging DB | `wathefni_staging` identity marker valid; additive ingress schema applied |

### Services / workers

| Unit / process | Role before first email |
|---|---|
| `wathefni-orchestrator-staging.service` | app + webhook surface on `:8011` |
| Intake worker (new systemd oneshot/timer or manual) | start **stopped** until receipt proof; then validation/scan only |
| Existing CV/document workers | leave OCR off the first email until clean-scan proof |
| `backup-wathefni` / predeploy snapshot | taken and verified before deploy |
| ClamAV / freshclam | healthy |

Recommended first-email worker posture:

1. webhook enabled for **one** synthetic staging intake address only;
2. validation + safety-scan workers on;
3. accepted preparation off until scan proof;
4. CV extraction off until preparation proof;
5. sender acknowledgment off.

### Health checks

| Check | Expectation |
|---|---|
| `GET http://127.0.0.1:8011/health` | 200 |
| `GET /ready` | ready + environment binding match |
| `GET /orchestrator/debug/intake-operations` with internal token | returns message/job/safety/quota/orphan summary |
| ClamAV smoke on a benign PDF and EICAR test file in an isolated temp path | clean vs malware_suspicious |
| Postmark webhook auth negative test | 401 without secret |
| Inbound disabled test | 503 while `WATHEFNI_INBOUND_EMAIL=off` |
| One synthetic email with workers stopped | durable ledger + quarantine + queued validation; no candidate |
| Duplicate MessageID | idempotent 200; no duplicate work |

### Postmark / DNS / routing

| Item | Pilot requirement |
|---|---|
| Staging inbound address | one isolated local-part on staging-only company |
| Webhook URL | SSH-tunnel or approved staging ingress path to `:8011` — staging remains non-public by default |
| Provider max payload | ≥ webhook body cap |
| Retry policy | retain retries on 5xx/503; do not treat 401/413 as success |

---

## Recommended selections

| Topic | Recommendation |
|---|---|
| Malware | Local ClamAV; fail-closed; 120s timeout; 5 attempts; freshclam ≤6h staging |
| Quarantine | Encrypted local disk path; defer S3 |
| Formats | PDF, DOCX, JPG/JPEG, PNG, WebP only |
| Queue | Keep Postgres leased queue |
| Sender ack | Disabled for first staging qualification |
| Commercial quotas | Leave disabled |
| Technical caps | 16 MiB body; 8 attachments; 8/12 MiB sizes; 40 PDF pages; 20M pixels; tenant concurrency 2; lease 180s; attempts 5 |

---

## Exact staging configuration manifest

Proposed EnvironmentFile
`/root/.openclaw/secrets/wathefni-durable-ingress.staging.env`:

```text
WATHEFNI_INBOUND_EMAIL=off
WATHEFNI_POSTMARK_INBOUND_SECRET=<staging-postmark-inbound-secret>
WATHEFNI_INBOUND_DOMAIN=inbound.wathefni.ai
WATHEFNI_INTERNAL_TOKEN=<staging-internal-token>

WATHEFNI_INTAKE_QUARANTINE_DIR=/opt/wathefni/staging/quarantine/email-intake
WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET=<staging-quarantine-hmac-secret>
WATHEFNI_INTAKE_MALWARE_SCANNER=clamav

WATHEFNI_INTAKE_MAX_WEBHOOK_BYTES=16777216
WATHEFNI_INTAKE_MAX_ATTACHMENTS=8
WATHEFNI_INTAKE_MAX_FILE_BYTES=8388608
WATHEFNI_INTAKE_MAX_TOTAL_BYTES=12582912
WATHEFNI_INTAKE_MAX_PDF_PAGES=40
WATHEFNI_INTAKE_MAX_IMAGE_PIXELS=20000000
WATHEFNI_INTAKE_MAX_ARCHIVE_MEMBERS=200
WATHEFNI_INTAKE_MAX_ARCHIVE_EXPANDED_BYTES=33554432
WATHEFNI_INTAKE_MAX_ARCHIVE_RATIO=100

WATHEFNI_INTAKE_JOB_LEASE_SECONDS=180
WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS=5
WATHEFNI_INTAKE_RETRY_BASE_SECONDS=5
WATHEFNI_INTAKE_RETRY_MAX_SECONDS=900
WATHEFNI_INTAKE_TENANT_CONCURRENCY=2
WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS=259200

WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA=0
WATHEFNI_INTAKE_MONTHLY_MESSAGE_QUOTA=0
WATHEFNI_INTAKE_DAILY_SOURCE_BYTES_QUOTA=0
WATHEFNI_INTAKE_MONTHLY_SOURCE_BYTES_QUOTA=0
WATHEFNI_INTAKE_DAILY_PROCESSING_JOB_QUOTA=0
```

Service wiring notes:

- add the EnvironmentFile to `wathefni-orchestrator-staging.service` only after
  artifact deploy approval;
- keep `WATHEFNI_INBOUND_EMAIL=off` until receipt readiness checks pass;
- add a staging intake worker unit modeled on
  `wathefni-document-storage-reconcile-staging.service`, initially disabled;
- do not enable sender acknowledgment jobs.

Isolated tenant prerequisites:

- synthetic company code reserved for ingress staging only;
- one `intake_addresses` row for that company;
- no production mailbox forwarding to it.

---

## Unresolved owner choices

These remain explicit owner decisions even after accepting the recommendations:

1. Approve ClamAV as the staging malware provider versus purchasing a managed AV API.
2. Approve encrypted local-disk quarantine versus forcing S3 on day one.
3. Approve the pilot technical caps in §3, especially attachment count 8 and PDF pages 40.
4. Confirm the five-format allowlist and continued rejection of DOC/RTF/ZIP.
5. Approve commercial quota values later; keep disabled for first staging email.
6. Approve sender-acknowledgment policy package in §6 before any ack enablement.
7. Approve whether staging Postmark webhook may be exposed beyond SSH tunnel
   (default: keep localhost + tunnel).
8. Approve quarantine retention for malware/suspicious objects and privacy
   deletion SLA.
9. Approve whether profile structuring/embedding stay inside the combined CV
   worker for staging.
10. Approve production disk path and backup inclusion only after staging-green.

---

## Go / no-go verdict for staging

**NO-GO for receiving even one isolated test email today.**

Reasons:

- owner selections above are not yet formally approved;
- ClamAV is not confirmed installed/configured on staging as an approved
  provider;
- quarantine disk path, signing secret, and backup coverage are not provisioned
  by this phase;
- staging EnvironmentFile / worker unit / inbound enablement sequence has not
  been applied;
- no deployment was authorized.

**Conditional GO criteria** (still not authorization to deploy):

1. Owner accepts the recommended selections in this document.
2. Secrets, ClamAV, encrypted quarantine path, and backup coverage exist on
   staging.
3. A separately authorized staging deploy follows the local remediation’s
   guarded order with inbound initially off.
4. Readiness health checks pass.
5. Only then may one isolated synthetic staging address receive a test email
   with validation/scan workers staged carefully and sender acknowledgment
   still disabled.

**Stop.** Do not deploy. Do not enable real inbound mail.
