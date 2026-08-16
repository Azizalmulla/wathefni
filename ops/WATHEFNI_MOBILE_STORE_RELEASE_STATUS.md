# WATHEFNI MOBILE STORE RELEASE — STATUS

**Stamp issued:** none  
**Requested stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`  
**Date:** 2026-08-16  
**Result:** **NOT GREEN — remaining gates below**

HR Web UX redesign was not started. Frozen HCM / R2–R8 / R5 / PT1–PT7 were not re-opened.

---

## Functional coverage ledger (actual counts)

Source: `ops/e2e/functional-coverage-ledger.json` (1390 production records).

| Surface | Covered / inventory | Notes |
|---|---|---|
| Web routes | **34/34** | Page union + nav structural |
| Web actions | **614/614** | Wired controls; dead-control scan **3/0**. Mapped to existing contracts where the route/action appears in smoke/qualify tests. Not a per-button browser E2E. |
| Setup actions | **27/27** | Setup cards + R6 structural |
| Employee mobile | **74/74** | Composition routes/screens. **Maestro UI still 0.** |
| HR mobile | **40/40** | Screen inventory. **Maestro UI still 0.** |
| Deep links | **38/38** | Live HTTPS on `https://api.wathefni.ai` — 84/0 including unknown-slug 404 |
| Client API contracts | **158/535** | Named in existing automated tests. **377 still inventoried.** |
| Assistant tools | **26/28** | 2 still inventoried |

**Zero untested is not met.** 379 records remain inventoried (almost all API operations).

---

## Blockers this run

### 1. Owner bootstrap — GREEN on staging, patched on production

Explicit bundle `setup_owner_bootstrap_v1`: `employees.read` + `employees.manage` only. Not inferred from `role=owner`. Written in the same Setup transaction, idempotent, audited.

Clean canary `QA11D090`: create company → seed owner → accept → login → Setup → **owner POST /dashboard/posthire/employees succeeds** → roster GET. **18/0.** Evidence: `ops/evidence/store-release-clean-canary-20260816T013513Z/`.

Production `:8010` now has `setup_owner_bootstrap.py` and the three write paths (seed / accept / team-invite).

### 2. Production `/ready` — GREEN (Caddy was the 404)

Cause: live Caddy `handle { respond "Not Found" 404 }` never proxied `/ready` or `/health`. Uvicorn `:8010` already had the handler.

`https://api.wathefni.ai/ready` → **200** `status=ready`, environment_binding.match=true, trusted_authority_enforced=true. `/health` 200.

Production payload is the older listener schema (no `link_signing` / `delivery` keys). Staging `/ready` still has the full R8 body. Store URL remains `https://api.wathefni.ai`, not staging.

### 3. Universal / App Links — HTTP GREEN; device verify blocked on secrets

- iOS `associatedDomains`: `applinks:api.wathefni.ai`
- Android App Links intent filter: `https://api.wathefni.ai/l`
- Custom scheme `wathefni://` preserved
- AASA + assetlinks served on production
- All 38 registered destinations + unknown-slug 404 live
- Client stashes HTTPS URL until signed in; employee never opens `/hr`; HR only opens `/hr`
- Module/app disabled and allowlist denial are first-class access states

**AASA `details` is empty** until `WATHEFNI_IOS_APP_ID` (Apple Team ID + bundle) is provisioned.  
**assetlinks is `[]`** until `WATHEFNI_ANDROID_SHA256_CERTS` is provisioned.  
Installed-app intercept will not verify on a real device until those exist. Store badge IDs in fallback HTML are still placeholders.

### 4. Maestro environment — Java green; runtimes in flight; MOBILE_PASS = 0

| Piece | State |
|---|---|
| Maestro CLI | present (`~/.maestro/bin/maestro`) |
| Java 17 | **installed** (Homebrew openjdk@17) |
| simctl / Xcode 26 | present via `DEVELOPER_DIR` |
| iOS simulator runtime | **downloading** iOS 26.0.1 (8.05 GB) — ~2.6% when last sampled |
| App on simulator | not installed |
| Android `adb` / emulator | commandlinetools cask still fetching; no USB device |
| Physical iPhone / Android | **ABSENT** |

Maestro smoke flows now drop `takeScreenshot` for the store loop. No video. No AI vision.

---

## Still required before FULL_PASS

1. Finish iOS runtime download, boot a simulator, install `ai.wathefni.employee`, run Employee + HR Maestro (no screenshots).
2. Finish Android SDK + emulator (or USB device) and run Employee + HR Maestro.
3. Owner: provision `WATHEFNI_IOS_APP_ID` and `WATHEFNI_ANDROID_SHA256_CERTS` on production, then re-qualify AASA/assetlinks non-empty.
4. Close **377 inventoried API operations** with cheapest authorized proofs (fail-closed probe is written; a scoping bug blocked the first staging run).
5. Physical RP on one real iPhone and one real Android — checklist: `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md`. **Never fabricate PASS.**
6. Optional: promote full R8 `/ready` body (`link_signing`, `delivery`) onto the production app.py listener.

---

## Frozen / preserved (not rerun)

| Phase | Result |
|---|---|
| R9 two-tenant attack | 48/0 |
| R10 measured performance | no 2.5s blocker |
| R11 EN/AR catalogs | 53/0 unit |
| Store build config | 20/0 including associatedDomains |
| Staging `/ready` | 200 |
| Cross-surface leave | 12/0 |

Do not treat this file as `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`.
