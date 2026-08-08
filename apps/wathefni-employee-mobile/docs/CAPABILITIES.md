# Employee App capability contract

`GET /app/me` is the only mobile authority for employee feature visibility.
The client must not derive features from module names, identity fields, roles,
routes, or local configuration.

Successful responses mean the platform flag, active company lifecycle,
`employee_app` company entitlement, active employment, and employee session have
already passed. `effective_modules` contains only effective employee-audience
modules; `enabled_modules` is a compatibility alias with the same meaning.

## Canonical feature keys

- `home`: core; `view`.
- `profile`: core; `view`.
- `inbox`: core; `view`, `mark_read`.
- `settings`: core; `view`, `change_locale`, `request_deletion`; `manage_push`
  only when push is platform-available.
- `onboarding`: requires all of `onboarding`; `view`, `upload_document`.
- `documents`: requires any of `onboarding`, `compliance`; `view`, `download`,
  and `upload_document` for renewals when the backend grants it.
- `attendance`: requires all of `attendance`; `view`.
- `shifts`: requires all of `shifts`; `view`.
- `leave`: requires all of `leave`; `view`, `request`, `cancel`.
- `payslips`: requires all of `payroll`, but stays disabled until an
  employee-scoped payslip API exists (**no payroll money authority in app v1**).
- `compliance_actions`: requires all of `compliance`, but stays disabled until
  missing/expiry action APIs exist. The Documents journey may still surface
  compliance expiry items via `documents` when enabled.

Every key is always returned in `features`. Disabled keys contain a deterministic
`reason` (`module_disabled` or `feature_not_available`) and no actions.

The `leave` object supplies backend-owned leave types and whether balances are
available. Company policy rows are authoritative; unseeded V1 tenants retain the
existing annual/sick compatibility defaults.

## Endpoint enforcement

The backend returns HTTP 403 with `error=employee_feature_disabled`, the canonical
feature key, and a reason before reading or mutating module data. Existing
session identity, tenant filtering, object ownership, and offboarding revocation
remain additional mandatory checks.

Core endpoints remain available to an otherwise eligible employee:
`/app/me`, `/app/profile`, `/app/notifications`, notification read state,
settings/account deletion, and push unregister. Push registration additionally
requires the `manage_push` action.
