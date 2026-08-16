# Phase 8C — Editable privacy and readiness materials

**Status:** drafts for owner completion only  
**Date:** 2026-07-12  
**Pilot company:** `WATHEFNI` (internal one-employee canary)  
**Does not authorize:** privacy publication, mailbox creation, flag/module changes, employee mutation, invite, session, activation, or canary execution

Fill every `[BRACKET]` field. Keep employee PII, phone, consent signatures, and activation material in the **private** evidence file — not in git.

Companion GO package: `ops/PHASE8C_CANARY_GO_PACKAGE.md`

---

## 1. Internal-canary privacy notice (draft)

**Version:** `INTERNAL-CANARY-NOTICE-v1`  
**Effective date:** `[YYYY-MM-DD]`  
**Notice SHA-256 (after finalization):** `[COMPUTE_AND_RECORD_PRIVATELY]`

You are invited to volunteer for a one-person internal production test of the Wathefni Employee App. This is an internal canary for `WATHEFNI` only. It does not authorize adding another employee or company.

If you agree, Wathefni will use:

- your existing employee identity, name, and phone number
- basic profile information
- app authentication and session metadata
- one HR handoff of an activation code (`hr_task_only`; no WhatsApp/email send for activation)
- in-app inbox state
- one manually provisioned `personal_photo` onboarding item and one approved photo upload

This canary does **not** require push notifications, public app-store distribution, company-owned messaging channels, or onboarding auto-seed.

Data is used only to verify activation, company/employee scoping, profile and inbox access, one photo upload, auditing, storage reconciliation, monitoring, support, and rollback.

Confirmed infrastructure that may process canary data is listed in §4. Opening the privacy page may cause the page host to process ordinary web-request metadata. Encrypted production backups may include pilot records and the uploaded photo after the next successful backup.

Access will be revoked if you withdraw, the canary ends, your employment is no longer active, or Wathefni rolls the canary back. Retention, deletion, backup, and post-employment treatment are described in §3 and supplied with this notice.

To ask a question, withdraw, request access revocation, or make a privacy request, contact:

- Mailbox: `[ROLE_BASED_MAILBOX]`
- Privacy-request owner: `[NAME_OR_ROLE]`
- Response target: `[SLA, e.g. 2 business days]`

Participation is voluntary. Ask questions before agreeing. Do not upload any document other than the single approved `personal_photo`.

---

## 2. Privacy-page draft (for `https://wathefni.ai/employee-app/privacy`)

**Published 2026-07-12 (HTTP 200).** Content still requires your explicit wording approval on the decision sheet.  
Target URL must return final HTTP **200** before canary GO.

### Wathefni Employee App — Internal Canary Privacy Notice

Last updated: `[YYYY-MM-DD]`  
Applies to: internal one-employee production canary for Wathefni (`WATHEFNI`) only

#### Who this covers

This page explains how Wathefni handles data during a limited internal test of the Employee App. Your employer record remains under Wathefni HR/data ownership for this internal canary.

#### What we use

- Employee identity already held by Wathefni (name, phone, employment profile)
- App sign-in / session metadata
- In-app notifications inbox
- One `personal_photo` upload if you participate

#### What we do not require for this canary

- Push notifications
- Public app-store distribution
- WhatsApp or email delivery of the activation code (handoff is HR-only)
- Civil ID, bank details, or employment-contract upload

#### How we use the data

To test that only you can access your own profile and inbox, that activation works, that one photo upload works safely, and that we can support and roll back the test.

#### Providers

See the factual provider table approved for this canary. Opening this page may send ordinary web-request information to the page host.

#### Your choices

- Participation is voluntary
- You may withdraw by contacting `[ROLE_BASED_MAILBOX]`
- Withdrawal revokes app access; it does not by itself erase required HR or audit records

#### Contact

Privacy / support: `[ROLE_BASED_MAILBOX]`  
Privacy-request owner: `[NAME_OR_ROLE]`

---

## 3. Retention, deletion, and post-employment wording

**Status:** editable operational wording — approve bracketed values before notice delivery

### Access and credentials

- Pending invites, active sessions, and refresh credentials are revoked when the employee withdraws, the canary is rolled back or closed, or employment ceases to be active.
- Revocation blocks future app access. It does not itself erase canonical HR or audit records.

### Pilot operational metadata

