# Multi-User Workspace Wave 5 — Concurrency & Collaboration Safety

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260728T222833Z`  
**Evidence:** `/opt/wathefni/production-evidence/multi-user-wave5-concurrency/20260728T222833Z/`  
**Scope:** Optimistic concurrency / version protection for shared editable HR records  
**Preserved:** Waves 1–4 (roles, visibility, ownership, personal work queues)  
**Out of scope:** Wathefni Calendar  

---

## Verdict

**PASS.** Shared editable surfaces no longer silently last-write-wins. Mutations require `expected_version` and/or `expected_updated_at`; stale writes return **409** with who/when/current version and safe next action `reload_latest`. Frontend shows the required human message (EN/AR), allows refresh of latest, and keeps unsaved draft text on interview-notes conflict. Company settings, interview notes, assessment review drafts, jobs/forms, notes, tasks, and ownership remain protected. Health **200**. Rollback/restore proven. Waves 1–4 regression smoke passed. No Calendar.

---

## Contract

| Rule | Behavior |
|---|---|
| Authority | Backend `version` and/or `updated_at` (+ `updated_by_*` where applicable) |
| Mutation | Client must send `expected_version` and/or `expected_updated_at` |
| Missing token | **422** `missing_expected_version` (when `require_expected` / required path) |
| Stale write | **409** conflict — never silent overwrite |
| Conflict body | `conflict=true`, human `message` / `message_ar`, `last_changed_by`, `last_changed_at`, `current_version`, `safe_next_action=reload_latest` |
| Locks | Soft optimistic only — no hard page locks |

Canonical human message (EN):  
`This was updated by another user. Review the latest version before saving.`

---

## Protected surfaces

| Surface | Token | Stale code(s) |
|---|---|---|
| Company settings (visibility / import) | `version` + `updated_at` | `stale_settings_version` / `stale_settings_update` |
| Interview notes / feedback drafts | `notes_version` + `updated_at` | `stale_interview_notes` |
| Assessment review drafts | `expected_updated_at` / `expected_version` | `stale_assessment_review` |
| Jobs / shared pre-hire forms | `version` + `updated_at` | `stale_job_version` / `stale_job_update` |
| Candidate notes | note version (C2) | `stale_note_version` |
| Tasks | task version (C2) | `stale_task_version` |
| Job / candidate ownership | ownership version (Wave 3) | `stale_ownership_version` |
| Lifecycle transitions | lifecycle version | `stale_lifecycle_version` |

Module: `concurrency_safety.py` — `assert_fresh`, `require_expected_token`, `conflict_envelope`, `ConcurrencyError`.

---

## APIs / wiring

| Area | Change |
|---|---|
| `set_company_setting(..., expected_version=, expected_updated_at=, require_expected=, actor=)` | Version bump + `updated_by_*`; dashboard PUTs require token |
| Settings GET | Returns `version`, `updated_at`, `last_updated_by` |
| Interview `save_notes_only` | Requires expected tokens; schema `notes_version`, `updated_by_user_id` |
| Assessment review request | `expected_updated_at` / `expected_version` |
| `prehire_jobs._assert_fresh` | Token **required** (no optional LWW) |
| Notes / tasks / ownership | Existing version checks enriched with conflict envelope fields |

---

## Frontend

- `friendlyDashboardError` maps all Wave 5 / prior `stale_*` + `conflict` codes to the shared EN/AR message.
- Settings visibility: shows **Last updated** by + timestamp; save sends expected tokens; on 409 reloads latest meta.
- Interview notes: on 409 keep unsaved draft text, revalidate latest, user re-saves after review.
- Jobs / assessment review / notes / tasks: pass expected tokens from loaded record.
- No hard locks; refresh/reload latest is the safe next action.

Dashboard asset: `dashboard-Byp5Hy6_.js`.

---

## Audit

| Action | Trail |
|---|---|
| Settings create/edit | `company_settings.updated_by_*` + version bump |
| Interview notes edit | `updated_by_user_id` + `notes_version` |
| Job / form edits | Existing job version + audit paths |
| Notes / tasks create/edit/resolve/reassign | Collaboration + task events (prior waves) |
| Ownership claim/assign/reassign | Wave 3 ownership events |
| Conflict responses | Actor label + timestamp from last writer |

Actor and timestamp on conflict responses match the last successful writer (`live-proof.json`).

---

## Proofs

| Gate | Result |
|---|---|
| Two users cannot silently overwrite | **PASS** — settings + interview notes live proofs |
| Stale save → 409 + human message | **PASS** (`stale_settings_version` / `stale_interview_notes`; message exact) |
| Latest data intact after stale attempt | **PASS** (`latest_intact`; settings version advanced only on fresh write) |
| Notes / tasks / settings protected | **PASS** (`notes_tasks_protected`; settings gates) |
| Ownership / lifecycle protections intact | **PASS** (Wave 3 regression; stale ownership codes retained) |
| Audit actor + timestamp | **PASS** (`last_changed_by` / `last_changed_at` in conflict) |
| Health | **200** |
| Rollback / restore | **PASS** — orch module absent (`False`) ↔ restored; dashboard `CYN46WBx` ↔ `Byp5Hy6_` |
| Waves 1–4 regression | **PASS** |
| Unrelated mutations | **PASS** — concurrency module + shared-edit wiring + conflict UX only |
| Calendar | **Not built** |

Smoke: `smoke-test-multi-user-wave5-concurrency.py` (+ Waves 1–4 after restore).  
Live: `live-proof.json`, `interview-notes-proof.json`.

---

## Source map

| Concern | Location |
|---|---|
| Conflict contract | `wathefni-orchestrator/concurrency_safety.py` |
| Settings OCC | `app.py` (`get_company_settings_row`, `set_company_setting`) |
| Interview notes OCC | `interview_service.py` + notes concurrency schema |
| Jobs OCC | `prehire_jobs.py` |
| Notes / tasks | `candidate_collaboration.py` |
| FE errors + draft preserve | `apps/wathefni-dashboard/src/App.tsx` |
| API client tokens | `apps/wathefni-dashboard/src/lib/api.ts` |
| Smoke | `smoke-test-multi-user-wave5-concurrency.py` |

---

## Remaining (not Wave 5)

- Calendar
- Hard locks (intentionally not added)
- Pushing every non-dashboard operator settings path onto `require_expected` (dashboard shared edits require it)

**Stop after Wave 5.**
