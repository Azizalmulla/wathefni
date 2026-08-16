# 20260806T212710Z — Aziz real bank flow acceptance

## Verdict

**ACCEPTANCE_PASS** — 19/19 checks

## Scope (read-only acceptance)

Confirm after owner completed real bank flow (submit → HR approve → payroll approve → Apply):

1. Bank screen shows real details as verified
2. No synthetic Walkthrough/test data remains
3. Onboarding completed
4. Absent from active onboarding queue
5. HR queue, HR drawer, employee app, and employee profile agree
6. No duplicate Apply / unexpected reconcile writes

## Live truth (Aziz `WATHEFNI-96599338566`)

| Surface | Result |
|---|---|
| `/app/bank` verified | Gulf bank · ABDULAZIZ HAMAD RASHED ALMULLA · IBAN last4 **9548** · stage `payroll` |
| submission | `none` (no stale withdrawn Walkthrough card) |
| next_step | “Your bank details are verified. Submit a change if anything is different.” |
| payroll_effective | present · fingerprint `0f349ce848ab5e4b` (not walkthrough `c4e2fb083889b894`) |
| employee app / profile / HR drawer | `completed` 4/4 · owner `none` · same next-action message |
| HR active queue | **absent** |
| bank_details | drawer `accepted` · app group `completed` |
| reconcile ×2 | `changed: false` · request `22ecca3c-…` state `applied` |
| open bank requests | none |

## Genuine defect found + fixed during acceptance

First read-only pass **failed** because `/app/bank` still projected an older walkthrough **`withdrawn`** request (`49baff00-…`, IBAN last4 `0000`) as the current submission whenever a live bank of record existed.

**Fix (minimal):** in `employee_bank_status()`, only surface terminal `rejected`/`withdrawn`/`failed` history when `updated_at` is **after** the current verified/effective bank-of-record timestamp. Older walkthrough terminals no longer outrank the live real bank.

Deployed to production orchestrator; acceptance re-run → **PASS**.

Artifact: `fix/terminal-history-cutoff.patch.txt`

## Evidence

- `prove/acceptance.txt` — PASS log
- `prove/acceptance.json` — full check payload
- `prove/acceptance.py` — verifier used
- `prove/db-snapshot.json` — requests / effective / verified rows
- `prove/deployed-module.txt` — live module hash + service active

## Notes

- Auth Wave 2 readiness updated to **ready** (Phase 1 PIN only; no auth code in this stamp) — `ops/AUTH_WAVE2_READINESS_DECISION.md`.
- Historical applied/withdrawn/rejected audit rows remain (expected); they are not projected as current Bank submission.
- Exactly one live `employee_bank_effective` row for the real Apply (`22ecca3c-…`).
