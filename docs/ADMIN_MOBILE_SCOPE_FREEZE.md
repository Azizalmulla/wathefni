# Admin / Manager / AI Recruiter Mobile — Scope Freeze

**Status:** Accepted (product decision frozen)  
**Date:** 2026-07-14  
**Prerequisite audit:** Admin / Manager / AI Recruiter Mobile Audit (accepted)

This document freezes durable product and security boundaries for operator mobile work. It does not authorize frontend build of Wathefni HR.

---

## Product decision — two separately authenticated apps

### 1. Wathefni (Employee App)

Employee-only mobile app. Uses:

- employee identity
- employee activation
- employee sessions
- `/app/*`
- self-scoped employee capabilities

Do not reuse `/app/auth/*` for operators. Do not modify the Employee App capability contract as part of operator mobile work.

### 2. Wathefni HR (operator mobile)

Separate mobile app for authorized:

- HR administrators
- managers
- recruiters
- hiring managers
- company owners

Must use:

- operator identity
- operator authentication
- operator sessions
- backend-current grants
- `/dashboard/*` or dedicated operator-mobile endpoints

**AI Recruiter** is a securely capability-gated module inside Wathefni HR. It is **not** a third app.

The in-product AI Recruiter is the Wathefni dashboard/orchestrator Assistant surface — **not** the legacy standalone `ai-recruiter/` prototype.

---

## Hard identity rules

1. **Do not create a unified employee/operator session.**
2. **Do not link identities** merely by matching email, phone, employee title, or role name.
3. A future unified binary may be reconsidered **only after** an explicit dual-principal and audited identity-linking architecture exists.
4. Three current principal systems remain separate until that architecture exists:
   - Employee (`employees` + `employee_sessions` + `/app/*`)
   - Operator (`dashboard_users` + sessions + grants + `/dashboard/*`)
   - Platform admin (Setup Console / env-gated internal)

---

## Parallel workstreams

| Stream | Status |
| --- | --- |
| Employee App — isolated Expo SDK migration | Approved to continue independently |
| **HR-0** — Existing Authority and Exposure Remediation | Active next slice (backend only) |
| **HR-1** — Operator Mobile Authentication and `/dashboard/mobile/me` Capability Contract | **Blocked until HR-0 is reviewed** |
| Wathefni HR frontend | **Do not start** |

HR-0 must not delay or combine with the Expo SDK migration.

---

## HR-0 scope (authority and exposure only)

1. Manager scope fail-closed (no phone / no binding → never company-wide)
2. Disable `legacy_untrusted` dashboard authentication on normal deployment paths
3. Quarantine or retire legacy `ai-recruiter/` `/internal/*`
4. Candidate CV view/preview/download audit evidence
5. Wire attendance status filtering on the authenticated HTTP route

### Out of scope (frozen exclusions)

- Wathefni HR frontend
- Unified employee/operator app
- Reusing `/app/auth/*` for operators
- Changing Employee App capability contract
- Production company module changes
- Exposing Payslips or employee compliance actions
- Brian canary
- EAS credentials / TestFlight publish

---

## Recommended next slice (after HR-0 review)

**HR-1 — Operator Mobile Authentication and `/dashboard/mobile/me` Capability Contract**

Deliver a backend-current, session-authenticated operator mobile bootstrap that exposes only granted capabilities for Wathefni HR — without starting the HR frontend and without unifying principals.

---

## Durable model notes (HR-0)

- Operator identity (`dashboard_user_id`) is the preferred manager-scope authority; phone remains a transitional binding.
- The `manager` role never implies company-wide employee visibility without an explicit scope assignment (including explicit `scope_type=company`).
- Owners / HR managers retain only backend-current authorized access (permissions + modules); they are not “managers without phone.”
- Shared dashboard tokens and client-supplied phone/company/role/permission claims must not establish authority outside an explicit test-only harness that fails startup elsewhere.
