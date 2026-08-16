# 20260806T200247Z — Onboarding: one canonical state and next action per surface

Bank ESS `Apply` succeeded but onboarding stayed at 3/4 with "Next: Payroll ·
Bank setup". This stamp fixes the reconciliation, then removes the reasons the
four surfaces could disagree at all, and proves it with a live Aziz/Talal walk.

## Root causes

1. **Stale bank history outranked the bank of record.**
   `reconcile_onboarding_bank_item` ordered Bank ESS requests by recency only, so
   an older `rejected` request beat a newer `applied` one: every HR read pushed
   the `bank_details` item back to `replacement_required`.
2. **Each surface picked its own "next" item.** The HR queue and the
   drawer/app/profile ran separate selection loops over different item sets
   (one included optional items), so they could name different items and owners.
3. **`reopened` hardcoded owner `employee`.** A bank change under review showed
   `hr` on the queue and `employee` on the other three. `reopened` records when
   work appeared, not who owns it.
4. **The mobile app preferred a local state→copy table** over the contract's
   `next_action` message, so client copy could contradict the backend owner.

## Fixes

- `desired_onboarding_bank_state()` — fixed authority order: open request → live
  `employee_bank_effective` → terminal history. Idempotent, so the reconcile
  that now runs on all four read paths causes no writes or event churn.
- `select_next_item()` in `onboarding_completion_contract.py` — the only way any
  surface names "what happens next": required + open, class priority
  `waiting_employee → waiting_hr → waiting_other → blocked`, unblocked-then-due
  tiebreak, same rows and filter as `compute_completion`.
- `current_actor()` drives the `reopened` owner and copy from the snapshot's own
  buckets, so the state's owner and the named item's owner cannot diverge.
- Mobile renders the contract's message; the per-state string is an offline
  fallback only, asserted by `verify-capability-foundation.py`.

## Evidence

| file | what it proves |
|---|---|
| `prove/consistency-matrix.md` | all four surfaces identical at all 7 transitions |
| `prove/live-walkthrough.txt` | 46/46 live checks, employee → HR → correction → approval → Apply, Aziz + Talal |
| `prove/reconcile-authority-smoke.txt` | 15/15 authority, idempotency, owner-parity and required-only regression checks |
| `deploy/backend-shipped.diff` | the orchestrator deploy is 5 hunks, all next-item/next-action |
| `deploy/dashboard-content-delta.txt` | of 36 dashboard chunks only `PostHire.js` changed; the rest only re-hashed |
| `deploy/unrelated-wip-needles.txt` | pre-existing unrelated WIP was already live before this stamp |
| `mobile/ota-shipped.diff` | the OTA delta is 8 files, all bank/onboarding |
| `mobile/ota-needles.txt` | new copy present, retired copy gone, both platforms, EN + AR |
| `mobile/capability.txt` | capability foundation GREEN incl. the new backend-copy assertion |

## Live surfaces

- Orchestrator: `app.py`, `onboarding_completion_contract.py` (health 200, active)
- Dashboard: `PostHire-Bcu7y5zK.js` in `/var/www/wathefni-dashboard`
- Mobile canary OTA: group `b540423a-de1a-44c9-afa5-caa9504d2957`, runtime `0.1.0`

## Rollback

`./ROLLBACK.sh` (OTA republish of group `e3d3ffae-14a8-42f9-bc87-301763b0b0cd`
is step 1 and is intentionally manual).

## Not in this stamp

Auth Wave 2 remains blocked. Broad rollout beyond the Aziz/Talal canary still
needs owner sign-off on a physical device.
