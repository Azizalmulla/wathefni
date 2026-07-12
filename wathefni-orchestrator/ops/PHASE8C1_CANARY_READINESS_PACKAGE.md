# Phase 8C1 — Internal Canary Readiness Package

**Status:** accepted with amendments  
**Date:** 2026-07-12  
**Scope:** readiness decisions only  
**Execution status:** not authorized

This package does not authorize deployment, production flags, company-module
enablement, employee changes, onboarding creation, invitations, sessions,
privacy publication, routing changes, or canary execution.

## 1. Product decision

Option A is explicitly selected:

> `WATHEFNI` is approved solely for one internal, one-employee production
> canary. It is not the external client pilot, creates no entitlement for
> additional employees or companies, and permits no automatic expansion. Any
> continuation requires a separate GO decision.

This approves the company choice only. It does not authorize module enablement,
flag changes, employee modification, onboarding creation, invitations, or
canary execution.

Option B—waiting for a real external pilot company—remains the fallback if the
internal-canary readiness gates cannot be completed safely.

## 2. Readiness sequence

Before a separate execution GO:

1. Name the HR/data, employee-support, and technical-rollback owners.
2. Record any role overlap explicitly and name a reachable backup.
3. Identify one genuine internal employee through authoritative HR records.
4. Verify authoritative `WATHEFNI` binding, active employment, phone ownership
   and uniqueness, and the absence of an employee-app invite or session.
5. Use only the supported admin/backend workflow for any employee correction;
   retain its audit evidence.
6. Complete the internal-canary privacy minimum.
7. Obtain explicit employee consent and notice acknowledgment.
8. Approve the minimum manual onboarding scope.
9. Review the enablement, monitoring, stop, and rollback procedures from the
   Phase 8C plan.
10. Issue a separate written execution GO.

## 3. Owner roles

Required roles:

- HR/data owner
- employee-support owner
- technical-rollback owner

One person may hold multiple roles only when:

- the overlap is explicitly recorded;
- the person has the required authority and technical access;
- the person is available throughout activation and immediate validation;
- a reachable backup is named; and
- support and rollback coverage remain available for the first four hours.

No owner names are inferred or invented.

Fields required for each role:

- name;
- title or authority;
- direct contact;
- backup name and contact;
- activation-window availability;
- first-four-hours coverage;
- acknowledgment of assigned responsibilities; and
- acknowledgment of stop and rollback authority.

## 4. Genuine internal employee selection

Exactly one employee may be proposed. Selection must:

1. Start from the authoritative HR/admin record.
2. Prove the employee belongs to `WATHEFNI`.
3. Prove employment status is active.
4. Verify the normalized phone is unique and controlled by the employee.
5. Prove no active or pending employee-app invite exists.
6. Prove no employee-app session or refresh credential exists.
7. Obtain explicit internal-pilot consent.
8. Deliver the versioned employee notice and retain acknowledgment evidence.
9. Record the employee key only in the restricted readiness record.
10. Repeat all identity, invite, and session checks immediately before any
    future invitation.

If an authoritative employee record is incorrect, the HR/data owner must use
the supported backend/admin workflow. The correction must retain requester,
approver, reason, before/after state, timestamp, and audit identifier. Direct
production-row patching merely to satisfy a gate is forbidden.

## 5. Internal-canary privacy minimum

The following are hard blockers before an invitation:

- monitored role-based privacy/support mailbox;
- exact in-app privacy URL returning HTTP 200;
- versioned internal-canary employee notice;
- explicit employee consent and acknowledgment;
- basic retention, deletion, and post-employment treatment;
- factual inventory of providers actually processing pilot data; and
- named owner for privacy requests.

The internal canary is not blocked on external-client contractual language or
public-store wording that is irrelevant to the internal pilot. Those remain
blockers before an external-client pilot.

No unapproved legal claim may be published.

## 6. Manual onboarding scope

Initial scope:

- `personal_photo`

`employment_contract` may be added only when the HR/data owner records a
genuine operational requirement.

Controls:

- `WATHEFNI_ONBOARDING_SEED=off`;
- manual provisioning only after execution authorization;
- one approved upload during the canary;
- no `civil_id`;
- no `bank_details`; and
- no extra sensitive document collected merely for testing.

## 7. GO checklist

- **Complete:** Phase 7E closed and staging-green.
- **Complete:** Phase 8B production-dark green.
- **Complete:** Phase 8C plan committed at `a2971c0`.
- **Complete:** Option A company choice explicitly approved for one internal
  employee only, with no automatic expansion.
- **Incomplete:** owner names, contacts, backups, authority, and availability.
- **Incomplete:** exact genuine internal employee.
- **Incomplete:** authoritative active status and company-binding evidence.
- **Incomplete:** unique verified phone evidence.
- **Incomplete:** selected-employee invite/session absence evidence.
- **Incomplete:** explicit consent and notice acknowledgment.
- **Incomplete:** monitored role-based mailbox.
- **Blocked:** privacy URL currently ends in HTTP 404; it must return 200.
- **Incomplete:** versioned internal-canary notice.
- **Incomplete:** retention, deletion, and post-employment wording.
- **Incomplete:** factual production-provider inventory.
- **Incomplete:** named privacy-request owner.
- **Incomplete:** HR/data approval of `personal_photo` as the initial checklist
  item and a documented decision on whether `employment_contract` is genuinely
  required.
- **Blocked:** separate Phase 8C execution GO.

## 8. Remaining blockers

1. Named owners and backups.
2. One genuine internal employee and authoritative eligibility evidence.
3. Consent and notice acknowledgment.
4. Live monitored mailbox and named privacy-request owner.
5. Privacy URL returning HTTP 200.
6. Versioned internal-canary notice.
7. Retention, deletion, and post-employment wording.
8. Factual production-provider inventory.
9. Final minimum onboarding-item approval.
10. Separate execution authorization.

## 9. Boundaries

Until a separate GO:

- do not deploy code;
- do not change production flags;
- do not enable `employee_app`;
- do not change an employee record;
- do not create onboarding rows;
- do not create invitations or sessions;
- do not publish privacy content;
- do not install or change routing; and
- do not touch Phase 7D, push, store, payroll, assessments, or onboarding seed.

Protected flags remain OFF:

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_ONBOARDING_SEED=off`

