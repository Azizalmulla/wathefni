# Kuwait Pilot Document Journey — Staging Green

**Status:** staging-green  
**Production:** **not promoted / untouched** (no `kuwait_pilot_document_journey.py` on prod)  
**Date:** 2026-07-25 (Kuwait)  
**Prior staging-green:** `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267` (Kuwait first-client foundation)  
**This staging-green artifact:** `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7`  
**Staging-green file:** `/opt/wathefni/staging/last-green.sha256`  
**Artifact record:** `/opt/wathefni/staging/kuwait-pilot-document-journey-artifact.sha256`  
**Freeze manifest:** `ops/KUWAIT_PILOT_DOCUMENT_JOURNEY_FREEZE.txt`  
**Delivery:** `WATHEFNI_DELIVERY_MODE=dry_run`  
**Stop:** do **not** deploy to production until explicit owner approval of **exactly** this artifact.

---

## Verdict

The exact Kuwait pilot document journey artifact was surgically promoted to isolated staging and fully qualified. Additive `governed_document_*` schema was applied while foundation-green code remained safe. Journey matrix **68/68**, foundation **53/53**, Offers/Hiring **38/38**, optional-module-boundary **301/301**, onboarding/compliance/document smokes green, dashboard **49/49**, employee capability + typecheck green. Synthetic residue **zero**. **Production untouched. Stop.**

---

## Artifact SHA

