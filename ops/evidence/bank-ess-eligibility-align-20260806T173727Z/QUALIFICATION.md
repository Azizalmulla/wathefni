# Bank ESS eligibility alignment — me / onboarding / bank

**Stamp:** `20260806T173727Z` (backend) · OTA `20260806T181405Z`  
**Verdict:** `deployed` (backend live + canary OTA tip; physical iPhone walk pending — no USB device on agent host)  
**Phase 2 / Auth Wave 2:** not started  

## Problem

Onboarding showed **Bank details** with **Open bank details**, but `/bank` returned “Bank self-service is not available yet” for canary employee Aziz (`WATHEFNI-96599338566`).

Aziz is on the employee-app allowlist but **not** on Bank ESS allowlist (synthetic `7001–7003` only). The bug was **projection/CTA mismatch**, not missing allowlist membership.

## Fix (canonical eligibility)

Single authority: `employee_bank_ess.bank_ess_eligibility(company, employee_key)`.

| Surface | Behavior when ineligible |
|---|---|
| `/app/me` → `features.bank` | `enabled: false`, reason stamped |
| `/app/onboarding` | `bank_ess` top-level; bank items **no** `open_bank` action |
| `/app/bank` | 403 with same reason |
| Mobile | CTA only if `actions.has('open_bank')` + `hasFeature('bank')`; route shows `BankUnavailableView` |

No Aziz hardcode. Real canary stays Bank ESS–disabled under current policy.

## Live prove (PASS)

Evidence: `prove/live-matrix-after-fix2.json`

| Case | employee | me.bank | open_bank | /app/bank | EN/AR onboarding |
|---|---|---|---|---|---|
| disabled | `WATHEFNI-96599338566` | false / `bank_ess_not_allowlisted` | false | 403 | 200 |
| enabled | `WATHEFNI-9655497001` | true | true | 200 | 200 |

## Backend deploy

- Modules: `employee_bank_ess.py`, `onboarding_lifecycle_wave2a.py`, surgical `app.py` patches
- Feature contract version: `phase9a1_bank_ess`
- Fix2: restore `/app/profile` (erroneous `bank_ess` insert), add `bank_ess` to `/app/onboarding` return, `_bank_ess_context` via eligibility helper
- Backup: `/opt/wathefni/orchestrator/app.py.bak-bank-elig-fix2-manual`
- Health: 200 after restart

## Canary OTA (use this)

| Item | Value |
|---|---|
| Group | `388e8cf5-1d6b-4140-9c84-bfff55504928` |
| Runtime | `0.1.0` |
| Branch | `canary` |
| iOS | `019fd849-26c1-72ec-94b8-500e667e3bc0` |
| Android | `019fd849-26c1-740a-bc32-6e4a2283d429` |
| Base | prior fix tree `wf-bank-ess-ota-fix-20260806T172002Z` + eligibility overlays |
| Capability | GREEN |
| Fingerprint | syncLayoutLocale + typeof guard + hasFeature('bank') + open_bank — PASS |

## Physical verification (owner)

1. Force-quit Wathefni → reopen (pull tip `388e8cf5…`).
2. Confirm home launches (no “fresh start”).
3. **Onboarding:** Bank details may still appear as a checklist item, but **no Open bank details** CTA for Aziz.
4. If `/bank` opened via deep link / stale nav → explained unavailable state, not a dead end error loop.
5. EN/AR if possible. Reply PASS/FAIL.

## Rollback

```bash
# OTA
apps/wathefni-employee-mobile → eas update:rollback 388e8cf5-1d6b-4140-9c84-bfff55504928
# Prior good tip: 85f648c9-73a0-4b14-9d8e-838913496a4d

# Backend
cp /opt/wathefni/orchestrator/app.py.bak-bank-elig /opt/wathefni/orchestrator/app.py
# + restore prior employee_bank_ess / onboarding_lifecycle_wave2a from backup stamp
systemctl restart wathefni-orchestrator
```

## Out of scope

- Expanding Bank ESS allowlist to real employees
- Phase 2 / Auth Wave 2
- Dashboard changes (unchanged this stamp)
