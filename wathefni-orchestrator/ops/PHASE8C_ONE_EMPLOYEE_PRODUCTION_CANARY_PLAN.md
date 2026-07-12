# Phase 8C — One-Employee Production Canary Plan and GO Checklist

**Document status:** plan and GO checklist only  
**Date:** 2026-07-12  
**Prerequisite:** Phase 8B production-dark green accepted (`167416b`)  
**Authorization:** This document does **not** authorize module enablement, flag changes, invitations, employee selection, or any production mutation.

**Protected flags (must remain until a separate written GO after this checklist is complete):**

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_ONBOARDING_SEED=off`

**Current GO verdict:** **INCOMPLETE — do not execute**

---

## 0. Production discovery (read-only, 2026-07-12)

| Fact | Evidence |
|------|----------|
| Active companies in production | Exactly one: `WATHEFNI` (`status=active`) |
| Other active client companies | **None** |
| `employee_app` module enabled anywhere | **0** rows |
| Employee-app invites / sessions | `0` / `0` |
| Reconciliation pending / manual_review | `0` / `0` |
| Live `/app/*` while dark | `503 employee_app_disabled` (Phase 8B) |
| Privacy URL `https://wathefni.ai/employee-app/privacy` | Redirects then **404** |
| `WATHEFNI` employees | 3 rows with phones; all `employment_status=null` (not `active`) |
| E1a / 8A pilot label | Still `PROPOSED_PILOT_CO` / TBD — not resolved |

Conclusion: no approved, qualifying one-employee canary target exists yet. Production `WATHEFNI` is **not** automatically the pilot.

---

## 1. Exact existing production pilot company

### Required fields (must be filled before GO)

| Field | Value |
|-------|--------|
| Company code | **UNRESOLVED** — replace `PROPOSED_PILOT_CO` with one existing production code |
| Lifecycle | Must be `active`; `disabled_at` and `archived_at` null |
| Why it qualifies | Must pass Phase 8A §1 criteria 1–15 |
| Not automatic `WATHEFNI` | Confirmed: selection must **not** default to `WATHEFNI` |

### Qualification rules

The pilot company must:

1. Already exist in production (no create/activate in 8C planning).
2. Be lifecycle `active`.
3. Have written client approval for a one-employee canary.
4. Already run the post-hire modules needed for included workflows (`onboarding` at minimum if upload is in scope; `leave` only if already enabled).
5. Have at least one active employee with a unique verified phone and no app invite/session.
6. Accept Option A manual onboarding (seed remains OFF).
7. Accept inbox-only ongoing notifications and shared activation ladder / `hr_task`.
8. Complete privacy readiness (§4) before any invite.
9. **Not** be assumed to be `WATHEFNI`.

### Explicit `WATHEFNI` rule

Production `WATHEFNI` may be used **only** after a separate explicit written decision that:

- names `WATHEFNI` as the pilot company,
- accepts internal support load,
- sets the chosen canary employee to canonical `employment_status='active'`,
- and still completes every owner/privacy/consent blocker below.

Until that written decision exists, treat `WATHEFNI` as **disqualified by policy**, even though it is the only active production company today.

### Current candidate status

| Candidate | Qualifies now? | Reason |
|-----------|----------------|--------|
| Non-`WATHEFNI` client company | **No candidate exists** | Production inventory has no other active company |
| `WATHEFNI` | **No (blocked)** | Automatic selection forbidden; no separate written pilot decision; employees are not `employment_status='active'` |

**Hard blocker:** pilot company unresolved.

---

## 2. Named owners

All three owners must be named, reachable on the activation window, and distinct for HR vs rollback.

| Role | Name | Direct contact | Available during activation? |
|------|------|----------------|------------------------------|
| HR owner | **TBD** | **TBD** | **No — unresolved** |
| Support owner | **TBD** | **TBD** | **No — unresolved** |
| Technical rollback owner | **TBD** | **TBD** | **No — unresolved** |
| GO approver (sign-off) | **TBD** | **TBD** | **No — unresolved** |

Ownership rules:

- HR owns employee selection, consent/notice delivery, Option A checklist rows, invitation action, and first-line employee questions.
- Support owns monitoring cadence, `hr_task` follow-up, incident log, and HR/employee coordination.
- Rollback owns module disable, global kill switch, restart, session/invite revocation proof, and reconciliation drain.
- If any owner becomes unavailable after GO, stop before invite or abort mid-canary per §9.

**Hard blocker:** named owners unresolved.

---

## 3. Exact canary employee

Exactly **one** existing active employee. No second invite. No invented employee.

### Eligibility checklist (all required)

- [ ] Belongs to the approved pilot company only
- [ ] Canonical `employment_status='active'`
- [ ] Unique verified phone belonging to that employee/company
- [ ] No row in `employee_app_invites` for that company+employee (any status that would confuse activation)
- [ ] No row in `employee_sessions` for that company+employee
- [ ] Employee has consented to the production canary
- [ ] Employee has received the approved privacy notice (proof recorded outside git)
- [ ] If onboarding upload is in scope: at least one Option A checklist item manually provisioned before invite

### Selected canary (fill only after blockers clear)

| Field | Value |
|-------|--------|
| Company code | **UNRESOLVED** |
| Employee key | **UNRESOLVED** (record in restricted HR sheet; do not commit PII beyond key if approved) |
| Phone uniqueness verified | **No** |
| Existing invite/session | N/A until selected — production currently `0`/`0` globally |
| Consent recorded | **No** |
| Privacy notice receipt proof | **No** |

### Discovery note (not a selection)

Production currently has three `WATHEFNI` employee keys with phones and `employment_status=null`. None are eligible until:

1. pilot company is approved,
2. status is set to `active` by authorized HR/admin process,
3. consent + notice proof exist,
4. and the employee is explicitly named in the GO packet.

**Hard blocker:** canary employee unresolved. Do not select or invite yet.

---

## 4. Privacy readiness (hard blockers before invite)

| # | Requirement | Status (2026-07-12) |
|---|-------------|---------------------|
| 4.1 | Live role-based contact mailbox (not a personal operator address) | **INCOMPLETE** |
| 4.2 | Published privacy URL at in-app target `https://wathefni.ai/employee-app/privacy` | **INCOMPLETE** — live fetch ends in **404** |
| 4.3 | Approved employee notice for the canary | **INCOMPLETE** |
| 4.4 | Retention / deletion wording approved (pilot SLA) | **INCOMPLETE** |
| 4.5 | Factual subprocessor list for actually deployed infra | **INCOMPLETE** |
| 4.6 | Proof the canary employee received the notice | **INCOMPLETE** |

Any incomplete item above is a **hard stop** before creating an invitation.

Draft mobile policy text may exist under the employee-mobile docs; draft ≠ published, approved, or delivered.

**Hard blocker:** privacy pack incomplete.

---

## 5. Manual onboarding scope

| Rule | Requirement |
|------|-------------|
| Seed | `WATHEFNI_ONBOARDING_SEED` remains **OFF** for the entire canary |
| Provisioning | Explicitly provision only the approved canary checklist item(s) |
| Invented state | Forbidden — no auto-seed, no bulk checklist generation, no synthetic production docs |
| Empty checklist | Means incomplete; never treat as done |
| Upload scope | One approved onboarding upload after activation, against a pre-provisioned `item_id` |
| Leave | Test leave **only if** `leave` is already enabled for the pilot company; do not enable leave for the canary |

Approved canary checklist items (fill after company decision):

| item type / id | Provisioned? | Notes |
|----------------|--------------|-------|
| **TBD** | No | Must be named by HR before invite |

---

## 6. Exact enablement sequence

Execute **only** after GO is complete and a separate written enablement approval exists. Owners must be present for the change window.

Placeholders: `<PILOT_CO>` = approved company code; never substitute `WATHEFNI` without the explicit written exception in §1.

1. **Capture production snapshot**
   - DB / env / artifact snapshot via existing backup path
   - record timestamp, operator, and snapshot path in the incident/canary log
2. **Confirm all protected flags OFF**
   - `WATHEFNI_EMPLOYEE_APP=off`
   - `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
   - `WATHEFNI_ONBOARDING_SEED=off`
3. **Confirm zero non-pilot companies have `employee_app` effective**
   - query all `company_modules` where `module_key='employee_app' AND enabled IS TRUE`
   - require empty set (or only `<PILOT_CO>` after step 4, never others)
4. **Enable `employee_app` for the pilot company only** while global remains OFF
   - write/update `company_modules` for `<PILOT_CO>` only
5. **Prove routes still globally denied**
   - with global OFF, live `/app/me` and `/app/auth/activate` must remain `503 employee_app_disabled` (or equivalent global deny)
6. **Recheck every non-pilot company remains denied**
   - module query: no other company has `employee_app` enabled
7. **Set `WATHEFNI_EMPLOYEE_APP=on`**
   - only after steps 1–6 pass
8. **Restart safely** through the guarded production service path
9. **Prove pilot company allowed and all non-pilot companies denied**
   - pilot lifecycle + module gate passes
   - any non-pilot company identity remains denied
   - if production still has only one company, use a negative control identity / absent company code and confirm deny; do not invent a second tenant
10. **Keep channel accounts and onboarding seed OFF**
    - re-read both flags after restart
    - shared routing must remain `flag_off` / no `channel_route`

Do **not** create the invitation in this section. Invitation is §7.

---

## 7. Canary execution

Only after §6 proofs and §4 privacy proofs.

1. Create **exactly one** invitation for the approved canary employee.
2. Use the existing shared activation ladder and `hr_task` (WhatsApp session → approved template → email fallback → visible `hr_task`). Never invent “delivered.”
3. Activate **exactly one** employee; require one active session, no duplicate active session from activation.
4. Validate:
   - `/app/me` returns the correct company + employee
   - profile is self-scoped
   - inbox is self-scoped
5. Perform **one** approved onboarding upload against the pre-provisioned item.
6. Test leave **only if** already enabled for the company.
7. **No** push dependency and **no** public store dependency.

Stop after the one-employee canary. No cohort expansion in Phase 8C.

---

## 8. Monitoring

### Cadence

| When | Required |
|------|----------|
| Before invite | Yes |
| Immediately after invite | Yes |
| After activation | Yes |
| After upload/workflow | Yes |
| Hourly for the first four hours | Yes |
| Daily through the 48-hour canary window | Yes |

### Exact queries / checks

Replace `<PILOT_CO>` and `<EMP_KEY>` only after GO. Do not run mutating statements.

**Sessions and refresh credentials**

```sql
SELECT session_id, company_code, employee_key, status,
       expires_at, refresh_expires_at, revoked_at, revoked_reason, created_at
FROM employee_sessions
WHERE company_code = '<PILOT_CO>'
ORDER BY created_at DESC;

SELECT count(*) FILTER (WHERE status = 'active') AS active_sessions,
       count(*) FILTER (WHERE status = 'revoked') AS revoked_sessions
FROM employee_sessions
WHERE company_code = '<PILOT_CO>' AND employee_key = '<EMP_KEY>';
```

Expect after successful activation: exactly **one** active session for the canary. After rollback: zero active; refresh must fail.

**Identity and tenant scope**

```sql
SELECT employee_key, company_code, employment_status,
       (COALESCE(phone,'') <> '') AS has_phone
FROM employees
WHERE company_code = '<PILOT_CO>' AND employee_key = '<EMP_KEY>';

SELECT company_code, name, status, disabled_at, archived_at
FROM companies
WHERE company_code = '<PILOT_CO>';
```

API: `/app/me` must return only `<PILOT_CO>` + `<EMP_KEY>`. Inbox/profile must not return other employees.

**Invites**

```sql
SELECT invite_id, company_code, employee_key, status,
       attempts, expires_at, redeemed_at, last_sent_at, created_at
FROM employee_app_invites
WHERE company_code = '<PILOT_CO>'
ORDER BY created_at DESC;
```

Expect exactly one canary invite lifecycle; no second pending invite for the same employee without supersession.

**Delivery status and `hr_task`**

- Inspect activation outbound / `employee_messages` (or equivalent delivery ledger used by the shared ladder) for the invite send.
- Require backend statuses only: created / attempted / delivered / failed / suppressed / fallback.
- If not delivered, require visible `hr_task` (or failed/fallback) — UI must not invent success.

**Onboarding and Document Hub records**

```sql
-- checklist / onboarding items for the canary only (use the project's canonical onboarding tables)
-- Confirm only manually provisioned items exist for <EMP_KEY>.

-- Document Hub / upload linkage for the canary employee after the approved upload
-- Confirm company_code and employee_key match <PILOT_CO>/<EMP_KEY>.
```

Also check `action_results` for `employee_document_uploaded` when the upload path records it.

**Storage reconciliation pending / manual-review**

```sql
SELECT status, count(*) AS n
FROM document_storage_operations
GROUP BY status
ORDER BY status;

SELECT operation_id, company_code, employee_key, item_id, status,
       attempt_count, next_attempt_at, lease_owner, lease_expires_at,
       failure_reason, created_at, updated_at
FROM document_storage_operations
WHERE status IN ('prepared','stored','deleting','compensation_pending','manual_review')
ORDER BY created_at;

SELECT count(*) AS pending
FROM document_storage_operations
WHERE status IN ('prepared','stored','deleting','compensation_pending');

SELECT count(*) AS manual_review
FROM document_storage_operations
WHERE status = 'manual_review';
```

Systemd:

```bash
systemctl is-active wathefni-document-storage-reconcile.timer
systemctl is-enabled wathefni-document-storage-reconcile.timer
systemctl status wathefni-document-storage-reconcile.service --no-pager
```

Expect timer active+enabled; after normal processing, pending and manual_review return to 0 (manual_review related to pilot upload is a stop condition).

**Rejected-upload audit**

```sql
SELECT count(*) AS rejected_audits
FROM action_results
WHERE company_code = '<PILOT_CO>'
  AND action_type = 'employee_document_upload_rejected';

SELECT created_at, action_type, result
FROM action_results
WHERE company_code = '<PILOT_CO>'
  AND action_type = 'employee_document_upload_rejected'
ORDER BY created_at DESC
LIMIT 20;
```

Rejected uploads must remain storage-free (no new durable object for the reject path).

**Non-pilot access denial**

```sql
SELECT company_code, enabled, updated_at
FROM company_modules
WHERE module_key = 'employee_app' AND enabled IS TRUE;
```

Expect only `<PILOT_CO>` after enablement. Live checks: non-pilot identities denied; global deny proofs from §6 retained in the canary log.

**Protected flags and shared routing**

```bash
# From production orchestrator env / drop-in (read-only):
# WATHEFNI_EMPLOYEE_APP
# WATHEFNI_COMPANY_CHANNEL_ACCOUNTS
# WATHEFNI_ONBOARDING_SEED
```

During canary after enablement: employee_app may be `on`; channel accounts and onboarding seed must stay `off`. Shared outbound resolve must remain shared default with `reason=flag_off` and no `channel_route`.

---

## 9. Immediate stop conditions

Stop new invitations and begin rollback (§10) immediately for:

1. Cross-tenant or cross-employee access
2. Wrong identity activation
3. Disabled / lifecycle bypass
4. Credential revival after revoke
5. Duplicate active session from activation
6. Orphaned storage object
7. Unsafe reconciliation delete
8. False delivered status
9. Unexplained repeated `/app/*` 5xx
10. Privacy or owner readiness no longer valid
11. Rollback owner unavailable

Also stop for pressure to enable push, company channel accounts, or onboarding seed to “unstick” the canary.

---

## 10. Rollback

Target: block canary access and new activation within **15 minutes**.

1. **Stop invitations** — HR/support announce stop; no further invites.
2. **Revoke employee access** — use existing revoke / transition hooks for the canary employee.
3. **Disable pilot company module** — `company_modules.employee_app` for `<PILOT_CO>` set disabled; expect session revoke + invite supersession side effects.
4. **Set global flag OFF and restart** — `WATHEFNI_EMPLOYEE_APP=off` via guarded path, then safe restart.
5. **Prove bearer and refresh denial** — old bearer and refresh fail; invites cannot reactivate.
6. **Keep reconciliation worker active until clean** — drain `prepared` / `stored` / `deleting` / `compensation_pending`; inspect `manual_review` without blind delete.
7. **Confirm channel accounts and seed remain OFF**.
8. **Require a new GO decision before retrying** — no re-enable from the incident window.

Rollback does not hard-delete legitimate employee documents or reconciliation truth.

---

## 11. GO checklist

Mark complete only with evidence. Current marks reflect 2026-07-12 discovery.

| # | Gate | Status |
|---|------|--------|
| G1 | Phase 8B production-dark green accepted | **COMPLETE** (`167416b`) |
| G2 | Exact existing pilot company named; lifecycle active | **INCOMPLETE** |
| G3 | Confirmation pilot is not automatic `WATHEFNI` (or separate written `WATHEFNI` exception) | **INCOMPLETE** |
| G4 | HR owner named and available | **INCOMPLETE** |
| G5 | Support owner named and available | **INCOMPLETE** |
| G6 | Technical rollback owner named and available | **INCOMPLETE** |
| G7 | Exact one active canary employee named | **INCOMPLETE** |
| G8 | Unique verified phone; no invite/session | **INCOMPLETE** |
| G9 | Employee consent recorded | **INCOMPLETE** |
| G10 | Live role-based privacy mailbox | **INCOMPLETE** |
| G11 | Privacy URL published (non-404) | **INCOMPLETE** (404 today) |
| G12 | Approved employee notice | **INCOMPLETE** |
| G13 | Retention/deletion wording approved | **INCOMPLETE** |
| G14 | Factual subprocessor list approved | **INCOMPLETE** |
| G15 | Proof employee received notice | **INCOMPLETE** |
| G16 | Option A checklist items named; seed remains OFF | **INCOMPLETE** |
| G17 | Enablement sequence reviewed by rollback owner | **INCOMPLETE** |
| G18 | Monitoring queries assigned to support owner | **INCOMPLETE** |
| G19 | Stop conditions acknowledged by all owners | **INCOMPLETE** |
| G20 | Rollback drill path acknowledged (&lt;15 min) | **INCOMPLETE** |
| G21 | Separate written Phase 8C execution GO | **NOT ISSUED** |

**GO result:** **INCOMPLETE** — no implementation, no production state change, no invite.

---

## 12. Exact unresolved blockers

1. **Pilot company** — no approved existing non-`WATHEFNI` production company; `WATHEFNI` not auto-selected and currently policy-blocked without a separate written decision.
2. **Named owners** — HR, support, and technical rollback owners all TBD / unavailable for activation.
3. **Canary employee** — not selected; no consent; no active employment status on current inventory candidates.
4. **Privacy pack** — mailbox, published URL (404), notice, retention/deletion wording, subprocessors, and receipt proof all incomplete.
5. **Manual onboarding item list** — approved canary checklist items not named.
6. **Execution GO** — not issued; Phase 8C remains plan-only.

---

## Planning guardrails (reconfirmed)

Until a separate Phase 8C execution approval clears every GO item:

- do not enable any module
- do not change protected flags
- do not create invitations
- do not select or message an employee as the canary
- do not create production tenants
- do not enable push, public store, company channel accounts, or onboarding seed
- do not promote Phase 7D routing

Flags remain:

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_ONBOARDING_SEED=off`
