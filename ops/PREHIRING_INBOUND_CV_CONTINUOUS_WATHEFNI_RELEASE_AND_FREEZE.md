# Pre-Hiring Inbound CV Continuous WATHEFNI Release and Freeze

Date: 2026-07-26  
Tenant: `WATHEFNI` only  
Environment: production  
Activation timestamp: `2026-07-26T16:15:58Z`  
Exact recipient:
`92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`

## Verdict

**GO — freeze the inbound Talent Pool automation phase with continuous
WATHEFNI automation operating.**

Approved automation remains ON after this release.

Continuous persistent workers automatically processed a fresh owner CV through
durable receipt, clean malware scan, and identity resolution without any
manual one-shot trigger. Identity authority correctly fail-closed on a weak
name match, opened an HR identity review, and refused ownership, extraction,
and classification. Kill switch and restore were proven. No external tenants,
Gmail/mailbox sync, sender acknowledgment, generic classification workers,
historical backfill, or retention cleanup were enabled.

## Sealed evidence

Production evidence root:

`/opt/wathefni/production-evidence/continuous-wathefni-release/20260726T161509Z`

Primary artifacts:

- `pre-activation.json`
- `activation-started-at.txt`
- `activated-posture.json`
- `continuous-operation-proof.json`
- `live-proof.json`
- `live-proof-summary.json`
- `kill-switch-proof.json`
- `final-leave-state.json`
- `monitor-latest-final.json`
- `KILL_SWITCH.sh`
- `RESTORE_CONTINUOUS.sh`
- `evidence-manifest.sha256`

Owner records preserved and not cleaned:

- prior canary candidate `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT`
- continuous live identity review `872fbd2d-326c-4882-bc16-533fdad15d13`

## Runtime and configuration identities

- Health: `200`
- Runtime composite SHA-256:
  `7cdb2c4de06b92f5da9a1a25c17c6ce2b278267780e1f6f82777c638eecfe9ce`
- Active retention policy: `inbound-retention-ops-v1`
- Exact active recipient inventory: one `WATHEFNI` address only
- ClamAV: Docker `wathefni-production-clamav` running/healthy
- Signature evidence observed on live scan:
  `ClamAV 1.5.3/28073/Sun Jul 26 06:25:14 2026`
- Quarantine mount:
  `/opt/wathefni/quarantine/email-intake` on
  `/dev/mapper/wathefni-production-email-quarantine`
- Service identity: orchestrator process user `root`, configured intake
  identity `wathefni-orchestrator-production`
- Rollback artifact present:
  `/opt/wathefni/backups/production-pre-final-pre-rearm-20260726T145921Z/ROLLBACK.sh`
- Noor/Esraa correction remains intact:
  open identity review count `1`, classification invalidation count `1`,
  invalidated run prefix `a48f3779` present

## Final enabled and disabled controls

Enabled for `WATHEFNI`:

