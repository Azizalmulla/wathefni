# Jobs Phase 1 UX Polish — Staging Follow-up

**Status:** STAGING GREEN — HOLD before production  
**Commit:** `898e05a` — fix: polish Jobs Phase 1 owner UX for clarity and bilingual use  
**Staging artifact SHA:** `054b555a1afc728269ef5f9db66549a7205b5fa813d3d1784f812b7daf1e641b`  
**Base production authority (unchanged):** `0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1` / `b35e9a1`

## Scope

Frontend-only dashboard UX polish validated in the owner soak. No backend logic, lifecycle, schema, permissions, APPLY routing, Assistant behavior, or production data changes.

### Included

- Remove duplicate Open / Open roles metric
- Drawer dismiss: Done / تم (not Cancel)
- Ownership (optional) collapsed section for recruiter / hiring manager
- Localized Jobs title + subtitle (EN/AR + RTL)
- Remove duplicated in-page subtitle
- Sticky Save draft / Publish / Save changes on long forms
- Localized lifecycle status badges (AR)
- Consequence-based confirmations for pause, resume, close, reopen, publish
- Preserve intentional `—` for missing optional legacy values

## Backend / runtime authority unchanged

| File | Staging SHA | Production SHA |
|---|---|---|
| `prehire_jobs.py` | `5b2e722bb5f0fd5892f5d76c9ae5dabbb4e0e86d3dfca797cebfa1ea28161896` | same |
| `app.py` | `b07f1a56652e8b891224013b93ea05aa6fd6fc3d6130998a7993dfb8aaba0717` | same |

No APPLY env changes. Production remains on authority artifact `0c0ac7a…`.

## Tests

- Dashboard vitest: **10 files, 47 passed, 0 failed**
- Staging smoke (`ops/deploy.sh staging`): **ALL STAGING SMOKE CHECKS PASSED**

## Screenshots

### Before (production green UI)

- `before/inventory-en-desktop.png`
- `before/inventory-ar-desktop.png`
- `before/inventory-en-laptop.png` (if present)

### After (staging UX polish)

- `after/inventory-en-desktop.png`
- `after/inventory-en-laptop.png`
- `after/inventory-ar-desktop.png`
- `after/form-create-en.png` (Ownership optional + sticky actions)
- `after/drawer-en.png` (Done label)

### Proof notes (after)

- `Open roles` absent; duplicate page subtitle count = 1 (shell only)
- Ownership optional section present on create form
- Drawer Done present; Cancel not adjacent to Close job
- Arabic title `الوظائف`, RTL, `مفتوحة` status label

## Production recommendation

**HOLD.** Promote this dashboard-only artifact after owner visual sign-off. Do not re-touch APPLY number, lifecycle APIs, or production data as part of this polish.

Stop before production.
