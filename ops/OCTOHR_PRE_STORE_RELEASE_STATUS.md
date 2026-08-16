# OCTOHR PRE-STORE RELEASE — CUTOVER ACCEPTED / FINAL AUTOMATION PENDING

**Date:** 2026-08-17

**Requested internal stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`

**Stamp issued:** **no — final requested automated gates are still running**

**Authority result:** **OCTOHR DOMAIN/BRAND CUTOVER GREEN; AUTHENTICATED EMPLOYEE MATRIX AND FINAL RELEASE HARNESS PENDING**

Frozen HCM/Product/PT authorities were not reopened. HR Web redesign, Analytics redesign, and new product work were not started.

## Accepted production cutover

- `https://octo-hr.com` is the canonical public OctoHR site.
- `https://app.octo-hr.com` is the canonical HR Web entry point.
- `https://api.octo-hr.com` is the canonical production API and governed App/Universal Link host.
- `https://octo-hr.com/privacy` and `https://octo-hr.com/support` are public HTTP 200 destinations.
- `wathefni.ai` and `www.wathefni.ai` remain path-compatible public aliases.
- `api.wathefni.ai` remains a full backward-compatible API/association proxy for already-built clients.
- Caddy and the orchestrator are healthy after the cutover. The frozen R8 `/ready` payload remains green for environment binding, link signing, delivery, migrations, errors, and failed jobs.
- DNS/Caddy are frozen after acceptance and must not change again without a genuine regression.

## Brand and runtime authority

- Pre-auth and platform/legal/support surfaces use OctoHR.
- Authenticated tenant-aware Employee and HR surfaces prefer the resolved company display name/logo and fail safely to OctoHR.
- Stable technical identifiers remain unchanged, including `ai.wathefni.employee`, `WATHEFNI_*` variables, database/migration names, the `wathefni://` scheme, and historical evidence.
- The source/runtime brand gates report zero unexplained customer-visible `Wathefni`, `WATHEFNI`, or `وظفني` defects.
- The active production OTA runtime cannot receive the retired 0.3.0 branding update.
- Android store build `709710c8-70b2-4d88-9666-67a82ec68d33` remains the qualified signed 0.3.1 AAB; stable package and signing identities were not changed.

## Current deterministic qualification

- Functional coverage ledger: **2,093/2,093**, with **0 unowned**.
- Client API contracts: **1,238/1,238**.
- Assistant tools: **28/28**.
- Canonical `api.octo-hr.com` App/Universal Link suite: **89/89**.
- Legacy `api.wathefni.ai` compatibility suite: **89/89**.
- Store configuration gate: **34/34**.
- Latest smoke safety net before the final rerun: **`SMOKE_OK`**.

## Remaining authorized closure scope

Only these automatable gates remain in scope:

1. authenticated Employee iOS EN and AR;
2. authenticated Employee Android EN and AR;
3. final `./ops/test-smoke`;
4. final `./ops/test-release`;
5. final canonical/legacy association and store-configuration checks.

The owner explicitly excluded the real-iPhone and real-Android physical checklists from this closure. No physical observation is fabricated or relabelled as a simulator/device result. Missing local simulator runtime or local disk capacity is not a release blocker when the required authenticated flows are proven through the available deterministic UI environment.

The full-pass stamp remains withheld until every gate above is genuinely green and the final evidence/status commit is pushed.
