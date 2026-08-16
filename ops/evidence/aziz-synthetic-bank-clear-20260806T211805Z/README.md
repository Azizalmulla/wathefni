# 20260806T211805Z — Aziz synthetic bank ghost cleared

## Root cause

The prior broad-rollout cleanup **only**:
1. superseded `employee_bank_effective` (payroll live row), and
2. soft-deleted `employee_ess_bank_profiles`.

It **did not** clear `employee_bank_verified`.

`employee_bank_status()` builds the Bank screen from:

```text
has_verified_bank = bool(verified_row OR live_effective)
```

and, when there is no active request, also resurfaced the latest terminal
request — including `applied` / `withdrawn` — as the current submission.

So after cleanup the live API still returned:

- `has_verified_bank: true`
- `verified.display.bank_name: "Walkthrough Bank"`
- `verified.display.account_holder: "Aziz Walkthrough Corrected"`
- `iban_last4: "0000"`
- `submission_state: approved` (then later `withdrawn` with the same proposed values)
- `payroll_effective: null`

The physical app is correct: it rendered what `/app/bank` returned. This was
not a mobile cache bug.

## Exact cleanup performed

1. **Schema (additive):** `employee_bank_verified.revoked_at` + `revocation_reason`
2. **Projection fix in `employee_bank_ess.py`:**
   - current verified read filters `revoked_at IS NULL`
   - terminal `applied` is never resurfaced as the current submission
   - when there is **no** live bank of record, terminal history is not projected
     at all (clean empty state for first real submit)
3. **Data:** revoked all 4 synthetic verified rows for Aziz
   (`reason=walkthrough_synthetic_revoked_not_current`)
4. Confirmed no live effective row; ESS profile remains soft-deleted
5. Request + superseded effective history **retained** for audit

## Live API proof

`prove/clear.txt` · `prove/clear.json` · `prove/live-api-after.json`

After:

| field | value |
|---|---|
| `has_verified_bank` | `false` |
| `verified` | `null` |
| `payroll_effective` | `null` |
| `submission` | `null` |
| `submission_state` | `none` |
| `can_submit_new` | `true` |
| `next_step` | Add your bank details so salary can be paid to you. |
| Walkthrough / 0000 in body | absent |

Authority regression: `RECONCILE_AUTHORITY_OK` (see `prove/authority-regression.txt`).

## Physical-app retest

1. Force-quit the Wathefni employee app (swipe away).
2. Reopen → open **Bank**.
3. Expect **no** Walkthrough Bank / Verified chip / IBAN …0000.
4. Expect empty state with CTA to **add bank details**.
5. Enter your real IBAN / account details and submit (do not use a TEST IBAN).

If anything synthetic still appears after force-quit, capture a screenshot and
the time — the live API above is already empty, so that would be a client-side
stale bundle and we would republish OTA next.
