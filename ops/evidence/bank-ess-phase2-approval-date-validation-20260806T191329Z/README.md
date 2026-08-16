# Bank ESS Phase 2 — approval/date/validation correction

## Finding

Aziz request `d65628a4-45c0-4e6a-9d42-7811f0f600ec` did not fail
silently and was not applied:

1. `pending_hr → pending_payroll` (`decide_approve`, HR)
2. `pending_payroll → approved` (`decide_approve`, payroll)

The dashboard collapsed both states into `pending_review`, so both buttons
looked like the same action. The request remained unapplied.

## Shipped correction

- Exact HR, payroll, ready-to-apply, and payroll-effective labels.
- Visible three-stage approval flow and stage-specific button copy.
- Decision concurrency version plus an immediate in-memory action lock.
- Stable apply idempotency key remains in place.
- Mobile submitted date uses a label plus formatted value, avoiding placeholder
  interpolation for returned and resubmitted requests.
- Backend scheme registry is enforced. Kuwait IBAN uses country prefix, length,
  alphanumeric and mod-97 checksum checks; generic identifiers also reject
  punctuation. No bank name is hardcoded.
- Apply revalidates before changing payroll authority.

## Live remediation

The approved request carried advisory validation failures
`iban_length_invalid` and `iban_charset_invalid`. It was returned through an
audited `validation_return: approved → needs_information` transition. No
plaintext value was added to the audit event and no invalid value became
payroll-effective.

## Evidence

- `audit/remediation.json`
- `audit/remediation.txt`
- `deploy/backend.txt`
- `dashboard/final-live-asset.txt`
- `mobile/typecheck.txt`
- `mobile/capability.txt`
- `mobile/eas-update.json`
- `deploy/ROLLBACK.sh`