- Invite, session, delivery/`hr_task`, incident, and audit metadata for the canary is retained for **`[PILOT_OPERATIONAL_RETENTION_DAYS]`** days after canary closure, unless an incident requires a documented hold.
- Activation codes, bearer tokens, refresh tokens, and document bytes must not be copied into readiness or incident logs.

### Personal-photo upload

- The canonical photo and Document Hub metadata are retained until **`[PHOTO_RETENTION_TRIGGER_OR_DATE]`**.
- At that point the HR/data owner decides whether the photo remains a legitimate HR record or is approved for deletion.
- Authorized deletion must reconcile canonical metadata, storage operations, and the live storage object. No blind object deletion is permitted.

### Deletion / privacy requests

- An in-app deletion request creates an auditable HR task; it is not an automatic hard delete.
- The privacy-request owner records the request, verifies identity, identifies records subject to operational or HR retention, approves disposition, and records completion.
- Access revocation is separate and is not delayed by longer record review.

### Post-employment

- When employment is no longer active, employee-app access and credentials are revoked through the supported lifecycle workflow.
- The employee can no longer access the app, inbox, checklist, or document.
- Canonical employment/document records are retained or deleted only according to the approved HR retention decision.

### Backups

- Production backups include database and workspace/document data and are sent offsite as encrypted bundles.
- Local rotation: seven daily and four weekly copies (confirmed configuration).
- Backblaze B2: private bucket; configured hide after 45 days and delete one day later (~46-day maximum persistence target, plus provider processing delay). B2 replication disabled.
- Deletion from the live system may remain in encrypted backups until that lifecycle expires.
- The canary photo’s primary copy is on the local production filesystem. After the next successful backup it may also exist inside the encrypted offsite bundle.
- Hostinger account-level snapshots: **`[CONFIRM_EXIST_OR_NOT]`**

Approving product/privacy owner: `[NAME]`  
Date: `[YYYY-MM-DD]`

---

## 4. Factual provider / subprocessor table

Only **confirmed** providers. Conditional/unverified downstream providers are excluded until separately evidenced.

| Provider | Confirmed role | Used by this canary? | Data in scope when used |
|---|---|---|---|
| Hostinger | Production VPS / API / local PostgreSQL / local document storage | **Yes** | Identity, phone, profile, session metadata, inbox/`hr_task` records, audit/reconciliation, uploaded photo |
| Backblaze B2 | Encrypted offsite backup destination | **Yes, after next successful backup** | Encrypted copies of pilot DB/workspace content and photo |
| Vercel | Privacy-page host | **Yes, if/when the published page is opened** | Ordinary web-request metadata (IP, headers, path, timestamp) |
| Healthchecks.io | Uptime monitoring only | **No employee/pilot content** | Health ping only |
| AI Octopus | Shared WhatsApp messaging provider (configured) | **No for this canary** — activation is `hr_task_only`; external messaging OFF | N/A unless canary scope is separately changed |
| Postmark | Outbound email provider (configured) | **No for this canary** — activation is `hr_task_only`; external messaging OFF | N/A unless canary scope is separately changed |

**Not listed as confirmed for this package:** 360dialog, Meta/WhatsApp (downstream of Octopus; not locally proven), Google/Gmail outbound (production email resolves to Postmark).

Product acceptance of this table: `[NAME / DATE]`

---

## 5. Employee consent / acknowledgment form

Store completed form **outside git**.

| Field | Value |
|---|---|
| Notice version acknowledged | `INTERNAL-CANARY-NOTICE-v1` |
| Notice effective date | `[YYYY-MM-DD]` |
| Notice SHA-256 | `[HASH]` |
| Employee key (private) | `[STORE_ONLY_IN_PRIVATE_RECORD]` |
| Employee display name (private) | `[PRIVATE]` |
| Date/time acknowledged | `[ISO-8601]` |
| Method | in-person / signed PDF / recorded email reply / other: ______ |
| HR/data-owner witness | `[NAME]` |

Employee statements (initial each):

- [ ] I received `INTERNAL-CANARY-NOTICE-v1` and the approved retention statement.
- [ ] I understand this is a one-person internal canary for Wathefni only.
- [ ] I consent to participate and to one approved `personal_photo` upload.
- [ ] I know how to contact `[ROLE_BASED_MAILBOX]` and how to withdraw.
- [ ] I will not upload Civil ID, bank details, or any document other than `personal_photo`.

Employee acknowledgment: ______________________________  
HR/data-owner confirmation: ______________________________

---

## 6. Owner-assignment form

