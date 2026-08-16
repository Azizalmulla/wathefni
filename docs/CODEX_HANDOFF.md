# Codex handoff

**Updated:** 2026-08-16  
**Branch:** `authority-cutover`  
**Current release stamp:** none  
**Requested stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`  
**Status:** **NOT GREEN**

This checkpoint preserves the verified Wathefni workspace after the Cursor-to-Codex cutover. It is a handoff, not a release claim. HR Web redesign and new HCM development have not started.

## Verified release state

- Functional ledger: 1,390 records. Web routes 34/34, web actions 614/614, Setup actions 27/27, employee mobile 74/74, HR mobile 40/40, and deep links 38/38.
- Remaining inventory: client API contracts 158/535 (**377 unproved**) and assistant tools 26/28 (**2 unproved**).
- Clean owner canary `QA11D090`: 18/0 on staging. Owner bootstrap is explicit, idempotent, audited, and grants only `employees.read` + `employees.manage`.
- Production `https://api.wathefni.ai/ready` and `/health` return 200. Production still exposes the older `/ready` payload without the staging `link_signing` and `delivery` fields.
- Universal/App Link HTTP routing is green for all 38 destinations plus unknown-slug 404. Real-device association remains blocked until `WATHEFNI_IOS_APP_ID` and `WATHEFNI_ANDROID_SHA256_CERTS` are provisioned; store badge IDs remain placeholders.
- Maestro CLI and Java 17 are present, but the four required Employee/HR × iOS/Android UI runs have no PASS. Physical iPhone and Android qualification is absent and must never be inferred or fabricated.
- Frozen regression evidence remains: R9 48/0 live two-tenant attack, R10 no 2.5-second blocker, R11 53/0 EN/AR unit, store build config 20/0, staging `/ready` 200, and cross-surface leave 12/0.

## Required work before full pass

1. Complete Employee and HR Maestro runs on iOS and Android with real runnable targets.
2. Provision production Apple App ID and Android SHA-256 certificate association values, then prove non-empty AASA and assetlinks responses.
3. Close the 377 inventoried API proofs and 2 assistant-tool proofs with authorized, fail-closed coverage.
4. Execute `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md` on one physical iPhone and one physical Android, in EN and AR/RTL.
5. Optionally promote the full R8 `/ready` schema to the production listener; do not change the store API base from `https://api.wathefni.ai`.

## Commands and evidence

- Fast local check: `PYTHONDONTWRITEBYTECODE=1 ./ops/test-smoke`
- Full live/staging release harness: `./ops/test-release` only with owner-approved targets and credentials.
- Status authority: `ops/WATHEFNI_MOBILE_STORE_RELEASE_STATUS.md`
- Physical checklist: `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md`
- Functional inventory: `ops/e2e/functional-coverage-ledger.json`

## Do not reopen

Preserve Waves 1–6, R2–R11, R5A–R5J, PT1–PT7, and all accepted freeze amendments. Continue only the remaining store-release gates unless the owner explicitly changes scope. Do not start HR Web redesign or new feature work from this handoff.
