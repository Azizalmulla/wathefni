# Jobs Phase 1 UX Polish — Production Promotion

**Status:** PRODUCTION GREEN — verification complete  
**Commit:** `898e05a` — fix: polish Jobs Phase 1 owner UX for clarity and bilingual use  
**Production artifact SHA:** `054b555a1afc728269ef5f9db66549a7205b5fa813d3d1784f812b7daf1e641b`  
**Matches staging green:** yes (`/opt/wathefni/staging/last-green.sha256`)  
**Live dashboard asset:** `dashboard-CP32tJQ9.js` (prod ↔ staging dist identical)

## Scope

Dashboard-only UX polish. No Jobs lifecycle, schema, permissions, APPLY routing, WhatsApp number, Assistant behavior, backend authority, or production data changes.

## Pre-deploy gates

| Gate | Result |
|---|---|
| Shipping artifact = staging green `054b555…` | PASS |
| Production backup created | `/opt/wathefni/backups/predeploy-20260720T231128Z/` (`orchestrator.tgz`, `dashboard-public.tgz`) |
| Rollback available | `ops/deploy.sh rollback` against that snapshot |
| `prehire_jobs.py` unchanged | `5b2e722bb5f0fd5892f5d76c9ae5dabbb4e0e86d3dfca797cebfa1ea28161896` |
| `app.py` unchanged | `b07f1a56652e8b891224013b93ea05aa6fd6fc3d6130998a7993dfb8aaba0717` |
| APPLY number | `WATHEFNI_APPLY_WHATSAPP_NUMBER=96599338566` (unchanged) |

## Counters (before → after)

| Metric | Before | After |
|---|---|---|
| `positions` | 10 | 10 |
| `applications` | 17 | 17 |

No outbound / APPLY activity change observed. Health `200`. Public dashboard `200`.

## Visual verification (production)

Evidence: `ops/reports/jobs-phase1-ux-polish/production/`

| Check | Result |
|---|---|
| Duplicate Open / Open roles metric gone | PASS |
| One clear Jobs title + subtitle | PASS |
| Arabic title `الوظائف`, RTL, lifecycle badges (`مفتوحة`) | PASS |
| Ownership fields inside Ownership (optional) | PASS |
| Sticky Save draft / Publish on long form | PASS |
| Detail drawer Done (not Cancel next to Close) | PASS |
| Pause / close confirm consequence copy | PASS (UI); resume / reopen / publish consequence strings present in shipped JS |
| Missing optional values as `—` | PASS |
| Desktop + narrower laptop layouts clean | PASS |

Automated visual checks: **23 passed, 0 failed** (`production/visual-verify.json`).

## Dashboard / smoke totals

| Suite | Result |
|---|---|
| Dashboard vitest | **10 files, 47 passed, 0 failed** |
| Deploy preflight (production) | passed (schema/health/public-route guard) |
| Production health | `/health` → **200** |
| Public dashboard | **200**, asset `dashboard-CP32tJQ9.js` |

Full `staging-smoke.sh` is staging-scoped; production smoke here is deploy preflight + health + public-route + authenticated visual verification.

## Backend hash confirmation

| File | Production SHA |
|---|---|
| `prehire_jobs.py` | `5b2e722bb5f0fd5892f5d76c9ae5dabbb4e0e86d3dfca797cebfa1ea28161896` |
| `app.py` | `b07f1a56652e8b891224013b93ea05aa6fd6fc3d6130998a7993dfb8aaba0717` |

Identical to pre-promote / staging authority hashes.

## Remaining non-blocking issues

1. Global sidebar / PRE-HIRING shell labels stay English when Jobs content is Arabic (existing product pattern).
2. Create/edit form remains long (bilingual descriptions); sticky actions mitigate reachability.
3. Create-form abort still labeled **Cancel** (correct for abandon-create); only the **detail drawer** uses **Done / تم**.
4. Unused `Open roles` string may still exist in the JS bundle; it is not rendered on the Jobs inventory.
5. Jobs inventory “Total applications” tile can read lower than raw `applications` table count depending on open-role aggregation (UI 10 vs DB 17) — pre-existing metric semantics, unchanged by this polish.

## Rollback

```bash
# from orchestrator ops on the VPS / deploy host
ops/deploy.sh rollback
# restore point: /opt/wathefni/backups/predeploy-20260720T231128Z
```

Stop after production verification.
