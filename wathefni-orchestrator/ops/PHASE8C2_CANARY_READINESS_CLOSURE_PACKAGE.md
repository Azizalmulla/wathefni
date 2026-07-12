# Phase 8C2 — Canary Readiness Closure Package

**Status:** draft closure package; GO blocked
**Date:** 2026-07-12
**Company decision:** `WATHEFNI`, internal one-employee canary only
**Execution status:** not authorized

This package does not authorize an employee change, onboarding row, module
enablement, global flag change, invitation, session, privacy publication, or
canary execution.

## 1. Phase 8C1 documentation commit

- `c610335` — `docs: record Phase 8C1 canary readiness decision`
- Included file only:
  `wathefni-orchestrator/ops/PHASE8C1_CANARY_READINESS_PACKAGE.md`

## 2. Owner decision sheet

No name, contact, or availability is inferred.

### HR/data owner

- Name: ______________________________
- Title / authority: ______________________________
- Direct contact: ______________________________
- Activation-window availability: ______________________________
- First-four-hours coverage: ______________________________
- Backup name: ______________________________
- Backup contact: ______________________________
- Authority to confirm/correct employee data: yes / no
- Owns company binding, employment status, phone verification, employee
  selection, consent, notice delivery, and onboarding scope: yes / no
- Accepts stop authority: yes / no
- Signed / dated: ______________________________

### Employee-support owner

- Name: ______________________________
- Title / authority: ______________________________
- Direct contact: ______________________________
- Activation-window availability: ______________________________
- First-four-hours coverage: ______________________________
- 48-hour follow-up availability: ______________________________
- Backup name: ______________________________
- Backup contact: ______________________________
- Owns employee guidance, delivery/`hr_task` monitoring, incident logging, and
  escalation: yes / no
- Accepts stop authority: yes / no
- Signed / dated: ______________________________

### Technical-rollback owner

- Name: ______________________________
- Title / authority: ______________________________
- Direct contact: ______________________________
- Activation-window availability: ______________________________
- First-four-hours coverage: ______________________________
- Backup name: ______________________________
- Backup contact: ______________________________
- Has production access for module disable, protected flag rollback, guarded
  restart, credential-denial proof, and reconciliation checks: yes / no
- Accepts the under-15-minute rollback target: yes / no
- Signed / dated: ______________________________

### Role overlap

- Does one person hold multiple roles? yes / no
- Roles overlapped: ______________________________
- Why the overlap is acceptable: ______________________________
- Authority and technical access confirmed by: ______________________________
- Reachable backup confirmed: yes / no
- Support and rollback coverage for first four hours confirmed: yes / no
- Approved by / dated: ______________________________

One person may hold multiple roles only when the overlap is explicit, authority
and access are sufficient, the person is available during activation and
immediate validation, a reachable backup is named, and support plus rollback
coverage remains available for the first four hours.

## 3. Read-only genuine-employee identification procedure

This procedure identifies a candidate; it does not modify or invite one.

1. The HR/data owner selects one genuine internal employee from the
   authoritative Wathefni HR roster.
2. Record the candidate employee key in a restricted readiness record. Do not
   place the employee's phone, notice acknowledgment, or other PII in git.
3. Read the canonical employee row and require:
   - `company_code='WATHEFNI'`;
   - `employment_status='active'`;
   - a non-empty normalized phone; and
   - no conflicting identity fields.
4. Normalize the phone with the application's Kuwait rule (an 8-digit local
   number maps to the `965`-prefixed form).
5. Search all employee rows—not only `WATHEFNI`—for that normalized phone.
   Require exactly one canonical employee.
6. HR independently confirms the employee controls the phone. Do not use an
   employee-app invite as the verification mechanism.
7. Require no employee-app invite for the employee or phone that could
   participate in activation.
