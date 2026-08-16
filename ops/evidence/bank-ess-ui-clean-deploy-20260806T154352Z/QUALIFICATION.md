# Phase 1 clean UI deploy — BLOCKED

**Stamp:** 20260806T154352Z
**Verdict:** `blocked`
**Auth Wave 2:** still blocked (unchanged)

## Exact reason

Cannot safely deploy Bank ESS / onboarding-completion UI without either:

1. **Regressing live OCR HR UI**, or
2. **Shipping unrelated dirty-tree WIP** inside `PostHire.tsx` and its dependency graph.

### Facts established

| Fact | Evidence |
|---|---|
| Live dashboard PostHire is OCR deploy `PostHire-6LCFY5pA.js` @ 2026-08-06T03:52:44Z | `/var/www/wathefni-dashboard` mtime + strings `Extraction & validation summary`, `never overwrite` |
| Live does **not** yet contain Bank Review UI | no `Currently verified` / `Awaiting your review` in live bundle |
| Git HEAD `cf26d59` PostHire is **not** production | 5208 lines, no employees360, no OCR, no EssBank |
| VPS `/opt/wathefni/apps/wathefni-dashboard` PostHire is stale (Aug 3) | has EssBankMask, no DocumentExtraction wires |
| Only local dirty working tree has OCR + BankReview + CompletionStrip together | `apps/wathefni-dashboard/src/posthire/PostHire.tsx` |
| Dirty PostHire also imports unrelated modules | MigrationSyncShell, LeaveWorkspace, ShiftsWorkspace, soft-keep query hooks, etc. — **not** present in live bundle |
| Building VPS base + bank patches alone fails / regresses OCR | tsc/vite missing modules; OCR not in VPS PostHire |
| Restoring HEAD files into a dirty rsync breaks the build | missing exports in moduleWorkspace / prehireOverviewPresentation |

### What was prepared (not deployed)

- Release branch: `release/bank-ess-ui-20260806T154352Z`
- Worktree: `/tmp/wf-bank-ess-ui-release-20260806T154352Z`
- Live backend contract check: **OK** for bank + onboarding-completion + ESS decide/apply + `/app/bank*`
- Feature flags on prod: `WATHEFNI_BANK_ESS_V1=on`, `WATHEFNI_ONBOARDING_COMPLETION_CONTRACT=on` (unchanged)
- No dashboard rsync performed
- No employee OTA / native build performed
- Auth Wave 2 not started

### Unblock requirements

1. Recover or freeze a **production PostHire source snapshot** that matches live `PostHire-6LCFY5pA` (OCR + EssBank, no later WIP), then
2. Apply **only** BankReviewPanel + OnboardingCompletionStrip + API/types patches on that snapshot, then
3. Build → deploy dashboard → OTA mobile bank screen from a similarly clean mobile snapshot.

### Rollback

Not applicable — production dashboard was not modified in this phase.
