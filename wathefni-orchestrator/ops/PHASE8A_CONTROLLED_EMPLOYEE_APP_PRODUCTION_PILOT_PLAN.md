# Phase 8A — Controlled Employee App Production Pilot Plan

**Document status:** plan only  
**Current production status:** dark; no deployment, tenant creation, invitations, or flag changes authorized  
**Required starting flags:** `WATHEFNI_EMPLOYEE_APP=off`, `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`, `WATHEFNI_ONBOARDING_SEED=off`

Phase 8A prepares one tightly controlled production pilot. Execution requires a separate written GO approval after every preflight field is complete.

## 1. Pilot-company selection criteria

The pilot must be one **existing** production company satisfying all criteria:

1. Company lifecycle is `active`, with no pending disable/archive or offboarding event.
2. The company gives written approval for a maximum five-employee controlled pilot.
3. A named client HR owner can issue invites, manually provision onboarding items, inspect `hr_task`, handle employee questions, and request immediate rollback.
4. Named Wathefni support and rollback owners are available throughout the observation window.
5. Cohort employees already exist in canonical HR data, are actively employed, and have verified unique phone numbers belonging to the correct company.
6. No cohort employee has ambiguous, duplicate, cross-company, `left`, disabled, or revoked identity state.
7. The company can use Option A onboarding: every required checklist row is reviewed and manually provisioned before that employee's invitation.
8. The company accepts inbox-only ongoing notifications; push is not required.
9. Activation can use the existing shared WhatsApp/email ladder and `hr_task`; company-owned channel accounts are not required.
10. Leave is included only if the company's `leave` module is already enabled and already operational.
11. The company does not require payroll, assessments, onboarding seed, push, public store launch, or new employee-app features for pilot success.
12. Privacy contact, policy, retention/deletion wording, subprocessor inventory, and employee notice are approved before any real invitation.
13. A private, approved application distribution path already exists for the named cohort. Phase 8A does not create a public store listing.
14. The company accepts immediate access revocation and invite supersession during rollback.
15. Production `WATHEFNI` is not the default pilot and may be selected only through a separate explicit written decision.

Any failed criterion disqualifies the company until corrected.

## 2. Proposed pilot company

**Design-only candidate:** `PROPOSED_PILOT_CO`

This is a planning label, not a tenant to create. Before execution it must be replaced by the code of one existing, consenting production company that passes every criterion above. No company is created, activated, or modified by this plan.

Selection evidence must include:

- company code and active lifecycle proof
- current module snapshot
- written client approval
- named owners and contact paths
- approved privacy/policy pack
- cohort count only in git; employee PII remains in the restricted HR/operator sheet
- checklist and optional leave readiness
- private distribution confirmation
- rollback contact acknowledgment

## 3. Cohort and canary

- Maximum total cohort: **5 employees**
- First step: **1 employee canary**
- Remaining expansion: at most **4 employees**
- No bulk invitations
- Each employee is revalidated immediately before invitation

Canary eligibility:

- active canonical employee in the pilot company
- verified unique phone
- no existing active employee-app session or pending/redeemed invite
- willing participant who received the approved privacy notice
- at least one manually provisioned onboarding item if upload is being tested
- leave included only when the company already has the leave module enabled

The remaining cohort is not invited until the canary gate passes.

## 4. Required owners

The following names and direct contact paths must be filled before GO:

- **HR owner:** one named client HR administrator; owns employee selection, checklist correctness, invitation action, employee notice, and first-line support.
- **Support owner:** one named Wathefni support lead; owns monitoring, `hr_task` follow-up, incident log, and employee/HR coordination.
- **Rollback owner:** one named Wathefni platform operator; owns module disablement, global kill switch, service restart, session/invite revocation proof, and reconciliation drain.
- **GO approver:** Wathefni product owner/operator who confirms privacy, technical, and owner readiness.

One person may not silently assume all roles. HR and rollback ownership must remain distinct. If any owner becomes unavailable, stop new invitations.

## 5. Included workflows

Only:

1. HR invite and employee activation
2. Employee profile
3. Notification inbox and read state
4. Manually provisioned onboarding checklist
5. Onboarding document upload
6. Leave balance/request/cancel only when the pilot company already has the `leave` module enabled

For onboarding:

- `WATHEFNI_ONBOARDING_SEED` remains OFF
- checklist rows are created manually and explicitly per employee
- empty checklist never means complete
- document type, ownership, size, MIME/signature, audit, storage, and reconciliation rules remain unchanged

## 6. Excluded workflows