8. Require no employee-app session or refresh credential for the employee.
9. Check the company is still active and neither disabled nor archived.
10. Obtain explicit consent only after the versioned notice is approved.
11. Repeat steps 3–9 immediately before any future invitation.

Read-only checks:

```sql
SELECT employee_key, company_code, employment_status,
       (COALESCE(phone, '') <> '') AS has_phone,
       updated_at
FROM employees
WHERE employee_key = '<EMP_KEY>';

SELECT employee_key, company_code, employment_status
FROM employees
WHERE phone = '<NORMALIZED_PHONE>'
ORDER BY company_code, employee_key;

SELECT company_code, status, disabled_at, archived_at
FROM companies
WHERE company_code = 'WATHEFNI';

SELECT invite_id, company_code, employee_key, status, expires_at,
       redeemed_at, created_at
FROM employee_app_invites
WHERE employee_key = '<EMP_KEY>' OR phone = '<NORMALIZED_PHONE>'
ORDER BY created_at DESC;

SELECT session_id, company_code, employee_key, status, expires_at,
       refresh_expires_at, revoked_at, created_at
FROM employee_sessions
WHERE employee_key = '<EMP_KEY>'
ORDER BY created_at DESC;
```

Acceptance evidence:

- HR/data-owner attestation to genuine employment and phone control;
- one canonical `WATHEFNI` employee row;
- explicit active employment;
- global normalized-phone count of exactly one;
- zero participating invites;
- zero sessions/refresh credentials; and
- timestamped query output retained in the restricted readiness record.

## 4. Supported authoritative active-status workflow

If the chosen employee is not explicitly active, do not patch the row directly.

### Confirmed legacy permission behavior — Phase 8C blocker

The deployed permission helper is **not fail-closed**:

```python
def dashboard_context_has_permission(context, permission):
    perms = {str(p) for p in (context.get("permissions") or []) if str(p).strip()}
    if not perms:
        return True
    return str(permission) in perms
```

Read-only production evaluation at
`2026-07-12T11:50:28.488417+00:00` confirmed:

- missing `permissions` key + `settings.manage` request → `true`;
- empty `permissions` list + `settings.manage` request → `true`;
- explicit unrelated permission → `false`; and
- explicit `settings.manage` → `true`.

`require_employee_roster_admin` relies on this helper for employee create,
identity edit, and status change. Although normal dashboard contexts currently
derive a role-based permission list, the helper explicitly grants write
authority when permission metadata is missing or empty. This violates the
Phase 8C binding requirement.

Therefore:

- the current employee status/identity workflow is **not authorized** for the
  canary;
- authenticated dashboard access, legacy operator context, missing permission
  metadata, or company membership must never imply write authority;
- no direct SQL, temporary route, dependency injection, or legacy-token
  workaround is permitted; and
- remediation must be separately approved, made fail-closed, tested in staging,
  deployed through a reviewed change, and reverified before this gate can pass.

### Required authoritative workflow after fail-closed remediation

1. HR/data owner creates an approved correction record containing:
   - employee key and `WATHEFNI` scope;
   - requester and separate or explicitly authorized approver;
   - approved reason;
   - authoritative current state;
   - intended state;
   - full before snapshot or immutable reference to it; and
   - approval timestamp.
2. Operator authenticates with a named dashboard-user identity. A legacy
   operator/service context is not accepted.
3. Authorization evidence must contain an explicit `settings.manage`
   permission. Missing or empty permission metadata must return HTTP 403.
4. The authenticated company scope must be `WATHEFNI`; client-supplied scope
   cannot widen or replace it.
5. Immediately before mutation, read back the employee and reconfirm the
   approved current state, employee key, company binding, and phone.
6. Only then may the supported API operation be used:

```http
POST /dashboard/posthire/employees/<EMP_KEY>/status
Content-Type: application/json

{"status":"active"}
```

7. The mutation must remain tenant-scoped by company and employee key and may
   change only `employment_status` plus `updated_at`.
