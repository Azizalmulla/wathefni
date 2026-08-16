# Wathefni repository guidance

## Scope and frozen authority

- Preserve accepted and frozen domain authorities. Read the applicable `ops/*FULL_PASS.md` and `ops/*FREEZE_AMENDMENT.md` before changing a frozen area.
- Extend through existing contracts, adapters, and overlays. Do not introduce a second source of truth, evaluator, audit system, permission model, module registry, or notification path.
- Reopen a frozen authority only for a documented correctness or security blocker with an explicit freeze amendment and owner scope.

## Security and composition

- The authenticated session company is the tenant authority. Keep `company_code` predicates on every tenant-owned read and write; client headers, route parameters, roles, and UI visibility never expand authority. Fail closed on empty or mismatched scope.
- Roles grant permissions; modules grant entitlements. A surface requires both. Use the canonical module catalog, `company_modules`, effective-module helpers, and `capability_readiness`; do not invent parallel availability logic or silently auto-enable dependencies.
- Disabling a module stops new work, hides normal surfaces, blocks governed APIs, preserves history, and suppresses new notifications. Re-enabling restores preserved history.

## Product requirements

- Every changed customer journey must remain complete in English and Arabic, including real RTL layout, validation, loading, empty, unavailable, and error states.
- Production surfaces must never fabricate demo, fixture, fallback, or silently-empty-on-error data. Unproved behavior stays labelled unverified; physical-device PASS must be observed on real hardware.
- Setup owns customer-facing configuration. Environment variables are only for secrets, allowlists, and kill switches.

## Verification

- Fast local safety net: `PYTHONDONTWRITEBYTECODE=1 ./ops/test-smoke`
- Full release harness: `./ops/test-release` only with the intended staging/production credentials and owner-approved targets; it performs live qualification and clean-canary writes.
- Run the closest frozen regression and qualification scripts for any touched authority. Never replace required staging, live, or physical evidence with a source/unit test.

## Current priority and stop rules

- Current priority is the mobile store-release gate in `ops/WATHEFNI_MOBILE_STORE_RELEASE_STATUS.md`: close 377 API proof gaps and 2 assistant gaps, complete the four Maestro surface/platform runs, provision production App/Universal Link identifiers, and execute physical iPhone and Android RP.
- Do not reopen Waves 1–6, R2–R11, R5A–R5J, PT1–PT7, the frozen HR/HCM authorities, or begin HR Web redesign/new HCM scope unless the owner explicitly directs it.
- After completing the requested checkpoint or release slice, stop. Do not automatically begin the next phase.