| Role | Name | Direct contact | Backup name | Backup contact | Available in activation window? | Covers first 4 hours? | Stop authority accepted? | Signed / dated |
|---|---|---|---|---|---|---|---|---|
| HR/data owner |  |  |  |  | yes/no | yes/no | yes/no |  |
| Employee-support owner |  |  |  |  | yes/no (+ 48h?) | yes/no | yes/no |  |
| Technical-rollback owner |  |  |  |  | yes/no | yes/no | yes/no |  |

Role overlap (if any):

- Roles overlapped: ______________________________
- Why acceptable: ______________________________
- Reachable backup confirmed: yes / no
- Approved by / dated: ______________________________

Privacy/support mailbox: `[ROLE_BASED_MAILBOX]`  
Mailbox monitored from (date/time): ______________________________  
Privacy-request owner: ______________________________  
Response target/SLA: ______________________________

---

## 7. `personal_photo` onboarding approval line

I, `[HR/DATA OWNER NAME]`, approve that the Phase 8C internal canary for employee `[PRIVATE_EMP_KEY]` may include **only** one manually provisioned onboarding item of type **`personal_photo`**, and one corresponding photo upload after activation.

I confirm that `employment_contract`, `civil_id`, and `bank_details` are **out of scope** unless a separate written operational need is approved later.

Onboarding seed remains **OFF**.

Signature / date: ______________________________

---

## 8. Final GO evidence template (sensitive details outside git)

**Private file location (not in git):** `[PATH_OR_VAULT_REF]`  
**Public companion:** `ops/PHASE8C_CANARY_GO_PACKAGE.md`

### A. Security / engineering baseline (already accepted)

| Item | Evidence |
|---|---|
| R1E fail-closed cutover | commit / record ref: `1114351` / `PHASE8C2_R1E_PRODUCTION_CUTOVER_RECORD.md` |
| Artifact hash | `42f657fdb7d528f8dce25f09ef0de4ba28f8c1934d64acbb063d2cc3e36bf8d2` |
| Flags currently OFF (intentional) | `EMPLOYEE_APP` / `COMPANY_CHANNEL_ACCOUNTS` / `ONBOARDING_SEED` |
| Activation mode | `hr_task_only` |

### B. Human inputs (fill)

| Item | Value / private ref |
|---|---|
| HR/data owner + backup |  |
| Support owner + backup |  |
| Rollback owner + backup |  |
| Activation window |  |
| Privacy/support mailbox |  |
| Privacy URL publish proof (HTTP 200) | `[attach curl output privately]` |
| Notice version + SHA-256 |  |
| Retention values approved | days ______ ; photo trigger ______ |
| Provider table accepted | yes/no + date |
| Consent/ack evidence ref | `[private]` |
| `personal_photo` approval | yes/no + date |

### C. Read-only employee validation (run after employee is named; store privately)

```sql
SELECT employee_key, company_code, employment_status,
       (COALESCE(phone, '') <> '') AS has_phone, updated_at
FROM employees
WHERE employee_key = '<EMP_KEY>';
-- require: WATHEFNI + active + has_phone

SELECT employee_key, company_code, employment_status
FROM employees
WHERE phone = '<NORMALIZED_PHONE>'
ORDER BY company_code, employee_key;
-- require: exactly one row

SELECT invite_id, status, expires_at, redeemed_at
FROM employee_app_invites
WHERE employee_key = '<EMP_KEY>' OR phone = '<NORMALIZED_PHONE>';
-- require: zero participating invites

SELECT session_id, status, expires_at, refresh_expires_at, revoked_at
FROM employee_sessions
WHERE employee_key = '<EMP_KEY>';
-- require: zero sessions / refresh credentials
```

| Check | Pass? | Private evidence ref |
|---|---|---|
| Company binding `WATHEFNI` |  |  |
| `employment_status=active` |  |  |
| Unique verified phone |  |  |
| Zero pending/active invite |  |  |
| Zero employee-app session/refresh |  |  |
| No cross-company identity conflict |  |  |

### D. Final recommendation block

- Completed GO checklist attached: yes / no
- Remaining blockers: ______________________________
- Recommendation: **GO** / **NO-GO**
- Approver name / date: ______________________________
- Explicit execution authorization phrase required before any production step: `GO`

---

## Pause confirmation

Production implementation is paused pending your human inputs listed above.  
No privacy page will be published and no mailbox will be created without separate authorization.  
No canary execution will occur until you explicitly say **GO**.
