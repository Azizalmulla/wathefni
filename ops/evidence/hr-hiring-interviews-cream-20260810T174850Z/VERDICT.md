# HR Hiring + Candidates list + Interviews — cream honesty ship

Stamp: `20260810T174850Z`  
Surfaces: `/hr/hiring` · `/hr/jobs` · `/hr/candidates` · `/hr/interviews` · `/hr/interviews/[id]`  
Actor spine: Aziz owner `96599338566`  
Mode: **ship + freeze**

## Functional verdict: **PASS — FROZEN**

Combined honesty + cream wave closed the CONDITIONAL audit blockers. Hiring home, Candidates list, and Interviews list/detail freeze **together**.

## Live spine (post-deploy)

| Check | Result |
| --- | --- |
| Priority destinations | follow-up/ready/assessment → `/jobs`; role → `/candidates?position=HR` |
| Unscoped candidates | `requires_position=true`, `ranking_unavailable=true`, total 0 |
| Scoped `position=HR` | total 3 / 2 items, not requires_position |
| Interviews | 4 rows; sample UUID present |
| Detail tokens | `updated_at` ISO + `notes_version` present on mobile DTO |
| Notes with DTO tokens | **OK** (`save_notes_only` accepted ISO `expected_updated_at`) |
| Backend backup | `/opt/wathefni/backups/hr-hiring-interviews-20260810T174850Z` |

## Client honesty

- Ranking/Candidates browse → Jobs picker first; Assessments omitted
- Candidates cream queue surfaces calm requires-position (never fake empty ranked pipeline)
- Assistant interviews use `interview_id` only; ranking/jobs → Jobs; assessments web-only
- Notes editor sends concurrency tokens; stale/error inline; invalidates Hiring/Interviews caches
- Upcoming kind labels via i18n keys; priority copy localized EN/AR
- Cream: Candidates list + Interviews list/detail + Jobs via `PageScreen` + `HrPushedNav` + ListRow/StatusChip

## Ship

| Field | Value |
| --- | --- |
| OTA | `56af1a85-d1b3-494d-957f-2f9668b93ac1` |
| iOS update | `019feccc-30a3-7fa6-958a-a733106dea71` |
| Runtime | 0.3.0 · canary |
| Gates | verify-hr-hiring-home · verify-hr-hiring-interviews-wave · physical-hr-hiring-interviews-en-ar · verify-hr-mobile-assistant · tsc · spine-probe · health 200 |
| Freeze | `.cursor/rules/hr-mobile-hiring-interviews-freeze.mdc` |
| Debt | `ops/HR_MOBILE_HIRING_INTERVIEWS_CONTRACT_DEBT.md` |

## Lock criteria — closed

- [x] Position-scoped Candidates + `requires_position` EN/AR
- [x] Interview notes concurrency tokens; stale/error inline; invalidate list/Hiring
- [x] Assistant interview deep-link uses `interview_id` (or list only)
- [x] Browse honesty: Jobs path; Ranking/Candidates via position; Assessments hidden
- [x] Cream migration for Candidates list + Interviews list/detail
- [x] Upcoming / priority copy EN/AR
- [x] Physical EN+AR pass
- [x] Stamp PASS and freeze Hiring + Candidates list + Interviews together
