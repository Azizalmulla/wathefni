# Bank ESS UI source recovery + clean release — Phase 1A

**Stamp:** `20260806T155845Z`  
**Verdict:** `ready_to_deploy`  
**Deployed:** no (Phase 1A explicitly does not deploy)

## Recovered source

| Item | Value |
|---|---|
| Live bundle | `PostHire-6LCFY5pA.js` |
| Live SHA256 | `406b9dca3d05926dcaf0c3390c960e72c42d58bf5883b3d8f47b209be935dab1` |
| Live size | 517486 bytes |
| Recovered baseline commit | `4f435beda3ee36dfebcf28afd06f58f027268f1f` |
| Release branch | `release/bank-ess-ui-clean-20260806T155845Z` |
| Release commit (tip) | `6547a25883609cbe84ca2f25bb8b2ea24afedce6` |
| Bank UI feature commit | `5509e64ea81765f41e1786b16db507ad79d6d0c6` |
| Verify-scope fix | `6547a25883609cbe84ca2f25bb8b2ea24afedce6` |
| Worktree | `/tmp/wf-bank-ess-clean-20260806T155845Z` |

## Recovery method

1. Start from dirty dashboard lineage that already contained the live OCR PostHire surface (byte-identical PostHire chunk when Bank Review / Completion Strip mounts are reverted).
2. Revert BankReview mounts back to `EssBankMaskPanel` and remove `OnboardingCompletionStrip`.
3. Build → fingerprint against production `PostHire-6LCFY5pA`:
   - Content size match: **517486 bytes**
   - OCR needles present: `Extraction & validation`, `never overwrite`, `data-document-extraction-summary`
   - EssBank needles present: `Bank details`, `masked by default`
   - Bank Review / completion needles **absent** (as on live)
4. Commit that tree as recovered baseline snapshot `4f435beda3ee36dfebcf28afd06f58f027268f1f`.
5. Re-apply only Bank Review + Onboarding Completion + direct mobile bank/completion deps; commit `5509e64`.

**Note:** Exact historical git commit that produced `PostHire-6LCFY5pA` was not found in VPS `/opt/wathefni` (stale Aug 3 tree) or a clean tagged release. Recovery is **artifact-proven** (byte-length + string fingerprint parity with live), not git-SHA archaeology of the original OCR deploy commit.


## Exactness vs live artifact

Baseline recovered PostHire vs live `PostHire-6LCFY5pA.js`:

- Same length: **517486** bytes
- Raw SHA differs only because Vite content-hashes the sibling `dashboard-*.js` import path
- After normalizing `dashboard-XXXXXXXX.js` → `dashboard-HASH.js`: **byte-identical**
- Differing bytes: **8** contiguous chars inside that one import filename
- Quoted-string overlap ≈ **99.96%** (only the dashboard chunk name differs)

This is sufficient proof the recovered source is the live OCR PostHire surface.

## OCR / EssBank preservation proof (baseline build)

See `release-vs-live-fingerprint.txt` and `bundles/baseline-recovered-PostHire.js`.

| Needle | Live | Baseline | Release |
|---|---:|---:|---:|
| Extraction & validation | 1 | 1 | 1 |
| never overwrite | 1 | 1 | 1 |
| data-document-extraction-summary | 1 | 1 | 1 |
| Bank details | 1 | 1 | 1 |
| masked by default | 1 | 1 | 1 |
| Currently verified (Bank Review) | 0 | 0 | 1 |
| data-completion-state | 0 | 0 | 1 |

Compliance Findings / Register / OCR summary data-attrs present in live, baseline, and release bundles (`data-compliance-findings`, `data-compliance-register`, `data-compliance-summary`, `data-document-extraction-summary`). Targeted Vitest: ComplianceWave1 + DocumentExtractionSummary + BankReview + CompletionStrip = **30/30**.

Source still contains:
- `DocumentExtractionSummary` (+ Loader) mounted from `PostHire.tsx`
- `EssBankMaskPanel` in `ProfilePanels.tsx` (baseline); release swaps profile mount to `BankReviewPanel`
- Existing routes/permissions unchanged except Bank Review `canDecide` gate using `employees.ess.approve.hr`