8. The expected durable audit record is `employee_reactivated`, containing the
   authenticated actor, company, employee target, approved reason/reference,
   requester, approver, and before/after values.
9. The current admin audit is best-effort and occurs after the employee commit.
   A successful API response without a durable `result_id` is a failed gate.
10. Perform independent database and API read-back after the change.
11. Compare the before/after snapshots and prove no unrelated employee field
    changed.

Required authorization and post-change evidence:

```sql
SELECT employee_key, company_code, employment_status, updated_at
FROM employees
WHERE company_code='WATHEFNI' AND employee_key='<EMP_KEY>';

SELECT result_id, action_type, status, company_code,
       actor_user_id, actor_email, actor_phone, actor_role,
       result, created_at
FROM action_results
WHERE company_code='WATHEFNI'
  AND action_type='employee_reactivated'
ORDER BY created_at DESC
LIMIT 10;
```

Evidence packet must include:

- authenticated operator user ID and role;
- explicit `settings.manage`;
- `WATHEFNI` scope from the authenticated session;
- requester, approver, reason, and approval timestamp;
- authoritative before state;
- API response;
- durable `action_results.result_id`;
- independent post-change DB/API read-back; and
- field-level diff proving only `employment_status` and `updated_at` changed.

Application reads currently treat a legacy null employment status as active,
but this canary requires canonical explicit `active`. If name, phone, or another
identity field is genuinely wrong, that is a separate approved correction and
must use a fail-closed employee `PATCH` workflow with its own complete evidence.

No correction is authorized by this package.

## 5. Draft internal-canary employee notice

**Status:** draft for product/privacy approval; do not publish or deliver yet
**Version:** `INTERNAL-CANARY-NOTICE-v1-DRAFT`
**Effective date:** ______________________________

> You are being asked to volunteer for a one-person internal production test of
> the Wathefni Employee App. This is an internal canary, not an external client
> pilot. Participation does not authorize adding another employee or company.
>
> If you agree, Wathefni will use your existing employee identity, name, phone
> number, basic profile information, app authentication/session metadata,
> activation-delivery status, in-app inbox state, and one manually provisioned
> `personal_photo` onboarding item. The test will include one approved photo
> upload. `employment_contract` will be added only if the HR/data owner records
> a genuine operational requirement. Civil ID and bank details are excluded.
>
> The data is used to verify activation, identity and company scoping, profile
> and inbox access, one document upload, auditing, storage reconciliation,
> monitoring, support, and rollback. Push notifications and public app-store
> distribution are not required for this test.
>
> Production infrastructure and the providers listed in the approved provider
> inventory may process the minimum data needed for their function. Depending
> on the activation route, WhatsApp or email delivery providers may process your
> contact details and activation message. The privacy webpage host processes
> ordinary web-request information when you open that page. Encrypted production
> backups may include pilot records and the uploaded file.
>
> Access will be revoked if you withdraw, the canary ends, your employment is no
> longer active, or Wathefni rolls the canary back. Retention, deletion, backup,
> and post-employment treatment are described in the approved internal-canary
> retention statement supplied with this notice.
>
> To ask a question, withdraw, request access revocation, or make a privacy
> request, contact: [ROLE-BASED MAILBOX]. Privacy-request owner:
> [OWNER NAME/ROLE]. Response target: [SLA].
>
> Participation is voluntary for this internal test. Ask questions before
> agreeing. Do not upload any document other than the single approved
> `personal_photo`.
>
> Consent and acknowledgment:
>
> - I received `INTERNAL-CANARY-NOTICE-v1` and the approved retention statement.
> - I understand the internal one-person scope and the data described above.
> - I consent to participate and to the one approved photo upload.
> - I know how to contact the privacy/support mailbox and how to withdraw.
>
> Employee identifier: ______________________________
> Employee signature/recorded acknowledgment: ______________________________
> Date/time: ______________________________
> HR/data-owner witness: ______________________________

