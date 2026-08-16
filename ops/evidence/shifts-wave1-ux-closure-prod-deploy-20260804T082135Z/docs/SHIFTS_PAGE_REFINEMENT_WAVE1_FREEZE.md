# Shifts Page Refinement Wave 1 — FREEZE

**Status:** FROZEN (amended)  
**Deploy stamp (IA):** `20260804T074315Z`  
**Composer-org correction stamp:** `20260804T075708Z`  
**UX Closure stamp:** `20260804T082135Z`  
**Evidence (IA):** `ops/evidence/shifts-page-refinement-wave1-prod-deploy-20260804T074315Z/`  
**Evidence (composer org):** `ops/evidence/shifts-page-refinement-wave1-composer-org-20260804T075708Z/`  
**Evidence (UX Closure):** `ops/evidence/shifts-wave1-ux-closure-prod-deploy-20260804T082135Z/`  
**Report:** `ops/SHIFTS_PAGE_REFINEMENT_WAVE1.md`  
**Native dialog inventory:** `ops/SHIFTS_WAVE1_UX_CLOSURE_NATIVE_DIALOG_INVENTORY.md`  
**Live bundle:** `/var/www/wathefni-dashboard/assets/PostHire-bz887YSK.js`

## Frozen surface

- Schedule is the default dominant surface (day/week board + date chrome + attention strip)
- Peer IA is only **Schedule / Requests / Planning**
- Requests: swaps, availability, reconciliation
- **Planning (normal HR):** Templates (+ recurring schedules), Publishing (+ coverage), Rotations **only when enabled and actually used**
- **Advanced operations** (`settings.manage` **or** `users.manage`): system reminders, compliance/PAM export, softened readiness chips — hidden from normal HR
- One page primary: **Schedule a shift**
- Quiet Refresh; governed compact org filters on Schedule
- No duplicated inner Shifts heading; no delivery strip on Shifts
- Empty board shows title + hint + Schedule CTA
- **Create composer** uses governed Organization selectors for branch / site / team / location (IDs from `getEmployeeOrgUnits`); child options filter by selected parent when hierarchy exists
- **Edit / detail** shows the same governed fields; legacy keys not in Organization surface an explicit **Unmapped** option and are preserved (not discarded)
- Normal creation does not fall back to unrestricted org-key text
- **No browser-native** `prompt` / `confirm` / `alert` in Shifts — audited cancels use shared `ConfirmDialog.withReason`
- Mutation contracts preserved: `createShift` / `cancelShift` / `rescheduleShift` + `expected_updated_at`

## Frozen non-goals

- Operator timer enablement
- PAM auto-submit / government submission
- Payroll money impact / Payroll Wave 1 reopen (`20260804T080520Z` stays frozen)
- Reopening Attendance / Leave / Onboarding freezes
- Inventing new shift statuses or weakening concurrency gates
- Inventing org units in the UI
- Blind global rewrite of Employees/document native prompts (deferred — see inventory)

## Rollback

UX Closure (current live):

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave1-ux-closure-20260804T082135Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-wave1-ux-closure-20260804T082135Z
```

Composer-org:

```bash
bash /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-composer-org-20260804T075708Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-composer-org-20260804T075708Z
```

IA baseline:

```bash
bash /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z
```