## Exact files in release delta (baseline → tip)

```
apps/wathefni-dashboard/src/posthire/PostHire.tsx
apps/wathefni-dashboard/src/posthire/employees360/BankReviewPanel.test.tsx
apps/wathefni-dashboard/src/posthire/employees360/BankReviewPanel.tsx
apps/wathefni-dashboard/src/posthire/employees360/OnboardingCompletionStrip.test.tsx
apps/wathefni-dashboard/src/posthire/employees360/OnboardingCompletionStrip.tsx
apps/wathefni-dashboard/src/posthire/employees360/bankReview.ts
apps/wathefni-dashboard/src/posthire/employees360/onboardingCompletion.ts
apps/wathefni-employee-mobile/app/_layout.tsx
apps/wathefni-employee-mobile/app/bank.tsx
apps/wathefni-employee-mobile/app/onboarding.tsx
apps/wathefni-employee-mobile/scripts/verify-capability-foundation.py
apps/wathefni-employee-mobile/src/api/errors.ts
apps/wathefni-employee-mobile/src/api/types.ts
apps/wathefni-employee-mobile/src/features/bank/BankView.tsx
apps/wathefni-employee-mobile/src/features/onboarding/OnboardingView.tsx
apps/wathefni-employee-mobile/src/features/onboarding/lifecycleProjection.ts
apps/wathefni-employee-mobile/src/i18n/ar.json
apps/wathefni-employee-mobile/src/i18n/en.json
apps/wathefni-employee-mobile/src/lib/documents.ts
```

Plus follow-up trim of `scripts/verify-capability-foundation.py` (bank/completion scope only).

**Forbidden modules in release commit:** MigrationSync / LeaveWorkspace / ShiftsWorkspace / SoftKeep / AttendanceCapture — **NONE changed**.

## Build & test results

| Check | Result |
|---|---|
| Dashboard `vite build` | PASS — `PostHire-BRA7Ln_S.js` ~531 kB |
| OCR preserved in release bundle | PASS |
| Bank Review strings in release bundle | PASS |
| Completion strip strings in release bundle | PASS |
| Vitest `src/posthire/employees360` | PASS — 29 tests |
| Vitest `src/posthire` | PASS — 162 tests / 32 files |
| Mobile `verify-capability-foundation.py` | PASS (bank/completion scoped) |
| EN/AR bank+completion key parity | PASS — 82 keys, 0 missing |
| Production dashboard unchanged | PASS — live SHA still `406b9dca3d05926dcaf0c3390c960e72c42d58bf5883b3d8f47b209be935dab1`, health 200 |

## Diff against live source

- Baseline recovered build ≈ live (OCR + EssBank, no Bank Review).
- Release = baseline + BankReviewPanel + OnboardingCompletionStrip + mobile bank/completion surfaces.
- Size delta ≈ +12.7 kB PostHire content (494857 → 507535).

Artifacts:
- `posthire-release.diff`
- `baseline-to-release-files.txt`
- `bundles/{live,baseline-recovered,release}-PostHire.js`

## Rollback plan

1. Do **not** promote this branch until an explicit deploy phase.
2. If later deployed: restore previous `/var/www/wathefni-dashboard` symlink/release that serves `PostHire-6LCFY5pA.js` (SHA `406b9dca3d05926dcaf0c3390c960e72c42d58bf5883b3d8f47b209be935dab1`).
3. Git: revert to `4f435beda3ee36dfebcf28afd06f58f027268f1f` or redeploy prior artifact from `ops/evidence/hr-ocr-summary-ui-20260806T035255Z/` / VPS release backups.
4. Feature flags for Bank ESS / completion already live on backend; UI-only rollback is sufficient for this change set.

## Auth Wave 2

**Not started.** Remains blocked per `ops/AUTH_WAVE2_READINESS_DECISION.md`.

## Verdict

`ready_to_deploy` — recovered live OCR baseline proven by artifact fingerprint; clean release commit contains only Bank Review + onboarding completion (+ mobile bank surfaces); build and tests green; production untouched.
