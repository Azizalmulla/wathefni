# Jobs Phase 1 — Staging Closure Report

**Date:** 2026-07-20  
**Branch:** `authority-cutover`  
**Environment:** staging only (`wathefni_staging`, `:8011`)  
**Staging artifact SHA:** `0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1`  
**Recommendation:** **HOLD before production.** Promote only after a short owner UX soak on staging Jobs form + confirmation that production `WATHEFNI_APPLY_WHATSAPP_NUMBER` is set explicitly.

## Commits (Jobs Phase 1)

1. `e8f32f7` — Jobs authority, lifecycle, schema, permissions, Assistant alignment  
2. `f249a27` — Dashboard create/edit form + bilingual inventory  
3. `337459e` — Schema migration comment-split fix  
4. `8cceb29` — Vacancy smoke candidate FK fix  
5. `e8e7cc8` — Staging APPLY WhatsApp env for smokes  
6. `895f67a` — Reject unknown statuses before normalize  
7. `f813951` — Idempotent status no-ops  

## Lifecycle transition matrix

| From \\ To | draft | open | paused | closed |
|-----------|-------|------|--------|--------|
| draft | noop | publish (`jobs.publish`) | — | close (`jobs.close`) |
| open | — | noop | pause (`jobs.close`) | close (`jobs.close`) |
| paused | — | resume (`jobs.publish`) | noop | close (`jobs.close`) |
| closed | — | reopen (`jobs.publish`) | — | noop |

- Intake accepts applications **only** when status = `open`.
- Content edits never change status.
- Create with existing position code → `409 position_code_conflict` (no silent reopen).

## Permissions matrix

| Permission | owner | hr_manager | recruiter | hiring_manager | viewer |
|------------|-------|------------|-----------|----------------|--------|
| jobs.read | ✓ | ✓ | ✓ | ✓ | ✓ |
| jobs.create | ✓ | ✓ | ✓ | — | — |
| jobs.edit | ✓ | ✓ | ✓ | — | — |
| jobs.publish | ✓ | ✓ | — | — | — |
| jobs.close | ✓ | ✓ | — | — | — |

**Temporary compatibility:** `settings.manage` ⇒ create/edit/publish/close; `prehire.read` ⇒ read.

## Authority-source inventory

| Surface | Authority |
|---------|-----------|
| Dashboard Jobs APIs | Postgres `positions` via `prehire_jobs` |
| Admin Assistant create/close/pause/reopen | `prehire_jobs.create_job` / `transition_job` |
| Candidate WhatsApp / public apply | `public_role_by_apply_code` (`status = open` only) |
| Ranking / overview job lists | positions inventory query |
| Mobile positions list | same positions query (mobile Jobs UI out of scope) |

## Retired / quarantined paths

| Path | Status |
|------|--------|
| File-based `data/companies/*/positions/*.json` via Octopus `listActivePositions` | Quarantined unless `WATHEFNI_FILE_POSITIONS_ENABLED=true` |
| Legacy upsert that set `status='open'` on conflict | Removed — conflict or explicit edit only |
| Hardcoded APPLY WhatsApp default in product paths | Removed — env-owned (`WATHEFNI_APPLY_WHATSAPP_NUMBER` → `WATHEFNI_WHATSAPP_NUMBER`) |
| Misleading “Active QR codes” metric | Aliased honestly to open roles; UI label is “Open roles” |

## Vacancy calculation

```
remaining_vacancies = approved_headcount (positions.vacancies) − COUNT(applications where status='hired')
```

Hired is the only vacancy-consuming state. Application counts never infer headcount.

## Staging smoke proof

Full `ops/staging-smoke.sh` **PASSED**, including:

- Jobs pagination  
- Jobs Phase 1 lifecycle / conflict / stale / vacancy / WA link / file quarantine  
- Job close/reopen (+ pause/resume)  

## Remaining Jobs gaps (post Phase 1)

- Public careers pages  
- Mobile Jobs management UI  
- Recruiter/HM picker UX (IDs are free-text for now)  
- Cursor pagination UX in dashboard (API supports cursor; UI still uses offset load-more)  
- Filter chips for recruiter/hiring manager from team roster  
- Dedicated pause/resume Assistant confirm copy polish in Arabic  
- Production APPLY number must be set explicitly before promote  
- Screenshots / EN-AR visual soak by owner on staging tunnel  

## Production recommendation

**Do not promote yet.** Staging is green for Phase 1 core authority and management. Before production:

1. Set `WATHEFNI_APPLY_WHATSAPP_NUMBER` on production unit (no hardcoded fallback).  
2. Owner soak: create draft → edit → publish → pause → resume → close → reopen on staging UI.  
3. Confirm existing production-compatible jobs migrate cleanly (staging inventory survived; count grew then cleaned).  
4. Keep Overview production contracts untouched during promote.
