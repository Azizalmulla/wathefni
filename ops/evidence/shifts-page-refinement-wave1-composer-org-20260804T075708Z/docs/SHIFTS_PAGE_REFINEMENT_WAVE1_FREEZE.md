# Shifts Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Deploy stamp (IA):** `20260804T074315Z`  
**Composer-org correction stamp:** `20260804T075708Z`  
**Evidence (IA):** `ops/evidence/shifts-page-refinement-wave1-prod-deploy-20260804T074315Z/`  
**Evidence (composer org):** `ops/evidence/shifts-page-refinement-wave1-composer-org-20260804T075708Z/`  
**Report:** `ops/SHIFTS_PAGE_REFINEMENT_WAVE1.md`  
**Live bundle:** `/var/www/wathefni-dashboard/assets/PostHire-oFjO0X5a.js`

## Frozen surface

- Schedule is the default dominant surface (day/week board + date chrome + attention strip)
- Peer IA is only **Schedule / Requests / Planning**
- Requests: swaps, availability, reconciliation
- Planning: templates, publish, enterprise, reminders; readiness/lab honesty collapsed by default
- One page primary: **Schedule a shift**
- Quiet Refresh; governed compact org filters on Schedule
- No duplicated inner Shifts heading; no delivery strip on Shifts
- Empty board shows title + hint + Schedule CTA
- **Create composer** uses governed Organization selectors for branch / site / team / location (IDs from `getEmployeeOrgUnits`); child options filter by selected parent when hierarchy exists
- **Edit / detail** shows the same governed fields; legacy keys not in Organization surface an explicit **Unmapped** option and are preserved (not discarded)
- Normal creation does not fall back to unrestricted org-key text
- Mutation contracts preserved: `createShift` / `cancelShift` / `rescheduleShift` + `expected_updated_at`

## Frozen non-goals

- Operator timer enablement
- PAM auto-submit / government submission
- Payroll money impact
- Reopening Attendance / Leave / Onboarding freezes
- Inventing new shift statuses or weakening concurrency gates
- Inventing org units in the UI

## Rollback

Composer-org (current live):

```bash
bash /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-composer-org-20260804T075708Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-composer-org-20260804T075708Z
```

IA baseline (pre-composer-org):

```bash
bash /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-page-refinement-wave1-20260804T074315Z
```
