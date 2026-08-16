# Phase 8C — Final Canary GO Package

**Status:** execution-ready checklist; **NO-GO until human/privacy blockers clear and a separate final GO is issued**  
**Date:** 2026-07-12  
**Pilot company (approved by Phase 8C1):** `WATHEFNI` — internal one-employee canary only  
**Security baseline:** Phase 8C2-R1E production fail-closed green accepted  
**This package does not authorize canary execution.**

References:

- Phase 8C plan: `ops/PHASE8C_ONE_EMPLOYEE_PRODUCTION_CANARY_PLAN.md`
- Phase 8C1 company decision: `ops/PHASE8C1_CANARY_READINESS_PACKAGE.md`
- Phase 8C2 readiness closure: `ops/PHASE8C2_CANARY_READINESS_CLOSURE_PACKAGE.md`
- R1E cutover record: `ops/PHASE8C2_R1E_PRODUCTION_CUTOVER_RECORD.md`
- Fail-closed fallback: `ops/PHASE8C2_R1D_FAIL_CLOSED_FALLBACK.md`

---

## 0. What is already complete (not a blocker)

| Item | Status |
|---|---|
| Phase 8B production-dark green | COMPLETE |
| Explicit written decision that pilot company is `WATHEFNI` | COMPLETE (Phase 8C1) |
| Fail-closed dashboard permission authority (R1A) | COMPLETE |
| Atomic employee status workflow wiring (R1B) | COMPLETE (staging mutation proof + prod schema/contract) |
| `hr_task_only` activation handoff (R1C) | COMPLETE (gated; unused) |
| Production security cutover (R1E) | COMPLETE |
| Global / module flags currently OFF | **Intentional hold state** — changed only during approved execution |

Do **not** treat the following as readiness blockers:

- `WATHEFNI_EMPLOYEE_APP=off`
- company `employee_app` module disabled

---

## 1. Exact pilot identity (public fields only)

| Field | Value |
|---|---|
| Company | `WATHEFNI` |
| Canary employee key | **RESTRICTED** — store only in the private readiness record / ops vault. Do **not** commit the key, phone, name, or activation material to git. |
| Placeholder used below | `<EMP_KEY>` |
| Onboarding scope | **`personal_photo` only** |
| Excluded unless separately documented | `employment_contract`, `civil_id`, `bank_details` |
| Activation mode | `hr_task_only` (no external messaging) |
| Push | OFF |
| Company channel accounts | OFF |
| Onboarding seed | OFF |

---

## 2. Named owners (must be filled before GO)

### HR/data owner

| Field | Value |
|---|---|
| Name | ______________________________ |
| Title / authority | ______________________________ |
| Direct contact | ______________________________ |
| Backup name / contact | ______________________________ |
| Activation-window availability | ______________________________ |
| First-four-hours coverage | ______________________________ |
| Owns employee selection, status/phone proof, consent, notice, onboarding scope | yes / no |
| Stop authority accepted | yes / no |
| Signed / dated | ______________________________ |

### Employee-support owner

| Field | Value |
|---|---|
| Name | ______________________________ |
| Title / authority | ______________________________ |
| Direct contact | ______________________________ |
| Backup name / contact | ______________________________ |
| Activation-window availability | ______________________________ |
| First-four-hours + 48h follow-up coverage | ______________________________ |
| Owns guidance, `hr_task` monitoring, incident log, escalation | yes / no |
| Stop authority accepted | yes / no |
| Signed / dated | ______________________________ |

### Technical-rollback owner

| Field | Value |
|---|---|
| Name | ______________________________ |
| Title / authority | ______________________________ |
| Direct contact | ______________________________ |
| Backup name / contact | ______________________________ |
| Activation-window availability | ______________________________ |
| First-four-hours coverage | ______________________________ |
| Has prod access for module disable, flag rollback, restart, deny proofs, reconciliation | yes / no |
| Accepts under-15-minute rollback target | yes / no |
| Signed / dated | ______________________________ |

Role overlap (if any): roles overlapped ______ ; why acceptable ______ ; backup reachable yes/no ______ .

---

## 3. Privacy / notice / mailbox proof

