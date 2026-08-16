# Onboarding Page Refinement Wave 1 — Final freeze evidence

**Freeze stamp:** `20260804T064643Z`  
**Prior visual stamp:** `20260804T063521Z`  
**Evidence:** `ops/evidence/onboarding-page-refinement-wave1-freeze-20260804T064643Z/`  
**Freeze:** `ops/ONBOARDING_PAGE_REFINEMENT_WAVE1_FREEZE.md`

## Verdict

| Decision | Result |
|---|---|
| Primary action derivation (not hard-coded Remind) | **GO** |
| Freeze Onboarding Wave 1 | **GO / FROZEN** |
| Begin Attendance | **GO** (owner may proceed) |
| Invent new backend item states | **NO-GO** (not done) |

## Pre-freeze correction

Remind was hard-coded as the row primary for every hire when `canManage` was true.

**Fix:** `onboardingPrimaryAction()` derives the primary from existing ownership/status:

| Condition | Primary |
|---|---|
| Uploaded / awaiting review (`storage_status` stored/ok/uploaded…, review-like status, or detail `document_index` file on open item) | **Review** |
| `next_owner_group === employee` and missing | **Remind** |
| `next_owner_group` in hr / it / payroll / compliance | **Open checklist** |
| No next/pending blocker | **View details** |

Remind remains available under **More** when it is not primary.

Additive surfacing only (existing DB columns): `next_item_status`, `next_item_storage_status` on queue enrichment + detail summary.

## Production deploy

- Dashboard → `/var/www/wathefni-dashboard` (`PostHire-DavN6N29.js`)
- Orchestrator `app.py` enrichment fields → `/opt/wathefni/orchestrator/app.py` (restarted; health ok)
- Backup: `/opt/wathefni/backups/production-pre-onboarding-page-refinement-wave1-freeze-20260804T064643Z/`

## Proof

- Vitest: primary-action unit + Onboarding/NA/mutation contracts — **21/21 PASS** (`ui/vitest.out`)
- Live enrichment probe: Talal next = employee · Signed employment contract → **remind**; fields present (`verify/enrichment-probe.out`)
- Synthetic branch proof: employee→remind, hr→open_checklist, stored→review, empty→view_details (`verify/primary-mix-probe.out`)
- Mutation integrity smoke — **PASS** (`verify/smoke-mutation-integrity.out`)
- Screenshot matrix: `screenshots/primary-actions-matrix.png`

## Visual evidence (Wave 1 + freeze)

Prior pack (cream queue UI): `ops/evidence/onboarding-page-refinement-wave1-20260804T063521Z/screenshots/`  
Freeze matrix: `ops/evidence/onboarding-page-refinement-wave1-freeze-20260804T064643Z/screenshots/primary-actions-matrix.png`