This notice intentionally makes no claim of compliance with a named law and
contains no external-client contractual or public-store wording.

## 6. Draft retention, deletion, and post-employment wording

**Status:** operational draft; product owner must approve the bracketed values
and ensure they match actual backup/provider behavior before publication.

### Access and credentials

- Pending invites, active sessions, refresh credentials, and push tokens (if
  any unexpectedly exist) are revoked when the employee withdraws, the canary
  is rolled back or closed, or employment ceases to be active.
- Revocation blocks future app access; it does not itself erase canonical HR or
  audit records.

### Pilot authentication, delivery, and audit records

- Invite, session, delivery, `hr_task`, incident, and audit metadata is retained
  for `[PILOT_OPERATIONAL_RETENTION_DAYS]` days after canary closure, unless an
  incident requires a documented hold.
- Activation codes, bearer tokens, refresh tokens, and document bytes must not
  be copied into readiness or incident logs.

### Personal-photo upload

- The canonical photo and Document Hub metadata are retained until
  `[PHOTO_RETENTION_TRIGGER/DATE]`.
- At that point the HR/data owner decides whether the photo remains a legitimate
  HR record or is approved for deletion.
- Authorized deletion must reconcile canonical metadata, storage operations,
  and the storage object. No blind object deletion is permitted.

### Deletion requests

- The in-app deletion request creates an auditable HR task; it is not an
  automatic hard delete.
- The named privacy-request owner records the request, verifies identity,
  identifies records subject to operational or HR retention, approves the
  disposition, and records completion.
- Access revocation occurs separately and is not delayed by a longer record
  review.

### Post-employment treatment

- When employment is no longer active, employee-app access and credentials are
  revoked immediately through the supported lifecycle workflow.
- The employee can no longer access the app, inbox, checklist, or document.
- Canonical employment/document records are retained or deleted only according
  to the approved HR retention decision; the app does not silently erase them.

### Backups

- Production backups include database and workspace/document data and are sent
  offsite as encrypted bundles.
- Local backup rotation is configured for seven daily and four weekly copies.
- Read-only B2 evidence captured on 2026-07-12 confirmed:
  - private bucket in `us-east-005`;
  - lifecycle hides objects 45 days after upload and deletes hidden objects one
    day later;
  - configured maximum persistence target is therefore approximately 46 days,
    plus any provider lifecycle-processing delay;
  - file lock/default retention is disabled;
  - B2 replication source and destination are both disabled;
  - rclone hard-delete is disabled; and
  - the latest scheduled offsite push completed successfully.
- Deletion from the live system may remain in encrypted backups until that
  lifecycle expires. Restoring an older backup requires reapplying approved
  deletions before normal service resumes.
- The canary photo's primary provider is the local production filesystem. After
  the next successful backup, the file will also be present inside the encrypted
  B2 bundle; it is not uploaded as an independently reconciled B2 document.
- Document-storage reconciliation operates on the live local object and
  canonical records. It does not delete historical encrypted B2 bundles.
- Confirmed additional copies are: the live local object, seven local daily
  backups, four local weekly backups, local encrypted offsite bundles, and B2.
  B2-side replication is disabled. Any Hostinger account-level snapshot or other
  provider-side replica is not visible from the server and requires account-owner
  confirmation.

Required final inputs:

- operational metadata retention days;
- personal-photo retention trigger;
- privacy-request response target;
- any incident/legal hold rule;
- product acceptance of the verified B2 lifecycle/maximum-persistence wording;
- confirmation of whether Hostinger account-level snapshots exist; and
- approving product/privacy owner and date.

## 7. Factual production provider inventory

Read-only evidence was collected on 2026-07-12. This is a technical inventory,
not a legal-role determination.

