# Bank ESS Phase 2 — correction resubmit + field errors

## Live failure

- Device POST `/app/bank/requests` → **409** `bank_request_already_active`
- Request `d65628a4-45c0-4e6a-9d42-7811f0f600ec` was already `needs_information`
- Mobile mapped unknown 409 to generic “Something went wrong”
- Synthetic IBAN `KW30TEST0000000000000000000000` **passes** production `kw_iban` validator
- No other field failed validation (account/SWIFT accepted)

## Fix

- `needs_information` / `draft` correction replaces sealed proposal on the same request_id and returns to `pending_hr` (audited `correct_and_resubmit`)
- Validation still enforced before seal/replace
- Mobile shows field-level errors, keeps form values, busy lock against duplicates
- Clear copy for `bank_account_invalid` and `bank_request_already_active`

## Proof

See `prove/resubmit-replace.txt` — same request_id, `needs_information → pending_hr`, display last4 `0000`.
