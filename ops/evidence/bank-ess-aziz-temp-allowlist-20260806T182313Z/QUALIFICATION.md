# Temporary Aziz Bank ESS canary allowlist

**Stamp:** `20260806T182313Z`  
**Verdict:** `deployed` (backend allowlist only; OTA not required)  
**Phase 2 / Auth Wave 2:** not started  

## Why

Physical canary test of the real Bank form for Aziz (`WATHEFNI-96599338566`) using the **normal eligibility allowlists** — no UI hardcoding.

## Env changes (temporary drop-in)

File on VPS (remove after Phase 2):

`/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-aziz-temp-phase2-canary.conf`

| Variable | Value |
|---|---|
| `WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST` | synthetic `7001–7003` **+** Aziz |
| `WATHEFNI_EMPLOYEE_ESS_V5_REAL_ALLOWLIST` | Talal **+** Aziz (needed under `SYNTHETIC_ONLY=on` for mutations) |
| `WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST` | Aziz (required for real bank_detail_change submits) |

## Live prove — PASS

`prove/aziz-enabled-matrix.json`

| Surface | Result |
|---|---|
| `bank_ess_eligibility` | eligible |
| `/app/me` `features.bank.enabled` | true (+ submit/withdraw/upload_evidence) |
| `/app/onboarding` | `bank_ess.eligible` + `open_bank` on bank_details · EN/AR 200 |
| `/app/bank` | 200 |

## OTA

**Not republished.** Tip remains `388e8cf5-1d6b-4140-9c84-bfff55504928` — mobile already follows `features.bank` + `open_bank`.

## Physical test (Aziz)

1. Force-quit → reopen Wathefni (pull canary OTA if not already on tip).
2. Onboarding → **Open bank details** should appear.
3. Open Bank form — fill IBAN/account (validation may be soft: `ENFORCE_VALIDATION=off`).
4. Optional: attach evidence, submit (goes to HR review; does not payroll-apply by itself).
5. EN/AR if possible. Reply PASS/FAIL.

Do **not** payroll-apply or expand beyond Aziz without a separate decision.

## Cleanup after Phase 2

```bash
bash ops/evidence/bank-ess-aziz-temp-allowlist-20260806T182313Z/cleanup/REMOVE_AZIZ_AFTER_PHASE2.sh
```

Removes the drop-in, restarts orchestrator, restores synthetic-only Bank ESS + Talal-only ESS real allowlist. Then re-prove Aziz is ineligible again.

## Out of scope

- Auth Wave 2
- Broad real-employee Bank ESS rollout
- UI hardcoding
