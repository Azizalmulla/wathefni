# Phase 7E-R1 implementation report

**Verdict:** R1A and R1B implementation checkpoints are green. The complete expanded E2 matrix is **55/57**; all **51 original E2 cases pass**. C07k and C07l remain failed under their unchanged assertions. Therefore Phase 7E remains **open / not staging-green** under the binding full-matrix rule. Phase 8 must not begin.

No production flag was enabled. No production tenant or employee was mutated. Phase 7D routing, shared WhatsApp routing, onboarding seed, push, store work, and dashboard/bootstrap were not changed.

## Separate implementation checkpoints

| Slice | Commit | Checkpoint | Result |
|-------|--------|------------|--------|
| R1A — identity/lifecycle/session | `79a2bf9` | `ops/staging-phase7e-r1a-checkpoint.py` | **20/20 pass** |
| R1B — upload content consistency | `3f50e8b` | `ops/staging-phase7e-r1b-checkpoint.py` | **9/9 pass** |
| R1B deployment safeguard | `a714419` | deploy-script syntax check | pinned dependency included in artifact/install gate |
| Expanded E2 | evidence refresh after both commits | `ops/staging-phase7e-employee-app-verify.py` | **55/57 pass** |

Evidence:

- `ops/reports/phase7e-r1a-checkpoint-report.json`
- `ops/reports/phase7e-r1b-checkpoint-report.json`
- `ops/reports/phase7e-e2-verifier-report.json`
- `ops/reports/phase7e-e2-verifier-report.md`

## R1A implemented behavior

### Canonical identity and transactional activation

- Invite redemption now locks the company, pending invite, and canonical employee activation state.
- Code, expiry, canonical company, exact `invite.employee_key`, phone-resolved employee, lifecycle, effective module, and employment eligibility are validated before session issuance.
- Session creation and invite redemption commit in one transaction; the invite is consumed only after session insertion succeeds.
- Existing active session returns deterministic `409 already_activated` only after secure invite validation/binding.
- Identity/lifecycle/module/eligibility denials do not redeem the invite or create a session.
- Concurrent double activation produced one success and one active session.

### Lifecycle and module revocation

The Phase 7A transition hook previously revoked only dashboard sessions/invites. It now calls one shared employee-app invalidation helper in the same transition transaction:

- active employee sessions → `revoked`
- refresh hash → `NULL`
- expiry timestamps bounded to transition time
- pending employee-app invites → `superseded`

The same helper runs when the effective `employee_app` module is removed. Reactivation/re-addition has no inverse operation, so old sessions, refresh credentials, and invites cannot revive.

### Refresh ordering

Refresh now:

1. resolves the current session record without mutation
2. takes a shared company lock (serialized against lifecycle/module transitions)
3. checks active lifecycle and effective module
4. locks and revalidates the refresh/session record
5. loads and checks current employee eligibility
6. generates and writes replacement hashes only after all gates pass

Focused evidence records unchanged hashes for direct lifecycle/module/eligibility denials, and cleared hashes when a lifecycle/module transition revokes the session.

## R1B implemented behavior

- Pinned `puremagic==2.2.0`, compatible with deployed Python **3.12.3**.
- Detector receives bytes only; the submitted filename is never passed to `puremagic`.
- Extension and client-declared MIME are independently allowlisted.
- Server-detected MIME/signature must resolve to the same allowed family.
- Unknown, unsupported, ambiguous, detector-error, and mismatch outcomes fail closed with `415 mime_mismatch_or_invalid_content`.
- Validation occurs before temporary storage, Document Hub writes, onboarding status changes, or completion audit.
- Validated bytes are reopened through a server-owned temporary file; the upload stream is defensively rewound first.
- This is content-type consistency validation, **not antivirus or malware scanning**.

Accepted mappings: PDF, JPEG, PNG, WEBP, HEIC/HEIF under explicit extension/MIME/signature rules.

## Full verifier result

The expanded matrix contains the original 51 E2 cases plus six previously added supplemental cases (real delivery ladder C03e–C03h and deferred C07k/C07l):

- Original E2 cases: **51/51 pass**
- Supplemental real delivery ladder: **4/4 pass**
- Deferred upload durability/audit cases: **0/2 pass**
- Total: **55/57 pass**

R1 target failures now green:

- C05e, C05g, C05h, C05i
- C07i
- C10c, C10d, C10d2, C10e, C10e2

Safety evidence:

- production protected flags remained OFF
- staging systemd protected flags remained OFF
- production WATHEFNI snapshot unchanged
- protected staging WATHEFNI snapshot unchanged
- P7ESTG01/P7ESTG02 fixtures removed

## C07k / C07l accepted R1 deferral

### C07k — DB failure after successful storage

**What it tests:** Storage succeeds, then the canonical DB receipt transaction fails. The test requires compensating deletion of the permanent object.

**Current behavior:** Database changes roll back and onboarding remains pending, but a local permanent object can remain without a `file_registry` / employee-document row.

**Risk:** **Medium operational/privacy durability risk.** It can create an unindexed retained copy. The verifier found no authorization, tenant-isolation, or protected-document API-access path: no canonical row/file ID exists, so employee/dashboard document endpoints cannot resolve the orphan. The synthetic staging object is removed by verifier cleanup.

**Why it is not an R1 authorization/content-gate blocker:** It does not bypass R1A authorization or R1B content validation and exposes no route-addressable protected document in current evidence. Its R1 deferral was explicitly accepted. However, because the binding rule also requires the complete expanded matrix to pass before declaring staging-green, this failure still prevents that declaration now.

**Proposed R2 scope:** Add provider-aware compensating deletion after post-storage DB failure (local and Drive), idempotent cleanup, a reconciliation scan for historical unindexed objects, and failure-injection tests for each provider.

### C07l — rejected-upload audit

**What it tests:** A rejected employee upload should create a metadata-only `employee_document_upload_rejected` audit event.

**Current behavior:** The request is denied before storage/canonical metadata/completion, but no rejection audit row is written.

**Risk:** **Low-to-medium observability risk.** Security/operations lose denial telemetry; no bytes are stored, onboarding is not completed, and no document access is created. The evidence exposes no authorization or tenant-isolation issue.

**Why it is not an R1 authorization/content-gate blocker:** Rejection itself is fail-closed and leaves canonical state unchanged. Its R1 deferral was explicitly accepted. As with C07k, the unchanged failed assertion means the overall full-matrix staging-green condition is not met.

**Proposed R2 scope:** Write an HR-safe, company/employee-scoped rejection audit containing reason class, normalized extension/MIME, and size only—never bytes, local paths, raw credentials, or activation codes. Add rate/volume controls and verifier assertions.

## Migrations and rollback

- Database migration: none.
- Runtime dependency: `puremagic==2.2.0` installed in the existing orchestrator venv and pinned in `requirements.txt`.
- Future deploys sync `requirements.txt`, require the exact `puremagic==2.2.0` pin, install only that package before restart, and include the requirements/deploy script in the staging-green artifact hash. No production deploy was run for this follow-up.
- Rollback: revert `3f50e8b` then `79a2bf9`; reinstall the prior requirements set if removing `puremagic`. No schema down-migration.
- Revoked/superseded credentials are intentionally not resurrected by rollback.

## Recommendation

Keep Phase 7E open and production-dark. R1 is implemented and verified, but do not declare Phase 7E staging-green or begin Phase 8 while C07k/C07l keep the expanded matrix below 100%.