| Item | Value |
|---|---|
| Staging-green artifact | `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7` |
| Orchestrator-only pin | `e418227b0acb87a688c2f4b721497d3219179de111713292c68af2796885d915` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator-staging.service` · `127.0.0.1:8011` |
| Database | `wathefni_staging` |
| Evidence | `ops/kuwait-pilot-document-journey/kuwait-pilot-document-journey-staging-20260725T042302Z.json` |

### Contained file SHAs

| File | SHA256 |
|---|---|
| `kuwait_pilot_document_journey.py` | `78befeb08da1f94dca5cb10f3bc6514d4799a6ad71e383fda0eeb50b294f99f4` |
| `ops/lib/doc_type_map.py` | `448d0946807db1ef493fa5bde8825798ead9fa0b0d63ff182b000e4bf6d510f0` |
| `app.py` (foundation-green `8d2e880a…` + document-journey hooks only) | `b266a0d24ff49659fb8966b03818f32f2e12fc76cf659ea28514ad8a447d7602` |
| `PostHire.tsx` | `e73d7027e6fc9a443d8a1f8fbae0ce055d010f7d189fc94cd56b9aaf64d00cf9` |
| `api.ts` | `2b767b3b25facd8aebd624f5a8b3da177b2cc57eed6e21fd93f734ef37057f01` |
| Employee mobile `documents.tsx` / `RemainingViews.tsx` / types / i18n | as in freeze manifest |

Unrelated local dirty tree content was **not** included. Staging `app.py` was derived surgically from foundation-green staging `8d2e880a…` via `ops/patch-staging-app-document-journey.py`.

---

## Backup and rollback

| Item | Value |
|---|---|
| Backup | `/opt/wathefni/backups/staging-pre-kuwait-doc-journey-20260725T041811Z` |
| DB dump SHA256 | `b8d9f5e3e403ae0b3928b0f09393707d65d5abd02c5a2f06f3eeca1adf0bd860` |
| Rollback | `bash /opt/wathefni/backups/staging-pre-kuwait-doc-journey-20260725T041811Z/ROLLBACK.sh` |
| Rollback restores | prior `app.py`, removes journey module, restores prior `last-green.sha256`, restores staging `dashboard-dist` |

---

## Migration and deployment order (executed)

1. **Verify frozen local artifact** — freeze manifest + SHA `4be5298e…`.  
2. **Verified staging backup** — dump + code snapshot + `ROLLBACK.sh`.  
3. **Record rollback commands** — see above.  
4. **Additive schema while old code running** — `ensure_document_journey_schema` via `/tmp` module only; staging still on foundation app `8d2e880a…`; health **200** (`PRE_SCHEMA_OLD_CODE_SAFE`).  
5. **Old code remained safe** during pre-code schema window.  
6. **Deploy exact orchestrator artifact** — journey module + surgically patched `app.py`; restart staging; health **200**.  
7. **Deploy exact dashboard artifact** — built dist → `/opt/wathefni/staging/dashboard-dist` only (**not** `/var/www`).  
8. **Deploy exact employee-mobile artifact** — frozen source tree → `/opt/wathefni/staging/employee-mobile-artifact` (API journey proven on staging; Expo binary not hosted on VPS).  
9. **Full staging qualification** — journey matrix + frozen regressions + frontend.  
10. **Clean synthetic fixtures** — KWDOC*/KWPILOT*/OFFERSTG/STBND* residue **0**.  
11. **Stop before production.**

---

## Exact screens / routes tested

| Surface | Route / handler |
|---|---|
| Employee onboarding upload | `POST /app/onboarding/documents` |
| Employee Documents list + compliance journey | `GET /app/documents` (status, expiry, renew, legitimacy note) |
| Employee Documents renewal | `POST /app/documents/renew` |
| HR dashboard upload | `POST /dashboard/posthire/employees/{key}/documents` |
| HR review decisions | `POST /dashboard/posthire/employees/{key}/documents/{type}/review` (`approve` / `reject` / `request_reupload` / `correct_metadata`) |
| HR compliance journey read | `GET /dashboard/posthire/employees/{key}/documents/compliance` |
| Dashboard UI artifact | Post-Hire HR reviewed / Reject / Enter dates + residence sensitive replace |
| Employee UI artifact | `/documents` renewal + EN/AR labels |

---

## Full gate matrix (document journey)

**Harness:** `ops/kuwait-pilot-document-journey-staging-matrix.py`  
**Marker:** `kuwait-pilot-document-journey-staging-v1`  
**Result:** **68 passed / 0 failed**  
**Evidence:** `ops/kuwait-pilot-document-journey/kuwait-pilot-document-journey-staging-20260725T042302Z.json`

Includes upload/handoff, review authority, renewal/versioning, OCR boundary, EN/AR UX, tenant isolation, unauthorized HR, append-only audit, reminder reset, zero residue, staging health.

---

## Version-history proof

Staging matrix proved for Article 18 synthetic employee:

- replacement stayed **pending** while prior **HR reviewed** remained current;  
- rejected replacement restored prior approved current;  
- newest approved renewal became current; prior became **superseded** / retained;  
- `reminder_count` / `last_alerted_at` cleared only after approved renewal;  
- `governed_document_events` append-only with actor/action.

---

## OCR authority proof

- OCR proposals stored with `authoritative: false`;  
- wrong OCR number corrected on HR approve;  
- OCR-unavailable path: HR `correct_metadata` entered issue/expiry;  
- uploads succeeded without OCR;  
- UI/API legitimacy notes state HR review only — not PACI/MOI/PAM.

---

## Frontend results

| Check | Result |
|---|---|
| Dashboard `npm test` | **49/49** PASS |
| Dashboard `tsc -b` + production build | PASS (dist deployed to staging) |
| Employee capability foundation script | **GREEN** |
| Employee `tsc --noEmit` | PASS |
| Staging dashboard JS contains “HR reviewed” + “not PACI” | PASS |
| Production `/var/www/wathefni-dashboard` preserved | PASS |

---

## Frozen regression results

| Suite | Result |
|---|---|
| Kuwait first-client foundation staging matrix | **53/53** PASS |
| Offers/Hiring staging matrix | **38/38** PASS |
| Optional-module-boundary | **301/301** PASS |
| `smoke-test-onboarding-seeding.py` | **38/38** PASS |
| `smoke-test-compliance-actions.py` | **31/31** PASS |
| `smoke-test-document-upload.py` | **25/25** PASS |
| `smoke-test-document-hub.py` | **18/18** PASS |
| `smoke-test-employee-app-capabilities.py` | GREEN |
| Staging health | **200** |
| Production health | **200** (untouched) |

---

## Cleanup proof

| Check | Result |
|---|---|
| `KWDOCSTG1` / `KWDOCSTG2` companies | **0** |
| Governed versions for those companies | **0** |
| Foundation/Offers matrix companies (`KWPILOT`/`OFFERSTG`/…) | **0** |
| Boundary `STBND*` companies | **0** |
| Prohibited gov/statutory hooks in journey module | **PASS** |

---

## Residual limitations

- Employee-mobile is frozen as source artifact + API-proven on staging; native Expo OTA/store binary publish is outside this VPS staging host.  
- Sync OCR remains optional on employee/dashboard upload surfaces; HR metadata entry covers OCR-unavailable.  
- HR mobile remains review-oriented; primary mutate path is dashboard.  
- Classifier may still emit bucket codes `needs_review`/`valid`; HR-facing labels map to Pending HR review / HR reviewed.  
- Do not claim automatic Kuwait legal compliance or PACI/MOI/PAM verification.

---

## Exact production promotion plan

**Do not execute until owner approves exact artifact `4be5298e…`.**

1. Owner approval of this staging-green pin only.  
2. Production backup + documented rollback.  
3. Additive `ensure_document_journey_schema` while current prod code runs (prove health).  
4. Surgical install of the **same product files** at the SHAs above (never sync unrelated dirty tree / full local `app.py`).  
5. Deploy matching dashboard dist to production public path only after backend health.  
6. Publish/ship employee-mobile build matching frozen source SHAs.  
7. Restart prod; health + environment binding.  
8. Re-run document-journey matrix + foundation + frozen pre-hiring/post-hire matrices (dry_run delivery).  
9. Orphan/residue sweep; pin production-green only if all pass.  
10. Do **not** claim PACI/MOI/PAM verification or automatic legal compliance in product copy.

---

## Owner next step

Approve production promotion of **exactly** `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7`. Do not ship a different tree. **Do not deploy to production from this report alone.**