| Provider | Classification | Canary processing status |
|----------|----------------|--------------------------|
| Hostinger | Confirmed infrastructure provider | Yes |
| Backblaze B2 | Confirmed encrypted-backup provider | Yes, after scheduled backup |
| AI Octopus | Confirmed external shared-messaging provider | Conditional on WhatsApp rung |
| 360dialog | Conditional downstream provider | Unverified; do not list as confirmed |
| Meta / WhatsApp | Conditional downstream/network provider | Unverified route; do not list as confirmed |
| Postmark | Confirmed configured email provider | Conditional on email fallback |
| Vercel | Confirmed privacy-page host | Web-request metadata when page is opened |
| Healthchecks.io | Confirmed operational provider | No employee/pilot content |

### Providers that will or may process internal-canary data

1. **Hostinger — CONFIRMED**
   - Production API host resolves directly to `76.13.63.68`, in Hostinger
     AS47583.
   - PostgreSQL is local to the VPS (`127.0.0.1`).
   - Active document provider for `WATHEFNI` is `local`; the photo therefore
     resides on the same production host unless configuration is separately
     changed.
   - Data: identity, phone, HR/profile data, credentials and session metadata,
     inbox/delivery records, audit/reconciliation records, and uploaded photo.

2. **Backblaze B2 — CONFIRMED**
   - The production backup timer is active and enabled.
   - Its configured rclone remote type is `b2`.
   - Bucket is private in region `us-east-005`.
   - Lifecycle: hide 45 days after upload; delete one day after hide. Configured
     maximum persistence target: approximately 46 days plus provider processing
     delay.
   - File lock/default retention and B2 replication are disabled.
   - rclone hard-delete is disabled; routine upload uses `copy`, while lifecycle
     performs expiry.
   - Encrypted offsite bundles include database, workspace/files, media,
     configuration, and encrypted secrets.
   - Data: encrypted copies of pilot database records and the uploaded photo
     after the next successful backup.
   - The photo remains a local primary object; application reconciliation or
     deletion does not remove historical encrypted backup bundles.

3. **AI Octopus — CONFIRMED external shared-messaging provider**
   - Timestamped production configuration evidence captured at
     `2026-07-12T11:50:28.488417+00:00` confirms the shared account points to
     `app.ai-octopus.com` and has configured credentials. No token or credential
     value was captured.
   - It processes canary data only if the shared WhatsApp session is selected by
     the existing activation ladder.
   - Wathefni sends the recipient phone, conversation ID, and text payload to
     its `/client/conversation/reply` API.
   - Company channel accounts remain OFF; this is the shared platform route.
   - Data when used: phone number, activation message/code, delivery metadata,
     and ordinary communications metadata.

4. **360dialog and Meta / WhatsApp — CONDITIONAL downstream**
   - The delivery-layer code documents the downstream chain as
     `Wathefni -> Octopus -> 360dialog`; Meta/WhatsApp is the messaging network.
   - Local production configuration does not expose or prove the downstream
     provider. They are not confirmed subprocessors in this package.
   - Before invitation readiness, product/operations must obtain timestamped
     non-secret route evidence from the selected AI Octopus account confirming
     the actual downstream provider(s).
   - Wathefni does not call 360dialog or Meta directly. Product/operations must
     confirm the deployed downstream chain before approving provider wording.
   - Data when used: phone number, activation message/code, and communications
     and delivery metadata.

5. **Postmark — CONFIRMED configured; processing CONDITIONAL**
   - Production resolves `postmark` as the live outbound email provider;
     fallback is enabled and Postmark credentials are configured.
   - Conditional on the email fallback being used.
   - Data when used: employee email address, activation message/code, sender
     details, and delivery/bounce metadata.

6. **Vercel — CONFIRMED privacy-page host**
   - The exact privacy URL is currently served by Vercel, although its final
     response is HTTP 404.
   - When the employee opens the published page, Vercel processes ordinary web
     request metadata such as IP address, request headers, path, and timestamp.
   - It should not receive the employee HR record, activation code, or uploaded
     photo through this page.