| # | Requirement | Current status | Evidence location |
|---|---|---|---|
| P1 | Privacy URL `https://wathefni.ai/employee-app/privacy` returns final HTTP **200** | **COMPLETE** (2026-07-12 live check → 200 at `https://www.wathefni.ai/employee-app/privacy`) | Live curl + page content |
| P2 | Monitored role-based privacy/support mailbox (not a personal address) | **INCOMPLETE** | Private ops log |
| P3 | Named privacy-request owner + response target/SLA | **INCOMPLETE** | Private ops log |
| P4 | Versioned internal-canary notice finalized (not draft) | **INCOMPLETE** — draft `INTERNAL-CANARY-NOTICE-v1-DRAFT` exists in 8C2 package | Notice file + SHA-256 outside git or hashed in private record |
| P5 | Retention / deletion / post-employment wording approved with concrete values | **INCOMPLETE** — draft brackets remain | Private approval record |
| P6 | Factual provider inventory approved for deployed infra | **INCOMPLETE** | Private approval record |
| P7 | Explicit employee consent + notice acknowledgment | **INCOMPLETE** | Restricted readiness record only |
| P8 | HR/data approval that onboarding item is **only** `personal_photo` | **INCOMPLETE** | Restricted readiness record |

Proof commands after publication (no PII):

```bash
curl -sS -o /dev/null -w '%{http_code} %{url_effective}\n' -L https://wathefni.ai/employee-app/privacy
# require final HTTP 200
```

---

## 4. Employee eligibility proof (restricted evidence only)

Run read-only. Store outputs in the **private** readiness record. Do not paste phone or name into git.

```sql
-- company binding + active status
SELECT employee_key, company_code, employment_status,
       (COALESCE(phone, '') <> '') AS has_phone, updated_at
FROM employees
WHERE employee_key = '<EMP_KEY>';

-- expect: company_code='WATHEFNI', employment_status='active', has_phone=true

-- global unique phone (use NORMALIZED phone from private record)
SELECT employee_key, company_code, employment_status
FROM employees
WHERE phone = '<NORMALIZED_PHONE>'
ORDER BY company_code, employee_key;
-- expect: exactly one row, the canary

SELECT company_code, status, disabled_at, archived_at
FROM companies
WHERE company_code = 'WATHEFNI';
-- expect: active; disabled_at/archived_at null

SELECT invite_id, company_code, employee_key, status, expires_at, redeemed_at, created_at
FROM employee_app_invites
WHERE employee_key = '<EMP_KEY>' OR phone = '<NORMALIZED_PHONE>'
ORDER BY created_at DESC;
-- expect: zero participating invites

SELECT session_id, company_code, employee_key, status, expires_at,
       refresh_expires_at, revoked_at, created_at
FROM employee_sessions
WHERE employee_key = '<EMP_KEY>'
ORDER BY created_at DESC;
-- expect: zero sessions
```

HR/data owner must separately attest phone control. Do **not** use an app invite as phone verification.

| Eligibility item | Status |
|---|---|
| Exact one genuine internal `WATHEFNI` employee selected | **INCOMPLETE** |
| Authoritative `employment_status=active` | **INCOMPLETE** |
| Company binding `WATHEFNI` | **INCOMPLETE** until selected |
| Unique verified phone | **INCOMPLETE** |
| Zero invite / session | Production currently global `0/0`, but must be re-proven for `<EMP_KEY>` immediately before invite |

---

## 5. Approved onboarding item

| Item | Approved? | Notes |
|---|---|---|
| `personal_photo` | **Pending HR/data sign-off** | Only allowed canary upload |
| `employment_contract` | **Not in scope** | Require separate documented operational need |
| `civil_id` | **Not in scope** | Forbidden for this canary |
| `bank_details` | **Not in scope** | Forbidden for this canary |

Seed remains OFF. Create the one manual onboarding row only during the approved execution sequence (step 3).

---

## 6. Final GO checklist

Mark complete only with evidence.

| # | Gate | Status |
|---|---|---|
| G1 | Phase 8B production-dark green | **COMPLETE** |
| G2 | Pilot company = `WATHEFNI` (Phase 8C1 written decision) | **COMPLETE** |
| G3 | R1E fail-closed production security cutover accepted | **COMPLETE** |
| G4 | HR/data owner + backup + availability | **INCOMPLETE** |
| G5 | Support owner + backup + availability | **INCOMPLETE** |
| G6 | Rollback owner + backup + availability | **INCOMPLETE** |
| G7 | Exact one employee key recorded privately | **INCOMPLETE** |
| G8 | Active status + company + unique phone proof | **INCOMPLETE** |
| G9 | Zero invite/session proof for that employee | **INCOMPLETE** |
| G10 | Privacy URL HTTP 200 | **COMPLETE** (live 200 on 2026-07-12) |
| G11 | Role mailbox + privacy-request owner | **INCOMPLETE** |
| G12 | Notice version/hash finalized | **INCOMPLETE** |
| G13 | Retention/deletion/post-employment wording approved | **INCOMPLETE** |
| G14 | Provider inventory approved | **INCOMPLETE** |
| G15 | Explicit consent + acknowledgment evidence | **INCOMPLETE** |
| G16 | Onboarding scope = `personal_photo` only | **INCOMPLETE** |
| G17 | Owners acknowledge enablement / monitor / stop / rollback | **INCOMPLETE** |
| G18 | Separate final execution GO issued | **NOT ISSUED** |

