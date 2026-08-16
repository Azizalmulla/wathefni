# Jobs Phase 1 — Owner UI Soak (staging only)

**Date:** 2026-07-20  
**Artifact SHA:** `0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1`  
**Scope:** Staging owner Jobs UI soak against Phase 1 backend; no production changes.  
**Recommendation:** **HOLD before production promotion.**

## Visual assessment

Jobs Phase 1 reads as a real job-management surface: inventory metrics, filters, bilingual create/edit, lifecycle actions, APPLY/QR in the drawer. Laptop width stays usable. Null owner/deadline render as intentional `—`.

Save draft / Save changes / Publish are visually distinct. Pause vs Close are both present; confirmation copy now states temporary intake stop vs closing intake (reopenable).

Form is still long (bilingual descriptions/requirements) but primary fields are grouped and ownership is collapsed. Sticky action bar keeps draft/publish reachable.

Arabic page title/subtitle and RTL content work; sidebar shell labels remain English (pre-existing product pattern). Status badges now use Jobs lifecycle copy in AR.

## Screenshots

Evidence in this folder:

- `jobs-inventory-en-desktop.png`
- `jobs-inventory-en-laptop.png`
- `jobs-inventory-ar-desktop.png`
- `jobs-form-create-en.png`
- `jobs-form-create-ar.png`
- `jobs-search-en.png`
- `jobs-drawer-en.png`

## UX issues found

1. Duplicate “Open” vs “Open roles” metrics (same count).
2. Drawer dismiss labeled “Cancel” next to “Close job”.
3. Raw recruiter/hiring-manager user ID fields felt broken/overwhelming.
4. Shell title stayed English “Jobs” while page content was Arabic.
5. Duplicate page subtitle under shell subtitle.
6. Status pills used candidate `stageLabel` (English Open/Closed) in Arabic UI.
7. Pause/Close confirm bodies were thin (title alone).

Non-blocking remainders: form length; global sidebar not localized; salary/ownership IDs still advanced.

## Contained fixes made (staging dashboard only)

- Removed redundant Open roles metric; metrics = Open / Draft / Paused / Closed / Applications.
- Drawer dismiss → Done / تم.
- Ownership fields under collapsed “Ownership (optional)”.
- Shell Jobs title + subtitle follow recruiting locale + RTL.
- Removed duplicate in-page subtitle.
- Sticky form action bar for Save draft / Publish / Save changes.
- Localized job status badges + clearer pause/close/resume/reopen confirm bodies.
- Dashboard rebuilt and rsynced to `/opt/wathefni/staging/dashboard-dist/` only (backend artifact unchanged).

Prepared (not installed) production env file: `production-apply-whatsapp.env.prepared`.

## Dashboard test totals

`apps/wathefni-dashboard` vitest: **10 files, 47 passed, 0 failed**.

## Owner UI soak

Playwright owner soak: **30 passed, 0 failed** (API lifecycle + EN/AR UI checks + APPLY `96599338566`). See `soak-results.json`.

## Full staging smoke

`ops/staging-smoke.sh` on staging VPS: **ALL STAGING SMOKE CHECKS PASSED** (0 FAIL lines). Production not touched.

## Final staging artifact SHA

`0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1`  
(Confirmed via `/opt/wathefni/staging/last-green.sha256` after dashboard-only sync.)

## Production APPLY WhatsApp number

**Intended live candidate number: `96599338566`.**  
Staging already has `WATHEFNI_APPLY_WHATSAPP_NUMBER=96599338566`.  
Production systemd unit does **not** yet set this variable — prepare only:

```
WATHEFNI_APPLY_WHATSAPP_NUMBER=96599338566
```

Orchestrator product path (`prehire_jobs.apply_whatsapp_number` / `apply_link`) fails closed if unset; APPLY links, wa.me, QR payloads, and Assistant share actions use that helper / env.

## Remaining hard-coded-number inventory

**Product APPLY path conflicts (same number, not env-owned):**

| Location | Notes |
|---|---|
| `ai-recruiter/app/routers/internal.py` | Hardcoded `wa.me/96599338566?text=APPLY-...` |
| `ai-recruiter/app/services/qr_generator.py` | `WHATSAPP_NUMBER = "96599338566"` default |

**Not APPLY destination (operator/HR fixtures / smoke / scripts):** many `96599338566` as HR phone in smokes/ops; `scripts/send-whatsapp-qr-same-process.mjs` default target; dashboard test localStorage. These are not candidate APPLY routing.

**No conflicting different APPLY number found** — leftovers match the intended number but bypass env ownership in legacy ai-recruiter paths.

## Production recommendation

**HOLD.** Promote Jobs Phase 1 only after:

1. Explicit install of `WATHEFNI_APPLY_WHATSAPP_NUMBER=96599338566` on production orchestrator unit.
2. Optional follow-up: wire ai-recruiter QR/internal APPLY builders to the same env (or retire those paths).
3. Owner sign-off on staging Jobs UX soak evidence above.

Do **not** promote from this soak alone.
