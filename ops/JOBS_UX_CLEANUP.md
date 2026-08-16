# Jobs UX Cleanup

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T004101Z`  
**Host:** `root@76.13.63.68`  
**Scope:** UX-only cleanup for Manage job and Edit job  
**Explicitly unchanged:** backend truth, data authority, lifecycle logic, backend contracts, colors system-wide, unrelated pages

---

## Final verdict

**PASS**

Manage job is no longer one long crowded drawer; it is a dedicated workspace with clear tabs. Edit job is no longer one giant form; it is grouped into collapsible sections with a single sticky save area. All existing save/publish/status/copy/QR actions and payloads are preserved. Health 200 before/after, rollback and restore proven.

---

## What changed

### Manage job (`src/components/JobWorkspace.tsx`)

Replaces the old inline `JobDrawer` in `src/App.tsx`.

- Dedicated full-page sheet (`max-w-5xl`, calm background), not a narrow crowded drawer.
- Header: status badge, position code, title, description, and lifecycle actions (Edit / Pause / Resume / Publish / Close / Reopen) grouped on one row.
- Tabs:
  - **Overview** — key job facts only; empty/non-useful fields hidden by default (department, location, deadline, age, salary, recruiter only render when present).
  - **Sharing** — application code, application link, QR, and copy/download actions in one card.
  - **Applicants** — candidate funnel by stage + recent applicants.
  - **Activity** — candidate contact activity only.
- Requirements/description moved under **Overview → Candidate-facing content** instead of dominating the drawer.
- EN/AR + RTL preserved (`dir` follows locale).

### Edit job (`src/components/JobsForm.tsx`)

- Grouped into collapsible sections:
  - **Basics** (titles, code, visibility)
  - **Hiring setup** (department, location, employment type, work arrangement, vacancies, dates)
  - **Candidate-facing content** (summaries, descriptions, requirements, approvals)
  - **Advanced / optional** (contract, salary, ownership) — collapsed by default
- Single sticky save bar at the bottom with preview toggle and one set of actions (no repeated Save buttons mid-form).
- Same `JobFormValues`, validation, and `jobFormToPayload` contract — no backend behavior change.

### Copy (`src/lib/recruitingLifecycle.ts`)

- Added EN/AR labels for the new workspace tabs/sections only; existing job labels reused.

---

## Before / after

| Area | Before | After |
|---|---|---|
| Manage job | One long drawer mixing facts, sharing, QR, requirements, funnel, applicants, activity | Workspace with Overview / Sharing / Applicants / Activity tabs |
| Key facts | Always a dense 2-column grid with many “—” rows | Only useful populated facts shown by default |
| Sharing | Nested `<details>` + side QR column | Dedicated Sharing tab with code/link/QR/actions together |
| Edit job | One long form, ownership `<details>`, duplicate save buttons | Collapsible sections + one sticky save area |
| Actions | Buttons scattered at top and bottom | Lifecycle actions in header; save actions only in sticky bar |

---

## Production proof (`20260728T004101Z`)

Evidence: `/opt/wathefni/production-evidence/jobs-ux-cleanup/20260728T004101Z/`

| Assertion | Result |
|---|---|
| Health before deploy | **200** |
| Health after deploy | **200** |
| New dashboard asset served | `dashboard-BJO95Dif.js` |
| Rollback asset restored | `dashboard-nFyK_VKW.js`; health **200** |
| Restore asset | `dashboard-BJO95Dif.js`; health **200** |
| Bundle markers (JobWorkspace tabs) | `jobsWsTabOverview`, `Key job facts`, `Candidate funnel by stage` |
| Build + tests | `vite build` PASS; **17/17 test files, 89/89 tests** |
| Backend modules touched | None |
| Payload/authority change | None (`jobFormToPayload`, status actions unchanged) |

---

## Rollback / restore

| Step | Result |
|---|---|
| Dashboard rollback → previous asset | `dashboard-nFyK_VKW.js`; health **200** |
| Dashboard restore → Jobs UX asset | `dashboard-BJO95Dif.js`; health **200** |

Artifacts:

- `wathefni-dashboard.before`
- `wathefni-dashboard.after`
- `asset.before.txt` / `asset.after.txt` / `asset.rollback.txt` / `asset.restore.txt`
- `health.before` / `health.after` / `health.rollback` / `health.restore`
- `bundle-markers.txt`

---

## Remaining limitations

- The workspace is a large sheet over the Jobs page, not a separate routed URL (keeps Wave 2 URL behavior unchanged).
- Overview intentionally hides empty HR fields; users still edit them in Edit job under their grouped sections.
- Job list table and other pages were not redesigned in this wave.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Manage job uses dedicated workspace + tabs | **PASS** |
| Overview hides empty/non-useful fields | **PASS** |
| Sharing/Applicants/Activity grouped | **PASS** |
| Edit job grouped + collapsible + single sticky save | **PASS** |
| No repeated save buttons | **PASS** |
| EN/AR + RTL | **PASS** |
| No backend/data/lifecycle change | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated page redesign | **PASS** |

**Stop after Jobs UX cleanup.**