**Current recommendation: NO-GO**

---

## 7. Execution sequence (do not run until separate final GO)

Keep placeholders; never commit activation codes or employee PII.

### 7.1 Capture production snapshot

```bash
/usr/local/bin/backup-wathefni daily
ts=$(date -u +%Y%m%dT%H%M%SZ)
snap=/opt/wathefni/backups/phase8c-canary-pre-$ts
mkdir -p "$snap"
tar --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  -czf "$snap/orchestrator.tgz" -C /opt/wathefni/orchestrator .
printf '%s\n' "$snap" > /opt/wathefni/backups/.last-phase8c-canary-pre
```

### 7.2 Confirm protected flags OFF and zero non-pilot modules

```bash
systemctl show wathefni-orchestrator.service -p Environment --value \
  | tr ' ' '\n' | grep -E 'WATHEFNI_(EMPLOYEE_APP|COMPANY_CHANNEL_ACCOUNTS|ONBOARDING_SEED)='
# expect all =off
```

```sql
SELECT company_code, enabled, updated_at
FROM company_modules
WHERE module_key = 'employee_app' AND enabled IS TRUE;
-- expect: zero rows
```

### 7.3 Manually create the one approved onboarding row

Use the supported dashboard/admin onboarding path for `<EMP_KEY>` with item type **`personal_photo` only**.  
Do not enable seed. Do not create other item types.

### 7.4 Enable `employee_app` for `WATHEFNI` only (global flag still OFF)

```sql
INSERT INTO company_modules (company_code, module_key, enabled, config, updated_at)
VALUES ('WATHEFNI', 'employee_app', TRUE, '{"source":"phase8c_canary"}'::jsonb, NOW())
ON CONFLICT (company_code, module_key)
DO UPDATE SET enabled = TRUE, updated_at = NOW();
```

### 7.5 Prove routes remain globally denied

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/app/me
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/app/auth/activate
# expect global deny (503 employee_app_disabled or equivalent)
```

### 7.6 Set global flag ON and restart

```bash
# via the guarded production systemd drop-in / EnvironmentFile path used by ops
# set WATHEFNI_EMPLOYEE_APP=on
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
sleep 3
curl -sS http://127.0.0.1:8010/health
# re-confirm channel accounts + onboarding seed still OFF
```

### 7.7 Prove `WATHEFNI` allowed; every other company denied

```sql
SELECT company_code, enabled
FROM company_modules
WHERE module_key = 'employee_app' AND enabled IS TRUE;
-- expect only WATHEFNI
```

Use a non-pilot / absent company control identity and confirm deny. Do not invent a second live tenant.

### 7.8 Create exactly one `hr_task_only` invite

```http
POST /dashboard/posthire/employees/<EMP_KEY>/app-invite
Authorization: Bearer <reviewed_dashboard_session>
Content-Type: application/json

{"delivery_mode":"hr_task_only"}
```

Expect: one HR task; zero external provider calls; raw code returned once with `Cache-Control: no-store`; hash-only persistence.

### 7.9 Secure handoff

Hand the activation code to the employee out-of-band. Keep code in memory only on the operator side. Do not log, commit, email publicly, or store in git.

### 7.10 Activate and verify

- Activate once
- `/app/me` = `WATHEFNI` + `<EMP_KEY>`
- profile + inbox self-scoped
- one `personal_photo` upload against the pre-provisioned item
- no push dependency

### 7.11 Monitor

Hourly for four hours, then through the 48-hour window using §8 queries.

---

## 8. Monitoring queries

```sql
-- sessions
SELECT count(*) FILTER (WHERE status = 'active') AS active_sessions,
       count(*) FILTER (WHERE status = 'revoked') AS revoked_sessions
FROM employee_sessions
WHERE company_code = 'WATHEFNI' AND employee_key = '<EMP_KEY>';

