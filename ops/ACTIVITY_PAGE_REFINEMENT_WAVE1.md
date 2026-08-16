# Activity Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T135815Z`  
**Evidence:** `ops/evidence/activity-page-refinement-wave1-prod-deploy-20260804T135815Z/`  
**Freeze:** `ops/ACTIVITY_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Live:** `/var/www/wathefni-dashboard/assets/` (`PostHire-B64Y1FhV.js`, `dashboard-JUpl8ZLI.js`)  
**Backup:** `/opt/wathefni/backups/production-pre-activity-page-refinement-wave1-20260804T135815Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** (`ACTIVITY_PAGE_WAVE1_SMOKE_OK`) |
| Read-only / permission proof | **GO** (`MUTATION_READONLY_PROOF_OK`) |
| Freeze Activity Page Wave 1 | **GO / FROZEN** |
| Audit authority / event definitions | **NO-GO** (unchanged) |
| Alerts / Compliance freezes | **UNTOUCHED** |

## Implementation-truth findings

| Finding | Truth |
|---|---|
| Mount | `ActivityLog` via `page=activity`; gated by `audit.read` |
| Pre-wave | Shell + “Company activity” card duplicated purpose; decorative category colors; summary prose collapsed who/what/subject |
| Permissions | `owner` / `hr_admin` only; UI wrongly said “HR Managers” |
| Mutations | None (GET + CSV download only) |

## Final event structure

1. Compact purpose + event count summary + Export CSV  
2. Filters: date · actor · module/category · action · result · search  
3. Chronological groups (Today / Yesterday / …)  
4. Each event: outcome badge · category (quiet text) · time · **who** · **what** · **affected** · Details  

Technical `action_type`, event id, raw status, actor email behind **Details**.

## Exact duplication and technical clutter removed

- Duplicate “Company activity” card heading / description  
- Decorative per-category color chips / icon circles (`CATEGORY_META`)  
- First-paint reliance on collapsed summary prose alone  
- Incorrect “HR Managers” RBAC copy  
- Raw implementation language on first paint (moved behind Details)

## Filter / search / export behavior

| Control | Behavior |
|---|---|
| Date / actor / category / search | Existing `GET /dashboard/activity` params |
| Action | Wires existing `action_type` param |
| Result | Client-side filter on loaded statuses (Done / Failed / Needs confirmation / Partly done) |
| Export CSV | Same filters (except client-only result); unchanged backend CSV |

## Permissions and read-only proof

- Gate: `audit.read` → Owners and HR Admins  
- No POST/PUT/PATCH/DELETE on Activity UI  
- Live proof: `verify/smoke-prod.out` + deploy `MUTATION_READONLY_PROOF_OK`

## Screenshots

`ops/evidence/activity-page-refinement-wave1-prod-deploy-20260804T135815Z/screenshots/`

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-activity-page-refinement-wave1-20260804T135815Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-activity-page-refinement-wave1-20260804T135815Z
```
