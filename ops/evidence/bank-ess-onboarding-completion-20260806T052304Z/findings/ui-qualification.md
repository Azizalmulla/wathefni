# UI qualification — Bank ESS + onboarding completion

Stamp: `20260806T153212Z`  
Parent evidence: `ops/evidence/bank-ess-onboarding-completion-20260806T052304Z/`

## Surfaces under test

| surface | what was proven | how |
|---|---|---|
| Employee mobile bank screen | Reads `/app/bank*` only · idempotent submit · no retained plaintext · evidence via authorized stream · verified vs payroll vs submitted · all submission states · rejection reason + next step · allowlist unavailable state | `scripts/verify-capability-foundation.py` GREEN |
| Employee mobile onboarding | Completion from canonical contract only · never recomputed locally · bank checklist item routes to `/bank` · EN/AR key parity | same script + i18n parity checks |
| HR dashboard bank review | Verified vs proposed · changed-field markers · reject requires reason · permission-gated decide · first-submission label · payroll lock copy · approve does not apply · apply uses stable idempotency key · host refetch after decision | `vitest` `BankReviewPanel` 11 cases |
| HR dashboard completion strip | Exactly the 7 canonical states · EN/AR labels · ownership tones distinct · RTL · unknown state renders nothing | `vitest` `OnboardingCompletionStrip` 7 cases |
| Dashboard suite | Full Vitest | **83 files / 451 tests** PASS |
| Dashboard production build | `npm run build` | PASS |
| New-file lint | BankReviewPanel, bankReview, OnboardingCompletionStrip, onboardingCompletion, keys, setup | **0 errors** |

## Not claimed here

- Live production dashboard bundle deploy of this UI (local tree contains unrelated WIP; a full `/var/www/wathefni-dashboard` rsync would ship non-Bank-ESS changes).
- Live device / OTA canary walkthrough of the new `/bank` route on Aziz/Talal phones.
- Live HTTP re-run of the backend matrix in this UI stamp (backend remains the `qual-20260806T052441Z` proven run: Bank 43/43, Onboarding 27/27).

## Verdict contribution

These results raise Bank ESS and onboarding completion from **backend-only live** to **backend live + UI contract-proven**. They do **not** alone justify `fully proven` across employee and HR paths, because live UI bundles and device walks are still outstanding.