- push notifications
- company channel accounts
- onboarding seed
- payroll
- assessments or video interviews
- public App Store or Play launch
- public listing assets/reviewer work
- multi-company enablement
- production `WATHEFNI` as an implicit pilot
- unrelated employee-app features or Document Hub redesign

## 7. Delivery policy

Activation delivery uses only the existing shared ladder:

1. existing shared WhatsApp session when valid
2. approved shared template when configured
3. email fallback when configured and allowed
4. visible `hr_task` when delivery cannot complete

Backend-owned states remain authoritative: created, attempted, delivered, failed, suppressed, or fallback. The UI and HR owner must never infer delivery.

All ongoing pilot notifications are **inbox-only**:

- no push registration or send
- no company channel account
- no ongoing WhatsApp notification promotion
- HR checks the inbox and `hr_task` surfaces during the pilot

## 8. Privacy and policy gate

Before the first real invitation, all must be complete:

- dedicated role-based privacy/support mailbox
- privacy policy published at the in-app URL
- product-owner approval and legal review of employer-controller / Wathefni-processor wording
- pilot-specific retention and deletion SLA
- policy for files after employment ends
- factual list of actually deployed infrastructure, storage, shared messaging/email, monitoring, and AI subprocessors
- approved employee privacy notice and HR delivery evidence
- account deletion/request handling runbook
- incident contact and escalation path
- private distribution disclosure and access instructions

Missing privacy or policy evidence is a hard stop. Public-store assets remain out of scope.

## 9. Production-dark deployment procedure

This procedure itself requires separate deployment approval. All protected flags remain OFF throughout the dark deployment.

1. Create and review final R2 commit(s); require a clean, traceable release boundary.
2. Confirm staging evidence remains 24/24 and 57/57 for the exact artifact.
3. Capture production DB/data, service environment, and artifact snapshots.
4. Confirm protected flags are OFF before deployment.
5. Deploy backend code, additive schema, pinned dependencies, reconciliation worker, operator CLI, and service templates.
6. Install and enable the production reconciliation timer while employee-app access remains globally OFF.
7. Run schema idempotency, compile, health, route, timer/service, and zero-pending reconciliation checks.
8. Verify no production company has become reachable through `/app/*`.
9. Verify shared routing, Phase 7D routing, onboarding seed, push, and dashboard behavior are unchanged.
10. Record the dark artifact hash and hold it without inviting anyone.

Dark deployment success does not authorize the pilot switch.

## 10. Exact one-company enablement sequence

After a separate pilot GO:

1. Start a change window with HR, support, rollback, and GO owners present.
2. Reconfirm all three protected flags are OFF and capture production snapshots.
3. Resolve `PROPOSED_PILOT_CO` to the approved existing company code; recheck active lifecycle.
4. Query every production `company_modules.employee_app` row. Require **zero enabled non-pilot companies**; otherwise stop.
5. Validate the five-or-fewer employee cohort against canonical company and employment state.
6. Manually provision and review Option A onboarding items for the canary only.
7. Confirm leave scope from the existing module state; do not enable leave merely for this pilot.
8. With the global flag still OFF, enable `company_modules.employee_app` for the pilot company only.
9. Requery module state and prove all non-pilot companies remain disabled.
10. Confirm reconciliation timer/service healthy, audit sink writable, and no pending/manual reconciliation entries.
11. Apply the separately approved production flag change `WATHEFNI_EMPLOYEE_APP=on` and restart through the normal guarded deployment path.
12. Verify the pilot company passes current lifecycle/module gates and a non-pilot company remains denied.
13. Reconfirm `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off` and `WATHEFNI_ONBOARDING_SEED=off`.
14. HR sends exactly one canary invitation.
15. Observe the canary gate before provisioning or inviting any remaining employee.
16. If approved after observation, provision and invite remaining employees individually, never exceeding five total.

No production tenant creation occurs in this sequence.

## 11. Monitoring, audit, and reconciliation

Monitoring cadence:

- immediately before each invitation
- 15 minutes after invitation
- after activation
- after each included workflow
- hourly for the first four canary hours
- daily through the cohort observation window

Required checks:

- API health and `/app/*` 4xx/5xx rate
- company lifecycle and module state
- active/revoked sessions and refresh rotation
- pending/redeemed/superseded invites
- employee identity/company binding
- activation `employee_messages`, outbound attempts, delivery events, and `hr_task`
- profile and inbox self-scope
- onboarding item state and Document Hub linkage
- `employee_document_uploaded` and `employee_document_upload_rejected` events
- `document_storage_operations` status, age, attempts, lease, and manual-review count
- reconciliation timer active/enabled and latest service result
- leave audit/state only when included
- zero non-pilot employee-app access
- protected flags and shared-routing state