### Operational provider not receiving pilot content

7. **Healthchecks.io — CONFIRMED operational-only**
   - Production uptime timer is active/enabled and a Healthchecks endpoint is
     configured.
   - It receives a health/dead-man ping, not employee identity, activation
     content, or uploaded documents.

### Configured or available but excluded from this canary

- **Google Drive:** a folder is configured, but the effective `WATHEFNI`
  document provider is `local` with local fallback. Do not list Google Drive as
  processing the canary photo unless the effective provider changes—which is
  not authorized.
- **Expo / Apple Push Notification service / Firebase Cloud Messaging:** push
  is excluded; no Expo token was present in the production orchestrator process.
- **Google/Gmail outbound:** production email resolves to Postmark, not Gmail.
- **AI model providers:** no OpenAI, Anthropic, or Voyage key was present in the
  production orchestrator process used for this check, and the scoped employee
  app canary does not require an LLM. Do not send canary data to an AI provider.
- **Public app stores:** excluded.
- **Company-owned WhatsApp channel accounts:** protected flag remains OFF.

The product owner must approve the factual inventory and confirm account names,
provider regions where relevant, the B2 lifecycle, and AI Octopus's current
downstream WhatsApp chain. No additional provider may be introduced during the
canary without a new review.

## 8. Privacy URL and mailbox requirements

### URL

- Exact in-app URL:
  `https://wathefni.ai/employee-app/privacy`
- Current evidence: apex returns HTTP 307 to
  `https://www.wathefni.ai/employee-app/privacy`; final response is HTTP 404
  from Vercel.
- Required before invite:
  - effective response after redirects is HTTP 200;
  - approved internal-canary notice and retention/provider wording are visible;
  - no draft marker, placeholder contact, or unapproved legal claim;
  - HTTPS is valid;
  - English/Arabic availability is stated by the product owner; and
  - version and last-updated date match the notice supplied to the employee.

Acceptance check:

```bash
curl -sS -L -o /dev/null \
  -w '%{http_code} %{url_effective}\n' \
  https://wathefni.ai/employee-app/privacy
```

Required result: final HTTP `200` at the approved page.

### Mailbox

- Exact address: ______________________________
- Must be role-based, not a personal operator mailbox.
- Named privacy-request owner: ______________________________
- Primary monitor: ______________________________
- Backup monitor: ______________________________
- Monitoring hours / activation coverage: ______________________________
- Response target: ______________________________
- MFA/access-control confirmation: ______________________________
- Inbound test received at: ______________________________
- Response test completed at: ______________________________
- Request/audit tracking location: ______________________________

The mailbox must be monitored before the notice is approved or delivered.

## 9. Updated GO checklist

1. **Complete:** Phase 7E staging-green closure.
2. **Complete:** Phase 8B production-dark green.
3. **Complete:** Phase 8C plan commit `a2971c0`.
4. **Complete:** Phase 8C1 documentation commit `c610335`.
5. **Complete:** product selected `WATHEFNI` for one internal employee only,
   not the external pilot, with no automatic expansion.
6. **Blocked:** employee-management permission behavior is fail-open when
   permission metadata is missing or empty.
7. **Blocked:** exact employee reactivation workflow does not yet prove all
   required authorization/change-control evidence. Current audit is best-effort
   and lacks guaranteed reason, requester, approver, before/after values, and a
   required durable audit identifier.