-- invites
SELECT invite_id, status, delivery_mode, expires_at, redeemed_at, created_at
FROM employee_app_invites
WHERE company_code = 'WATHEFNI' AND employee_key = '<EMP_KEY>'
ORDER BY created_at DESC;

-- modules
SELECT company_code, enabled, updated_at
FROM company_modules
WHERE module_key = 'employee_app' AND enabled IS TRUE;

-- storage reconciliation
SELECT status, count(*) AS n
FROM document_storage_operations
GROUP BY status
ORDER BY status;

SELECT count(*) AS pending
FROM document_storage_operations
WHERE status IN ('prepared','stored','deleting','compensation_pending');

SELECT count(*) AS manual_review
FROM document_storage_operations
WHERE status = 'manual_review';
```

```bash
systemctl is-active wathefni-document-storage-reconcile.timer
systemctl show wathefni-orchestrator.service -p Environment --value \
  | tr ' ' '\n' | grep -E 'WATHEFNI_(EMPLOYEE_APP|COMPANY_CHANNEL_ACCOUNTS|ONBOARDING_SEED)='
```

Immediate stop conditions: cross-tenant/cross-employee access; wrong identity; credential revival; orphaned storage; false delivered; unexplained `/app/*` 5xx; owner unavailability; pressure to enable push/channel accounts/seed.

---

## 9. Rollback commands (target < 15 minutes)

```bash
# 1) Stop new invites (operational announcement)

# 2) Disable company module
# SQL:
# UPDATE company_modules
# SET enabled=FALSE, updated_at=NOW()
# WHERE company_code='WATHEFNI' AND module_key='employee_app';

# 3) Global kill switch + restart
# set WATHEFNI_EMPLOYEE_APP=off via guarded env path
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service

# 4) Prove deny
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/app/me

# 5) Confirm channel accounts + seed remain OFF
systemctl show wathefni-orchestrator.service -p Environment --value \
  | tr ' ' '\n' | grep -E 'WATHEFNI_(COMPANY_CHANNEL_ACCOUNTS|ONBOARDING_SEED)='

# 6) Keep reconciliation active until pending drains; inspect manual_review without blind deletes
```

Revoke canary sessions/invites through supported revoke paths. Do **not** restore the pre-R1E fail-open artifact. Do not hard-delete legitimate HR documents to “clean up.”

Require a new GO before any retry.

---

## 10. Completed vs incomplete human/privacy fields

### Completed

- Pilot company named: `WATHEFNI`
- Security remediations R1A–R1E accepted
- Activation mode fixed: `hr_task_only`
- Onboarding item **policy** constrained to `personal_photo` (sign-off still required)
- Protected non-canary flags policy confirmed
- Execution and rollback sequences documented

### Incomplete (must clear before final GO)

1. Named HR/data, support, and rollback owners (+ backups + activation-window availability)
2. Exact genuine employee key selected and stored privately
3. Authoritative active status / company / unique phone / zero invite-session proofs
4. Privacy URL HTTP 200
5. Monitored role mailbox + privacy-request owner
6. Final notice version/hash + retention wording + provider inventory
7. Explicit consent and acknowledgment evidence
8. Explicit HR approval that the provisioned item is only `personal_photo`
9. Separate final execution GO

---

## 11. Exact remaining blockers

1. Name HR/data owner, support owner, rollback owner, with backups and activation-window availability.
2. Select exactly one genuine `WATHEFNI` internal employee (key outside public git).
3. Prove authoritative `employment_status=active`, company binding, unique verified phone, zero existing invite/session.
4. Publish privacy URL and prove HTTP 200.
5. Confirm monitored role-based privacy/support mailbox.
6. Finalize versioned notice, retention/deletion/post-employment wording, and factual provider inventory.
7. Obtain explicit employee consent and notice acknowledgment.
8. Approve manual onboarding scope as `personal_photo` only.

**Not blockers:** `WATHEFNI_EMPLOYEE_APP=off` and disabled company `employee_app` module.

---

## 12. Final recommendation

**NO-GO for canary execution.**

Engineering/security gates for the one-employee canary are ready. Human, privacy, consent, employee-selection, and onboarding-approval gates are not. Do not execute §7 until a separate final GO clears every incomplete item above.

**Confirmation:** no canary execution occurred while preparing this package. No production employee, invite, session, onboarding row, module, flag, privacy publication, or activation code was created or changed for Phase 8C canary purposes.