Every incident receives timestamp, owner, affected company/employee identifier, evidence, disposition, and rollback decision. No file bytes, activation codes, tokens, or unsafe filenames enter the incident log.

## 12. Canary success gate

Observe the one-employee canary for **48 hours**.

Canary must:

- receive an honest delivered/fallback/failed activation result with `hr_task` when required
- activate exactly once with one valid session
- load the correct profile and inbox
- view only the manually provisioned checklist
- complete at least one valid document upload when onboarding is in scope
- create canonical document/audit state with zero permanent orphan
- leave reconciliation at zero pending/manual work after normal processing
- complete one leave read/request/cancel control only if leave was already enabled
- produce no cross-tenant, cross-employee, privacy, or support incident

Only the named GO approver may authorize the remaining cohort.

## 13. Pilot success criteria

Through seven days after the last invitation:

- canary gate fully passed
- total cohort never exceeded five
- at least 80% of invited employees activated
- no employee obtained a second session through repeated activation
- all profile/inbox/document/leave data remained self- and tenant-scoped
- every participating employee with onboarding scope completed at least one valid upload
- no permanent object orphan and no unresolved reconciliation `manual_review`
- rejected uploads remained storage-free and auditable when the sink was available
- all activation failures/fallbacks were honestly surfaced, with `hr_task` where required
- no push, company channel account, onboarding seed, payroll, assessment, or public-store dependency
- no severity-1/2 incident
- rollback drill evidence remains executable in under 15 minutes
- HR and support owners confirm manageable load

## 14. Stop criteria

Immediately stop new invitations and begin rollback for:

- any cross-tenant or cross-employee access
- identity mismatch, stale lifecycle authorization, credential revival, or duplicate activation session
- any permanent unreferenced object, unsafe deletion, or cross-tenant reconciliation attempt
- any reconciliation `manual_review` related to a pilot upload
- reconciliation timer unavailable for more than 10 minutes during upload activity
- repeated or unexplained `/app/*` 5xx errors
- activation reported as delivered without backend proof
- delivery failure with no visible failed/fallback/`hr_task` outcome
- audit sink outage during repeated rejected-upload activity
- privacy notice, policy, retention, or owner readiness becoming invalid
- support load exceeding the named owners' capacity
- pressure to enable push, company channels, onboarding seed, or excluded features to continue
- rollback owner unavailable

For a single contained non-security issue, support may pause new invitations while the GO and rollback owners decide. Authorization, tenant isolation, privacy, or object-safety failures always trigger immediate rollback.

## 15. Immediate rollback

Target: block pilot access and new activation within **15 minutes**.

1. Announce rollback; HR stops invitations and support opens the incident record.
2. Disable the pilot company's `employee_app` module. Use the existing transition hook to revoke sessions/refresh credentials and supersede pending invites.
3. Set `WATHEFNI_EMPLOYEE_APP=off` and restart through the guarded service path.
4. Verify pilot bearer access is denied, refresh is denied, and old invites cannot reactivate.
5. Verify every non-pilot company remains denied.
6. Keep reconciliation timer/service running; drain `prepared`, `stored`, `deleting`, and `compensation_pending` operations.
7. Inspect `manual_review` without blind deletion; preserve the ledger and canonical documents.
8. Reconfirm company channel accounts and onboarding seed remain OFF.
9. Capture post-rollback data, flag, service, session, invite, object, audit, and reconciliation evidence.
10. Do not re-enable from the incident window. Require a new written GO after root cause and staging regression.

Rollback does not hard-delete legitimate employee documents or reconciliation truth.

## 16. Observation and expansion gate

- Canary observation: **48 hours**
- Full cohort observation: **7 days after the final invitation**
- No additional company during Phase 8A
- No cohort expansion beyond five

At day seven, the GO group reviews:

- success/stop criteria
- support and HR load
- activation delivery outcomes
- security/tenant evidence
- document audit and reconciliation history
- privacy requests or incidents
- rollback readiness

Possible decisions:

1. **Hold:** continue the same cohort with no new invitations.
2. **Rollback:** disable the pilot and investigate.
3. **Close pilot successfully:** maintain only the approved cohort pending a later phase.
4. **Propose expansion:** create a new reviewed phase plan; no automatic second-company or public rollout.

Phase 8A never authorizes automatic expansion.

## Planning guardrails

During planning:

- no production deployment
- no production tenant creation
- no employee invitation
- no protected flag change
- no Phase 7D routing promotion
- no onboarding seed enablement
- no push or public store work
- no unrelated feature expansion

Flags remain unchanged:

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_ONBOARDING_SEED=off`
