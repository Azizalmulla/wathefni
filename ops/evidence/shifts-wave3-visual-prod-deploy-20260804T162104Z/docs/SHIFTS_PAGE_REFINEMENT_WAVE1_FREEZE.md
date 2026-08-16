# Shifts Page Refinement Wave 1 — FREEZE

**Status:** FROZEN (amended by Visual Design Wave 3)  
**Deploy stamp (IA):** `20260804T074315Z`  
**Composer-org correction stamp:** `20260804T075708Z`  
**UX Closure stamp:** `20260804T082135Z`  
**Visual & UX Wave 2 (IQ-12) stamp:** `20260804T155956Z`  
**Visual Design Wave 3 (shared baseline) stamp:** `20260804T162104Z`  
**Evidence (IA):** `ops/evidence/shifts-page-refinement-wave1-prod-deploy-20260804T074315Z/`  
**Evidence (composer org):** `ops/evidence/shifts-page-refinement-wave1-composer-org-20260804T075708Z/`  
**Evidence (UX Closure):** `ops/evidence/shifts-wave1-ux-closure-prod-deploy-20260804T082135Z/`  
**Evidence (Wave 2 IQ):** `ops/evidence/shifts-wave2-iq-prod-deploy-20260804T155956Z/`  
**Evidence (Wave 3 visual):** `ops/evidence/shifts-wave3-visual-prod-deploy-20260804T162104Z/`  
**Report:** `ops/SHIFTS_PAGE_REFINEMENT_WAVE1.md` · Wave 2: `ops/SHIFTS_VISUAL_UX_WAVE2.md` · Wave 3: `ops/SHIFTS_VISUAL_DESIGN_WAVE3.md`  
**Native dialog inventory:** `ops/SHIFTS_WAVE1_UX_CLOSURE_NATIVE_DIALOG_INVENTORY.md`  
**Live bundle:** `/opt/wathefni/dashboard-dist/assets/PostHire-Cjhqi0Um.js` (uvicorn `:8010`)

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
- **Wave 2 IQ:** soft-keep loading, debounced employee filter, sticky drawer rematch, `needs_confirmation` completion, `confirm.run` for governed mutations, non-reflow updating overlay
- **Wave 3 visual:** shared pre-hire `wf-accent-*` semantic surfaces on shift blocks; Schedule board hero; ink today pill; compact filters; designed empty state; Requests/Planning calmer than Schedule; markers `data-shifts-visual-wave3` / `data-shifts-board-hero`

## Frozen non-goals

- Operator timer enablement
- PAM auto-submit / government submission
- Payroll money impact / Payroll Wave 1 reopen (`20260804T080520Z` stays frozen)
- Reopening Attendance / Leave / Onboarding freezes
- Inventing new shift statuses or weakening concurrency gates
- Inventing org units in the UI
- Blind global rewrite of Employees/document native prompts (deferred — see inventory)
- Blind restyle of all post-hire pages in one stamp (adopt Wave 3 tokens page-by-page)
- CalendarShell legacy hex rewrite (separate wave)

## Rollback

Wave 3 visual (current live — prefer `dashboard-dist`):

```bash
rsync -a --delete \
  /opt/wathefni/backups/production-pre-shifts-wave3-visual-dashboard-dist-20260804T162104Z/ \
  /opt/wathefni/dashboard-dist/
# optional mirror
rsync -a --delete \
  /opt/wathefni/backups/production-pre-shifts-wave3-visual-20260804T162104Z/ \
  /var/www/wathefni-dashboard/
```

Wave 2 IQ:

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave2-iq-20260804T155956Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-wave2-iq-20260804T155956Z
```

UX Closure:

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