8. **Incomplete:** HR/data owner fields and acknowledgment.
9. **Incomplete:** employee-support owner fields and acknowledgment.
10. **Incomplete:** technical-rollback owner fields and acknowledgment.
11. **Incomplete:** any role overlap and reachable backups.
12. **Incomplete:** exact genuine internal employee.
13. **Incomplete:** authoritative active status and company-binding proof.
14. **Incomplete:** global unique-phone and phone-control proof.
15. **Incomplete:** selected-employee zero-invite/zero-session proof.
16. **Incomplete:** versioned notice approval.
17. **Incomplete:** explicit consent and acknowledgment.
18. **Incomplete:** retention/deletion/post-employment values and approval.
19. **Complete technical B2 evidence / incomplete product acceptance:** private
    `us-east-005`, hide after 45 days, delete one day after hide, no file lock,
    no B2 replication, latest offsite push successful.
20. **Complete:** AI Octopus is confirmed as the external shared-messaging
    provider, with timestamped non-secret production configuration evidence.
21. **Blocked:** actual AI Octopus downstream provider route is not exposed in
    local configuration; 360dialog and Meta remain conditional, not confirmed.
22. **Incomplete:** account-owner confirmation of any Hostinger snapshots or
    other provider-side replicas.
23. **Blocked:** privacy URL final response is HTTP 404, not 200.
24. **Incomplete:** exact monitored role mailbox and privacy-request owner.
25. **Incomplete:** HR/data owner approval of `personal_photo` only; decision on
    whether `employment_contract` has a genuine operational requirement.
26. **Complete as boundary:** seed remains OFF; manual provisioning and one
    upload only; `civil_id` and `bank_details` excluded.
27. **Blocked:** separate Phase 8C execution GO.

Overall: **BLOCKED; canary execution is not authorized.**

## 10. Exact remaining blockers

1. Fail-open legacy permission behavior in
   `dashboard_context_has_permission`.
2. No fail-closed employee status/identity workflow with explicit permission.
3. Current reactivation mutation and best-effort audit do not guarantee the
   complete approved reason/requester/approver/before/after/durable-ID evidence.
4. Named owners, backups, role overlap, and availability.
5. Exact genuine employee and authoritative eligibility evidence.
6. Unique verified phone and zero invite/session proof.
7. Approved notice, explicit consent, and acknowledgment evidence.
8. Monitored role mailbox and named privacy-request owner.
9. Privacy URL still returns final HTTP 404.
10. Final retention/deletion/post-employment values and product approval of the
    verified B2 wording.
11. Actual timestamped AI Octopus downstream route; 360dialog/Meta remain
    conditional until proven.
12. Account-owner confirmation of any Hostinger snapshots/additional replicas.
13. HR/data approval of `personal_photo` and decision on whether
    `employment_contract` is genuinely required.
14. Separate execution GO.

## 11. Exact product-owner inputs required

1. Fill and approve all owner fields, role overlap, backups, and availability.
2. Approve the exact genuine internal employee after HR evidence.
3. Approve `INTERNAL-CANARY-NOTICE-v1` and its effective date.
4. Supply the exact role-based mailbox.
5. Name the privacy-request owner and response target.
6. Approve:
   - pilot operational metadata retention days;
   - personal-photo retention trigger;
   - deletion-request workflow;
   - post-employment treatment;
   - incident/hold rule; and
   - acceptance of the verified B2 persistence wording.
7. Approve the provider inventory; obtain non-secret evidence of AI Octopus's
   current downstream route and confirm whether Hostinger snapshots exist.
8. Approve publication content and owner; publication itself remains a separate
   action and is not authorized here.
9. Confirm whether the privacy page requires English, Arabic, or both for the
   internal employee.
10. Approve `personal_photo` as the only initial item.
11. State whether `employment_contract` has a genuine operational requirement;
    default is excluded.
12. Approve the consent and acknowledgment capture method.
13. Issue a separate execution GO only after all readiness evidence is accepted.

## 12. No-change confirmation

Preparation of this package made no production mutation:

- no employee was selected or modified;
- no onboarding row was created;
- no company module was enabled;
- no protected flag was changed;
- no invitation or session was created;
- no privacy content was published;
- no routing was installed or changed; and
- Phase 7D, push, store, payroll, assessments, and onboarding seed were untouched.
