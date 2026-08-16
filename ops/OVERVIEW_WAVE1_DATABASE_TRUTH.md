# Overview Wave 1 — Database Truth & Entity Units

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260727T223623Z`  
**Host:** `root@76.13.63.68`  
**Scope:** Overview database-backed units only  
**Not in this wave:** Ranking behavior, Assessments behavior, destination routing, colors

---

## Final verdict

**PASS — Wave 1**

Every Overview headline metric now declares its unit. Display counts that say “candidates” are distinct confirmed **people** (same identity authority as Candidates). Application counts are published beside them. Accounting Excel no longer shows overlapping signal sum `3`. Top priorities is person-first. Role next steps are backend pressure-ordered.

---

## What changed

### Backend (`wathefni-orchestrator/prehire_overview.py` + summary wiring)

- Synced production assessment-pending definition into repo (`pending|in_progress|expired`, assigned-only).
- Added confirmed person identity SQL matching Candidates:
  - grounded email → `email:…`
  - else non-surrogate phone digits → `phone:…`
  - else `singleton:{app_key}`
- `compute_action_counts` now returns:
  - display keys as **people**
  - `*_people` / `*_applications`
  - `units` + `metrics[]` with explicit unit
- `compute_role_priority` / `role_next_steps`:
  - `people_count` / `application_count` / `display_count`
  - `signals` kept separate (never summed for the card value)
- `compute_work_queue` returns **person** rows with nested `actions` + `applications`
- Summary exposes `role_next_steps`

### Frontend (`apps/wathefni-dashboard`)

- Overview cards consume backend people counts + optional application hints
- Role card uses `display_count` / `people_count` (no FE signal sum)
- Top priorities renders one person row with job/stage + nested action/app hints
- Role next steps uses `summary.role_next_steps` (backend pressure order)
- No Ranking / Assessments / routing changes

---

## Live WATHEFNI proof (`20260727T223623Z`)

| Metric | Unit | People (display) | Applications | Notes |
|---|---|---:|---:|---|
| Follow-up | people | **2** | **4** | Was showing 4 as “candidates” |
| Review ready | people | **2** | **3** | Distinct confirmed people (email-first identity) |
| Assessment attention | people | **2** | **3** | Routing unchanged |
| Accounting Excel card | people | **1** | **1** | Signals remain 1/1/1 separately — not shown as `3` |
| Top priorities | people | **3** rows | 14 nested actions | One row each: Aziz, Hamad, Faisal |
| Role next steps | jobs | pressure-ordered | — | ACCOUNTING_EXCEL → HR → ACCOUNTING → FULLSTACK → FINANCE; no 0-active above urgent |

Evidence: `/opt/wathefni/production-evidence/overview-wave1-database-truth/20260727T223623Z/live-proof.json`

### Assertions

- `follow_up_needed == 2` and `follow_up_needed_applications == 4`
- `units.follow_up_needed == "people"`
- Accounting Excel `people_count == display_count == 1` (not 3)
- Work queue `unit == "people"` and unique `person_key`s
- Role next steps pressure descending; all `active > 0`
- Health **200** before / after rollback / after restore

---

## Health / rollback / restore

| Step | Result |
|---|---|
| Health after deploy | **200** |
| Rollback to previous `prehire_overview.py` | Health **200** |
| Restore Wave 1 module | Health **200**; follow-up people/apps `2/4` restored |
| Dashboard asset | `dashboard-CelXMCur.js` live under `/var/www/wathefni-dashboard` |
| Lifecycle / data mutations | **None** (read-only SQL + UI deploy) |

Rollback artifacts:

- `/opt/wathefni/production-evidence/overview-wave1-database-truth/20260727T223623Z/prehire_overview.py.before`
- `/opt/wathefni/production-evidence/overview-wave1-database-truth/20260727T223623Z/prehire_overview.py.after`
- `/var/www/wathefni-dashboard.wave1-before`
- `/opt/wathefni/apps/wathefni-dashboard/dist-old-20260727T223623Z`

---

## Unit / contract notes

- Metric units: `people` | `applications` | `actions` | `jobs`
- Overview copy “candidates” → people display keys
- Dual publication: `*_people` + `*_applications` + `metrics[]`
- Repo and production `prehire_overview.py` are aligned (Wave 1 after file)
- Local tests: `smoke-test-prehire-overview-unit.py` PASS; `prehireOverviewPresentation.test.ts` + `App.test.tsx` PASS

---

## Intentionally deferred

- Ranking auto-load / score presentation
- Assessments send/resend routing and queue parity
- Overview destination URL filter persistence
- Interview filter honor on destination

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Each metric declares unit | **PASS** |
| Follow-up shows 2 candidates, not 4 | **PASS** |
| Accounting Excel shows 1, not 3 | **PASS** |
| Top priorities one row per person | **PASS** |
| Role ordering reflects pressure | **PASS** |
| Backend and UI counts match (backend-authoritative) | **PASS** |
| No lifecycle/data mutations | **PASS** |
| Health 200 | **PASS** |
| Rollback + restore | **PASS** |

**Wave 1: PASS**
