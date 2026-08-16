# Shifts Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T074315Z` (IA) · **Composer-org:** `20260804T075708Z` · **UX Closure:** `20260804T082135Z`  
**Evidence:** `ops/evidence/shifts-page-refinement-wave1-prod-deploy-20260804T074315Z/`  
**Composer-org evidence:** `ops/evidence/shifts-page-refinement-wave1-composer-org-20260804T075708Z/`  
**UX Closure evidence:** `ops/evidence/shifts-wave1-ux-closure-prod-deploy-20260804T082135Z/`  
**Freeze:** `ops/SHIFTS_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundle (live):** `/var/www/wathefni-dashboard/assets/PostHire-bz887YSK.js`  
**Backup (UX Closure):** `/opt/wathefni/backups/production-pre-shifts-wave1-ux-closure-20260804T082135Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy (IA) | **GO** |
| Composer-org correction | **GO** |
| UX Closure (Planning + native dialogs) | **GO** |
| Safe smoke | **GO** (`SHIFTS_WAVE1_UX_CLOSURE_SMOKE_OK`) |
| Freeze Shifts Wave 1 | **GO / FROZEN** (amended) |
| Payroll Wave 1 | **UNTOUCHED** (`20260804T080520Z`) |
| Backend / freeze reopen / payroll money | **NO-GO** (not done) |

## IA correction

| Before | After |
|---|---|
| 8 peer tabs | **Schedule / Requests / Planning** |
| Duplicated inner Shifts h1 | Removed (shell owns title) |
| Delivery-failure strip on Shifts | Excluded |
| Honesty/lab chips on first paint | Admin Advanced operations only |
| Free-text branch/site/team filters | Governed org-unit selects |
| Free-text composer org keys | Governed selectors + **Unmapped** for legacy |
| Competing primaries | One primary: **Schedule a shift** |
| Loud Refresh | Ghost icon |
| Thin empty text | Empty state + Schedule CTA |

## Composer-org amendment (`20260804T075708Z`)

- Create: branch / site / team / location from Organization IDs; parent→child filtering when hierarchy exists
- Edit/detail: same fields, disabled; legacy values show **Unmapped** + stored value (not discarded)
- Role remains free-text (not an org unit)
- `expected_updated_at` / create-cancel-reschedule contracts unchanged

## UX Closure amendment (`20260804T082135Z`)

### Planning for normal HR

- Shows: **Templates**, **Recurring schedules**, **Publishing**, **Coverage**
- **Rotations** only when wave6 is enabled **and** patterns/assignments exist
- Plain HR copy (no “real mutation”, “named allowlist”, “concurrency token”, “no automated government submission”)

### Advanced operations (admin)

- Visible when actor has `settings.manage` **or** `users.manage`
- Contains: readiness/authority chips (softened), system reminders, compliance/PAM export (read-only framing)
- Backend gates, audit, permissions, concurrency unchanged

### Native dialogs

- Shifts soft-cancel + reconciliation cancel → shared `ConfirmDialog` / `withReason`
- Also replaced low-risk: Jobs unsaved discard, Attendance mapping name
- Deferred Employees/document prompts — see `ops/SHIFTS_WAVE1_UX_CLOSURE_NATIVE_DIALOG_INVENTORY.md`
- Payroll not modified

## Smoke

`verify/smoke-prod.out` / UX Closure `deploy.out` — `SHIFTS_WAVE1_UX_CLOSURE_SMOKE_OK`

## Screenshots

`ops/evidence/shifts-wave1-ux-closure-prod-deploy-20260804T082135Z/screenshots/`

## Residual

- Empty org catalogs show “Not set” / “All …” until units exist
- Reschedule API does not rewrite org keys; edit shows preserved org as read-only
- Employees native prompts deferred (D1–D6)

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave1-ux-closure-20260804T082135Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-wave1-ux-closure-20260804T082135Z
```
