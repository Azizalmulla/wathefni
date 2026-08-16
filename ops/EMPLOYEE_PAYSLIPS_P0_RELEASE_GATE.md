# Employee Payslips P0 — HR Release Gate + Employee Read-Only

## Authority model

Document lifecycle (unchanged): `active | replaced | revoked`

**Orthogonal employee visibility:** `employee_visibility = not_released | released`

| Employee-facing state | Rule |
|---|---|
| Not released | `status=active` AND `employee_visibility=not_released` |
| Released | `status=active` AND `employee_visibility=released` |
| Replaced | `status=replaced` (not employee-visible) |
| Revoked | `status=revoked` (not employee-visible) |

**Employee App visibility iff** `status=active AND employee_visibility=released`.

Period `open|locked|closed` never implies employee visibility.

## Download honesty

- No official employee PDF yet.
- Download is an employee-safe **statement summary** `.txt` with honesty banner.
- `official_document=false`; `payment_date` always null until a real field exists.
- Native preview remains non-authoritative (`money_authority=preview_non_authoritative`).

## Blockers to official downloadable payslips

1. Official PDF generation + signed document storage
2. Authoritative money source for native (or only release external mirrors)
3. Real `payment_date` / payment confirmation field
4. Production non-synthetic payroll authority (Wave 3 still synthetic-only in prod)

## APIs

HR: `POST .../payslips/{id}/release`, `.../unrelease`  
Employee: `GET /app/payslips`, `GET /app/payslips/{id}`, `GET /app/payslips/{id}/download`
