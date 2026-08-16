# Onboarding Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Freeze stamp:** `20260804T064643Z`  
**Evidence:** `ops/evidence/onboarding-page-refinement-wave1-freeze-20260804T064643Z/`  
**Report:** `ops/ONBOARDING_PAGE_REFINEMENT_WAVE1.md`

## Frozen surface

- Queue-first Onboarding with filters: Needs attention / In progress / Not started / Completed / All
- Row shows employee+role, start, progress, next/blocker, urgency
- **Primary action is derived** from existing checklist ownership/status (not hard-coded Remind):
  - employee-owned missing item → **Remind**
  - HR / IT / payroll / compliance owned → **Open checklist**
  - uploaded / awaiting review (existing `storage_status` / review-like status / detail `document_index`) → **Review**
  - no actionable blocker → **View details**
- Secondary actions stay under **More** (Remind when not primary, Checklist, Reschedule, Cancel, Profile)
- Deep-link `?employee=` expands + selects + scrolls (+ pin if off-page)
- Profile: onboarding context + Open in Onboarding only
- Needs Attention polish: no duplicate inner heading; no delivery strip on inbox/onboarding

## Surfaced fields (not new states)

Queue enrichment / detail summary may include existing item columns:

- `next_item_status`
- `next_item_storage_status`

## Frozen non-goals

- Attendance redesign (next after this freeze)
- Needs Attention ranking/grouping reopen
- Assistant mutation kill policy changes
- Inventing new onboarding item statuses

## Ownership matrix (frozen)

Onboarding mutates checklist/remind/reschedule/cancel.  
Employee Profile routes. Compliance verifies docs. Alerts owns delivery. Needs Attention ranks and routes.

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-onboarding-page-refinement-wave1-freeze-20260804T064643Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-onboarding-page-refinement-wave1-freeze-20260804T064643Z
```