- `WATHEFNI_INBOUND_EMAIL=on`
- `WATHEFNI_INTAKE_TENANT_CONCURRENCY=1`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=on`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=WATHEFNI`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_STARTED_AT=2026-07-26T16:15:58Z`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_RECIPIENT=<exact recipient>`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_MAX_ATTEMPTS=3`
- `WATHEFNI_TALENT_POOL_CLASSIFICATION=on`
- `WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=on`
- `WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=on`
- `WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=on`
- `WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI`

Kept OFF:

- sender acknowledgment
- Gmail/mailbox live synchronization
- generic unrestricted classification workers
  (`WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off`)
- external tenants
- historical backfill
- retention cleanup scheduler
- legacy `wathefni-prehire-cv-process.timer` (inactive and disabled)

## Worker and service posture

Installed and enabled persistent units:

| Unit | Role | Mode |
|---|---|---|
| `wathefni-inbound-intake-worker.timer/.service` | durable intake processing | oneshot, `--limit 1`, every 15s, fail-closed unless inbound email ON |
| `wathefni-talent-pool-auto-email-classification.timer/.service` | automatic post-extraction classification | oneshot, `--limit 1`, every 15s, fail-closed unless auto-class ON and tenant allowlist includes WATHEFNI |
| `wathefni-inbound-ops-monitor.timer/.service` | operational metrics snapshot | oneshot every 60s, read-only, no candidate messaging |

Worker binary added for continuous intake:

`/opt/wathefni/orchestrator/durable-email-ingress-worker.py`

Classification continues to use:

`/opt/wathefni/orchestrator/talent_pool_auto_email_classification.py`

Bounds:

- WATHEFNI only
- exact recipient only for automatic classification eligibility
- concurrency `1`
- idempotent claims
- retries and dead-letter support
- no historical jobs before `2026-07-26T16:15:58Z`
- no unrestricted backfill
- scan/identity/ownership gates remain authoritative before downstream work
- workers do not call outreach, ranking, lifecycle, or Job assignment

## Monitoring proof

Monitor root:

`/var/lib/wathefni/inbound-ops-monitor`

Observed metrics include:

- intake and classification queue depth
- oldest pending age
- success / retry / dead-letter counts
- scan failures and malware detections
- open identity reviews and identity conflicts
- extraction failures and OCR usage
- classification latency
- worker/unit health and ClamAV health
- non-WATHEFNI and recipient-violation counters
- held-with-Job-binding suspects
- absolute lifecycle / ranking / outbound / interview totals

Alerting writes local alert snapshots only. Candidate messaging remains
disabled.

Expected current alerts after activation include the retained Noor open
identity review and the historical scan-failure residue from the governed
correction path. Those are preserved authority records, not continuous-release
regressions.

## Continuous live CV journey

No one-shot intake or classification command was used.

Inbound:

- Inbound ID: `df24ed05-37ea-59f3-ae1c-c79194534be8`
- Durable at: `2026-07-26T16:20:35.995819Z`
- Recipient: exact authorized Postmark address
- Tenant: `WATHEFNI`
- Filename: `Mariam_Almulla_CV_Test.pdf`
- Sender provenance only: `azizalmulla16@gmail.com`

Persistent worker journal proof:

- `16:20:45Z` worker completed `intake_validation`
  (`c2cd87c6-58f1-4a4f-a44c-0b95be7afcaf`)
- `16:21:00Z` worker completed `file_safety_scan`
  (`4b5f466e-8d61-4842-86f0-1040fc38337c`)
- `16:21:16Z` worker completed `cv_identity_resolution`
  (`6a44dea8-1b46-448a-9d02-1883fff96bfd`)

Scan:

- State: `clean`
- Engine: `clamav`
- Version: `ClamAV 1.5.3`
- Signature:
  `ClamAV 1.5.3/28073/Sun Jul 26 06:25:14 2026`

Identity:

- Extracted name/email/phone from CV:
  `mariam almulla` /
  `mariam.almulla@example.com` /
  `96555629147`
- Outcome: `possible_match`
- Ownership confirmed: `false`
- Reason: `weak_name_match_requires_hr_review`
- Selected app key: none
- Open review ID: `872fbd2d-326c-4882-bc16-533fdad15d13`
- Possible existing matches retained for HR review only

Authority-correct terminal state:

- no candidate created or reused
- no document ownership confirmed
- no immutable CV text version created
- no extraction/OCR continuation
- no classification job enqueued
- no dashboard classification chip produced for a new row
- no Job linkage
- no lifecycle, ranking, interview, offer, hiring, or outbound mutation from
  this journey

This is the required fail-closed continuous behavior when identity is unsafe
to auto-merge. Classification correctly remained gated behind clean scan, safe
identity, ownership confirmation, and canonical extraction.

## Tenant and recipient isolation

- Active recipients after activation: exactly one, `WATHEFNI` only
- External active recipients: `0`
- Historical active intake jobs before activation: `0`
- Historical active classification jobs before activation: `0`
- Non-WATHEFNI active intake/classification jobs: `0`
- Post-activation recipient violations: `0`

## Forbidden mutation proof

For the continuous live journey:

- Job binding: none
- lifecycle events for a new app: none created
- ranking evaluations for a new app: none created
- interviews for a new app: none created
- outbound delivery for a new app: none created
- sender acknowledgment jobs: none
- automatic intake admit: none

Prior owner canary record remains preserved and held without Job binding.

## Kill-switch and restore proof

Kill switch at `2026-07-26T16:25:24Z` → `16:25:26Z`:

- stopped and disabled intake + classification timers
- set `WATHEFNI_INBOUND_EMAIL=off`
- set automatic classification OFF and cleared tenant allowlist
- kept classification UI/manual review ON
- kept Unified Candidates ON
- preserved evidence and audit rows
- health returned `200`

Restore at `2026-07-26T16:25:42Z` → `16:25:45Z`:

- restored the approved continuous WATHEFNI-only flag set
- re-enabled and started intake, classification, and monitor timers
- left pre-hire CV timer inactive/disabled
- health `200`
- runtime composite unchanged
- Mariam identity review still `open`
- Yasser owner canary record still present

## Final leave-state

Automation left ON for internal `WATHEFNI` only:

- orchestrator: active
- inbound intake timer: active + enabled
- automatic classification timer: active + enabled
- ops monitor timer: active + enabled
- pre-hire CV timer: inactive + disabled
- inbound email: on
- automatic classification: on / tenants=`WATHEFNI`
- Unified Candidates: on / tenants=`WATHEFNI`
- classification UI/manual: on
- sender acknowledgment: off
- generic classification workers: off
- retention cleanup: off
- retention policy: `inbound-retention-ops-v1`
- runtime composite unchanged
- owner test records preserved

## Residual note

The continuous live CV intentionally exercised the weak-name identity hold
path. Full happy-path continuous extraction and automatic classification under
persistent workers therefore did not continue for that message. That is
correct authority behavior, not a worker failure.

The final owner production canary already proved the complete clean-scan →
safe-identity → ownership → extraction → automatic classification path for a
non-conflicting CV. Continuous workers now own that same production path for
future eligible WATHEFNI inbound mail.

## Stop state

The inbound Talent Pool automation phase is frozen with approved continuous
WATHEFNI automation operating. External tenants were not enabled. No next
product phase was started.
