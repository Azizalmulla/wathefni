# Employee API Gap Plans

Planning only. No Payslips or Compliance Actions UI is exposed.

## Shared contract requirements

Before either slice starts, the backend must provide:

- Employee-scoped `/app/*` endpoints deriving company and employee identity from the verified session.
- Capability entries in `/app/me` using the existing `payslips` and `compliance_actions` keys, with explicit action names.
- The same company-disabled, archived, module-removed, employee-inactive, session-expired, and global-app-disabled errors used by existing employee endpoints.
- Pagination/order rules, stable identifiers, localized-display ownership, and audit requirements.
- A document delivery contract compatible with authenticated byte download or a short-lived HTTPS provider URL. Bearer tokens must never appear in URLs.
- Empty, unavailable, and retention semantics. The frontend must not infer records from HR dashboard endpoints.

## Payslips slice

Backend decisions required:

- List periods and available payslip records.
- Download/preview authority and file metadata.
- Whether acknowledgement exists; if so, expose it as an explicit capability action and idempotent mutation.
- Retention, replacement/versioning, and unavailable-period behavior.
- Pagination and newest-first ordering.

Frontend implementation after contract approval:

1. Add response types mirroring the approved payload.
2. Add route/query only when `hasFeature('payslips')` is true.
3. Add Home/profile entry only when the capability is enabled.
4. Reuse the secure cancellable document transfer path.
5. Render mutations only when the corresponding capability action exists.

## Compliance Actions slice

Backend decisions required:

- List open/completed actions with stable IDs, due dates, status, display content, and action type.
- Explicit supported mutations such as acknowledge, attest, or upload; do not overload one generic action.
- Evidence/document requirements and whether the existing onboarding upload endpoint can be reused. Reuse is not assumed.
- Idempotency, expiry, withdrawal, completion, and HR-rejection behavior.
- Pagination, ordering, and unread/attention counts.

Frontend implementation after contract approval:

1. Add typed list/detail queries for the approved employee endpoints.
2. Surface the module only through `hasFeature('compliance_actions')`.
3. Gate every mutation with `can('compliance_actions', approvedActionName)`.
4. Reuse permanent state, upload, document, accessibility, RTL, and error patterns.
5. Add no fallback action when the backend omits a capability.

## Acceptance

Both slices require backend contract tests, cross-tenant denial tests, inactive/disabled state tests, EN/AR copy review, physical-device transfer tests, and capability-removal tests before any UI becomes visible.
