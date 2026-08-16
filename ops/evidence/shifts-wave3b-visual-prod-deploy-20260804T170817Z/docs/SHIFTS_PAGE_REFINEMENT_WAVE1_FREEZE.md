# Shifts Page Refinement — AUTHORITY + WAVE 3B VISUAL FREEZE

**Status:** Wave 1 authority, Wave 2 IQ, and approved Wave 3B visual composition are **FROZEN**  
**Deploy stamp (IA):** `20260804T074315Z`  
**Composer-org correction stamp:** `20260804T075708Z`  
**UX Closure stamp:** `20260804T082135Z`  
**Visual & UX Wave 2 (IQ-12) stamp:** `20260804T155956Z`  
**Visual Design Wave 3 rejected stamp:** `20260804T162104Z` — historical evidence only, not a baseline  
**Visual & Interaction Wave 3B stamp:** `20260804T170817Z`  
**Evidence (IA):** `ops/evidence/shifts-page-refinement-wave1-prod-deploy-20260804T074315Z/`  
**Evidence (composer org):** `ops/evidence/shifts-page-refinement-wave1-composer-org-20260804T075708Z/`  
**Evidence (UX Closure):** `ops/evidence/shifts-wave1-ux-closure-prod-deploy-20260804T082135Z/`  
**Evidence (Wave 2 IQ):** `ops/evidence/shifts-wave2-iq-prod-deploy-20260804T155956Z/`  
**Evidence (Wave 3 visual):** `ops/evidence/shifts-wave3-visual-prod-deploy-20260804T162104Z/`  
**Evidence (Wave 3B):** `ops/evidence/shifts-wave3b-visual-prod-deploy-20260804T170817Z/`  
**Report:** `ops/SHIFTS_PAGE_REFINEMENT_WAVE1.md` · Wave 2: `ops/SHIFTS_VISUAL_UX_WAVE2.md` · Rejected Wave 3: `ops/SHIFTS_VISUAL_DESIGN_WAVE3.md` · Wave 3B: `ops/SHIFTS_VISUAL_INTERACTION_WAVE3B.md`  
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

## Wave 3B visual freeze

- Wave 3's spreadsheet-like board, repeated identity cards, filter chrome, generic
  empty state, and plain create/edit aside are **not frozen** and must not be
  propagated.
- Wave 3B replaces the table with roster lanes, anchors employee identity once,
  makes time primary, and uses semantic state rails and linked overnight
  continuations.
- Create/detail/edit uses a fixed 420px end sheet on desktop and full-screen
  mobile sheet, so opening it never resizes the board.
- Mobile uses a seven-day strip and employee-grouped agenda; RTL uses logical
  inline positioning and direction-aware continuation treatment.
- Loading retains board and drawer content, history stays rendered while
  refreshing, and client-only status filtering does not refetch.
- Wave 3B preserves every authority and interaction item above, including
  organization governance, sticky selection, confirmation-until-success,
  duplicate-submission guards, and clear success/error/cancellation feedback.
- Wave 3B may be adopted as the post-hiring composition baseline page-by-page;
  scheduling-specific semantics must not be copied as decoration.

## Frozen non-goals

- Operator timer enablement
- PAM auto-submit / government submission
- Payroll money impact / Payroll Wave 1 reopen (`20260804T080520Z` stays frozen)
- Reopening Attendance / Leave / Onboarding freezes
- Inventing new shift statuses or weakening concurrency gates
- Inventing org units in the UI
- Blind global rewrite of Employees/document native prompts (deferred — see inventory)
- Propagating rejected Wave 3 visual composition to any post-hire page
- CalendarShell legacy hex rewrite (separate wave)

## Rollback

Wave 3B visual (current live):

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave3b-visual-20260804T170817Z/ROLLBACK.sh
```

Rejected Wave 3 visual:

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
